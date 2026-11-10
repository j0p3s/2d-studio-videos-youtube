package com.j0p3s.studio;
import android.app.*;
import android.content.*;
import android.os.*;
import android.provider.MediaStore;
import java.io.*;
import java.nio.file.Files;
import org.json.*;

public class RenderService extends Service {
 static volatile Thread worker;static final String CHANNEL="render";
 public android.os.IBinder onBind(Intent i){return null;}
 void status(int percent,String text){getSharedPreferences("status",0).edit().putString("message",text).putInt("percent",percent).apply();
  Notification n=new Notification.Builder(this,CHANNEL).setContentTitle("2D Studio · "+percent+"%").setContentText(text).setSmallIcon(android.R.drawable.ic_media_play).setProgress(100,percent,false).build();getSystemService(NotificationManager.class).notify(1,n);}
 public int onStartCommand(Intent i,int flags,int id){
  if(i!=null&&"cancel".equals(i.getAction())){if(worker!=null)worker.interrupt();return START_NOT_STICKY;}
  if(worker!=null)return START_NOT_STICKY;
  getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel(CHANNEL,"Video export",NotificationManager.IMPORTANCE_LOW));
  startForeground(1,new Notification.Builder(this,CHANNEL).setContentTitle("Preparing 1080p export").setSmallIcon(android.R.drawable.ic_media_play).build());
  getSharedPreferences("status",0).edit().putBoolean("running",true).apply();
  worker=new Thread(()->{
   PowerManager.WakeLock lock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"studio:export");lock.acquire(6*60*60*1000L);
   File temp=new File(getFilesDir(),"current-export");temp.mkdirs();
   try{
    int testSeconds=i==null?0:i.getIntExtra("testSeconds",0);
    if(testSeconds!=0&&testSeconds!=10&&testSeconds!=600)throw new IOException("Invalid test duration");
    JSONObject cfg=new JSONObject(Vault.load(this));JSONObject plan;
    if(testSeconds>0){JSONArray demo=new JSONArray();for(int s=0;s<testSeconds/10;s++)demo.put(new JSONObject().put("narration","Silent device benchmark. This tests rendering, not AI or voice quality.").put("caption","1080p device test · scene "+(s+1)).put("setting",new String[]{"desk","space","city","diagram"}[s%4]).put("prop",new String[]{"book","phone","clock","steps"}[s%4]));plan=new JSONObject().put("language","en").put("title","Silent benchmark").put("scenes",demo);}
    else plan=new JSONObject(TextFiles.read(new File(getFilesDir(),"plan.json").toPath()));Cloud.validate(plan);
    JSONArray scenes=plan.getJSONArray("scenes");File pcm=new File(temp,"voice.pcm");long bytes=0;
    try(OutputStream audio=new FileOutputStream(pcm)){
     for(int s=0;s<scenes.length();s++){VideoEncoder.check();status(s*30/scenes.length(),"Microsoft Neural · scene "+(s+1)+"/"+scenes.length());JSONObject scene=scenes.getJSONObject(s);
      byte[] data=testSeconds>0?new byte[480000]:null;Exception failure=null;for(int attempt=0;attempt<3&&data==null;attempt++){try{data=Cloud.speech(cfg,scene.getString("narration"));break;}catch(Exception e){failure=e;VideoEncoder.check();if(attempt<2)Thread.sleep(1000L*(attempt+1));}}
      if(data==null)throw failure;if(data.length==0||data.length%2!=0)throw new IOException("Invalid Microsoft speech PCM");scene.put("startUs",Timeline.pcmDuration(bytes));bytes+=data.length;if(Timeline.pcmDuration(bytes)>Timeline.MAX_US)throw new IOException("Narration exceeds 10 minutes. Shorten the plan.");scene.put("endUs",Timeline.pcmDuration(bytes));audio.write(data);
     }
    }
    TextFiles.write(new File(temp,"timed-plan.json").toPath(),plan.toString(2));
    status(30,"Encoding English audio");File audio=new File(temp,"audio.m4a"),video=new File(temp,"video.mp4"),out=new File(temp,"final.mp4");VideoEncoder.audio(pcm,audio);
    VideoEncoder.video(scenes,video,(p,stage)->status(32+p*63/100,stage));status(96,"Muxing video and narration");VideoEncoder.mux(video,audio,out);VideoEncoder.check();
    android.media.MediaMetadataRetriever metadata=new android.media.MediaMetadataRetriever();try{metadata.setDataSource(out.toString());if(!"1920".equals(metadata.extractMetadata(18))||!"1080".equals(metadata.extractMetadata(19)))throw new IOException("Output resolution check failed");}finally{metadata.release();}
    ContentValues values=new ContentValues();values.put(MediaStore.Video.Media.DISPLAY_NAME,"2D-Studio-"+System.currentTimeMillis()+".mp4");values.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4");values.put(MediaStore.Video.Media.RELATIVE_PATH,"Movies/2D-Studio");values.put(MediaStore.Video.Media.IS_PENDING,1);
    android.net.Uri uri=getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values);if(uri==null)throw new IOException("Cannot create movie");
    try {try(OutputStream dest=getContentResolver().openOutputStream(uri);InputStream source=new FileInputStream(out)){source.transferTo(dest);}values.clear();values.put(MediaStore.Video.Media.IS_PENDING,0);getContentResolver().update(uri,values,null,null);}
    catch(Exception e){getContentResolver().delete(uri,null,null);throw e;}
    getSharedPreferences("status",0).edit().putString("video",uri.toString()).apply();status(100,"Ready · Movies/2D-Studio · "+(Timeline.pcmDuration(bytes)/1000000)+"s");
   }catch(Exception e){status(0,Thread.currentThread().isInterrupted()?"Export cancelled":"Export failed: "+e.getMessage());}
   finally{if(lock.isHeld())lock.release();getSharedPreferences("status",0).edit().putBoolean("running",false).apply();worker=null;stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();}
  },"studio-render");worker.start();return START_NOT_STICKY;
 }
 public void onDestroy(){if(worker!=null)worker.interrupt();super.onDestroy();}
 @Override public void onTimeout(int startId,int type){if(worker!=null)worker.interrupt();getSharedPreferences("status",0).edit().putBoolean("running",false).putString("message","Android stopped the export at the foreground-service time limit. Retry from the saved plan.").apply();stopSelf();}
}
