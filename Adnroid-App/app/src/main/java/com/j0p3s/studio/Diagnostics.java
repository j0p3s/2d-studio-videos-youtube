package com.j0p3s.studio;
import android.content.*;
import android.app.*;
import android.os.*;
import android.media.*;
import android.util.Log;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.zip.*;
import org.json.*;

final class Diagnostics {
 static Context context;static File folder;
 static void initialize(Context c){context=c.getApplicationContext();folder=new File(c.getFilesDir(),"diagnostics");folder.mkdirs();
  Thread.UncaughtExceptionHandler previous=Thread.getDefaultUncaughtExceptionHandler();
  Thread.setDefaultUncaughtExceptionHandler((thread,error)->{failure("uncaught · "+thread.getName(),error);try{write(new File(folder,"last-crash.txt"),Log.getStackTraceString(error));}catch(Exception ignored){}if(previous!=null)previous.uncaughtException(thread,error);else android.os.Process.killProcess(android.os.Process.myPid());});
  event("lifecycle","App started · version=0.2.0 · Android="+Build.VERSION.RELEASE+" · model="+Build.MODEL);
 }
 static String clean(String s){return s.replaceAll("(?i)(Bearer\\s+)[^\\s\"']+","$1[REDACTED]").replaceAll("sk-[a-zA-Z0-9_-]{12,}","[REDACTED]");}
 static synchronized void event(String stage,String message){if(folder==null)return;String line=java.time.Instant.now()+" ["+stage+"] "+clean(message)+"\n";try{File f=new File(folder,"events.log");if(f.length()>1024*1024){File old=new File(folder,"previous.log");if(old.exists())old.delete();f.renameTo(old);}try(FileOutputStream o=new FileOutputStream(f,true)){o.write(line.getBytes(StandardCharsets.UTF_8));}}catch(Exception ignored){}Log.i("StudioDebug",clean(stage+": "+message));}
 static void failure(String stage,Throwable error){event(stage,Log.getStackTraceString(error));}
 static void write(File f,String text)throws Exception{try(FileOutputStream o=new FileOutputStream(f)){o.write(clean(text).getBytes(StandardCharsets.UTF_8));}}
 static String recent(){try{return TextFiles.read(new File(folder,"events.log").toPath());}catch(Exception e){return "No logs yet";}}
 static String scrubSecrets(String text){try{JSONObject cfg=new JSONObject(Vault.load(context));for(String key:new String[]{"apiKey","speechKey"}){String secret=cfg.optString(key);if(!secret.isBlank())text=text.replace(secret,"[REDACTED]");}}catch(Exception ignored){}return clean(text);}
 static File export()throws Exception {
  File outFolder=new File(context.getCacheDir(),"debug-reports");outFolder.mkdirs();File file=new File(outFolder,"studio-diagnostics.zip");
  event("debug","Diagnostic export requested");
  try(ZipOutputStream zip=new ZipOutputStream(new FileOutputStream(file))){
   for(String name:new String[]{"events.log","previous.log","last-crash.txt"}){File f=new File(folder,name);if(f.exists())entry(zip,name,TextFiles.read(f.toPath()));}
   JSONObject info=new JSONObject().put("version","0.2.0").put("model",Build.MODEL).put("manufacturer",Build.MANUFACTURER).put("android",Build.VERSION.RELEASE).put("sdk",Build.VERSION.SDK_INT).put("freeBytes",context.getFilesDir().getUsableSpace());
   JSONArray codecs=new JSONArray();for(MediaCodecInfo codec:new MediaCodecList(MediaCodecList.REGULAR_CODECS).getCodecInfos())if(codec.isEncoder())codecs.put(new JSONObject().put("name",codec.getName()).put("hardware",codec.isHardwareAccelerated()).put("types",new JSONArray(java.util.Arrays.asList(codec.getSupportedTypes()))));info.put("encoders",codecs);entry(zip,"device.json",info.toString(2));
   JSONArray exits=new JSONArray();for(ApplicationExitInfo exit:context.getSystemService(ActivityManager.class).getHistoricalProcessExitReasons(null,0,5))exits.put(new JSONObject().put("time",exit.getTimestamp()).put("reason",exit.getReason()).put("description",exit.getDescription()).put("status",exit.getStatus()));entry(zip,"process-exits.json",exits.toString(2));
   try{java.lang.Process p=new ProcessBuilder("logcat","-d","--pid="+android.os.Process.myPid(),"-t","400").redirectErrorStream(true).start();try(InputStream in=p.getInputStream()){entry(zip,"logcat.txt",new String(in.readNBytes(128*1024),StandardCharsets.UTF_8));}p.destroy();}catch(Exception e){entry(zip,"logcat.txt","Logcat unavailable: "+e.getClass().getSimpleName());}
   entry(zip,"README.txt","App-only diagnostic report. Credentials, scene plans and audio are excluded. Review the report before sharing. Previous process exit reasons may include ANRs or native crashes. Java crashes are recorded in last-crash.txt.");
  }return file;
 }
 static void entry(ZipOutputStream zip,String name,String text)throws Exception{zip.putNextEntry(new ZipEntry(name));zip.write(scrubSecrets(text).getBytes(StandardCharsets.UTF_8));zip.closeEntry();}
}
