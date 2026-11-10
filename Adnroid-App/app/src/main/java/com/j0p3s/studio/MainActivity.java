package com.j0p3s.studio;
import android.app.*;
import android.os.*;
import android.content.*;
import android.graphics.Color;
import android.widget.*;
import android.text.InputType;
import java.io.*;
import java.nio.file.Files;
import org.json.*;

public class MainActivity extends Activity {
 EditText topic,model,key,speech,region,editor,minutes;Spinner provider;TextView status;ProgressBar bar;Button generate,render;boolean generating=false;
 Handler handler=new Handler(Looper.getMainLooper());
 EditText field(LinearLayout parent,String hint,boolean secret){EditText e=new EditText(this);e.setHint(hint);e.setTextColor(Color.WHITE);e.setHintTextColor(0xff9caab8);if(secret)e.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);parent.addView(e);return e;}
 Button button(LinearLayout parent,String label,Runnable action){Button b=new Button(this);b.setText(label);b.setOnClickListener(v->action.run());parent.addView(b);return b;}
 void alert(String text){new AlertDialog.Builder(this).setMessage(text).setPositiveButton("OK",null).show();}
 JSONObject config()throws Exception{return new JSONObject().put("provider",provider.getSelectedItem().toString()).put("model",model.getText().toString().trim()).put("apiKey",key.getText().toString().trim()).put("region",region.getText().toString().trim()).put("speechKey",speech.getText().toString().trim());}
 public void onCreate(Bundle state){super.onCreate(state);if(RenderService.worker==null)getSharedPreferences("status",0).edit().putBoolean("running",false).apply();getWindow().setStatusBarColor(0xff0b1320);ScrollView scroll=new ScrollView(this);LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(32,24,32,40);root.setBackgroundColor(0xff0b1320);scroll.addView(root);setContentView(scroll);
  TextView title=new TextView(this);title.setText("2D STUDIO / ANDROID\n1080p · English · up to 10 minutes");title.setTextColor(0xff6af5b4);title.setTextSize(24);root.addView(title);
  TextView note=new TextView(this);note.setText("AI and Microsoft speech need internet and API credentials. Rendering runs on this phone. This version uses native animated scenes, not the desktop GrowKaz engine.");note.setTextColor(0xffb8c7d6);root.addView(note);
  topic=field(root,"Video topic",false);minutes=field(root,"Target minutes (1–10)",false);minutes.setInputType(InputType.TYPE_CLASS_NUMBER);minutes.setText("1");
  provider=new Spinner(this);provider.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Gemini","OpenAI","Claude"}));root.addView(provider);
  model=field(root,"Model ID available in your API account",false);key=field(root,"Selected provider API key",true);region=field(root,"Microsoft Azure Speech region, e.g. eastus",false);speech=field(root,"Microsoft Azure Speech key",true);
  button(root,"Save credentials on this device",()->{try{Vault.save(this,config().toString());alert("Saved encrypted on this device. API access is separate from CLI login.");}catch(Exception e){alert(e.getMessage());}});
  generate=button(root,"1 · Generate English script & scene plan",this::generate);
  editor=field(root,"Review or paste English scene-plan JSON",false);editor.setMinLines(8);editor.setGravity(android.view.Gravity.TOP);editor.setTextSize(14);
  render=button(root,"2 · Generate Microsoft voice & export 1080p",()->{try{if(generating||getSharedPreferences("status",0).getBoolean("running",false))throw new IOException("A job is running");JSONObject p=new JSONObject(editor.getText().toString());Cloud.validate(p);JSONObject cfg=config();if(cfg.getString("speechKey").isBlank()||cfg.getString("region").isBlank())throw new IOException("Configure Microsoft Speech key and region");Vault.save(this,cfg.toString());TextFiles.write(new File(getFilesDir(),"plan.json").toPath(),p.toString());startForegroundService(new Intent(this,RenderService.class));}catch(Exception e){alert(e.getMessage());}});
  button(root,"Cancel export",()->{if(getSharedPreferences("status",0).getBoolean("running",false))startService(new Intent(this,RenderService.class).setAction("cancel"));});
  button(root,"Device benchmark · 1080p / 10 seconds · silent",()->benchmark(10));
  button(root,"Device benchmark · 1080p / 10 minutes · silent",()->benchmark(600));
  button(root,"Open latest video",()->{String uri=getSharedPreferences("status",0).getString("video","");if(uri.isEmpty()){alert("Export a video first");return;}try{startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(android.net.Uri.parse(uri),"video/mp4").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));}catch(Exception e){alert("No video player available");}});
  button(root,"Share latest video",()->{String uri=getSharedPreferences("status",0).getString("video","");if(!uri.isEmpty())startActivity(Intent.createChooser(new Intent(Intent.ACTION_SEND).setType("video/mp4").putExtra(Intent.EXTRA_STREAM,android.net.Uri.parse(uri)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),"Share video"));});
  bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);root.addView(bar);status=new TextView(this);status.setTextColor(Color.WHITE);root.addView(status);
  try{JSONObject cfg=new JSONObject(Vault.load(this));model.setText(cfg.optString("model"));key.setText(cfg.optString("apiKey"));region.setText(cfg.optString("region"));speech.setText(cfg.optString("speechKey"));String[] names={"Gemini","OpenAI","Claude"};for(int i=0;i<3;i++)if(names[i].equals(cfg.optString("provider")))provider.setSelection(i);File f=new File(getFilesDir(),"plan.json");if(f.exists())editor.setText(TextFiles.read(f.toPath()));}catch(Exception e){alert("Could not read saved configuration: "+e.getMessage());}
  requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},11);
 }
 void benchmark(int seconds){if(RenderService.worker!=null||generating){alert("A job is running");return;}new AlertDialog.Builder(this).setMessage("Export a silent "+seconds+"-second hardware test without AI or speech credentials?").setNegativeButton("Cancel",null).setPositiveButton("Start",(d,w)->startForegroundService(new Intent(this,RenderService.class).putExtra("testSeconds",seconds))).show();}
 void generate(){try{if(generating||getSharedPreferences("status",0).getBoolean("running",false))throw new IOException("A job is running");int duration=Integer.parseInt(minutes.getText().toString());if(duration<1||duration>10)throw new IOException("Choose 1–10 minutes");String subject=topic.getText().toString().trim();if(subject.isEmpty())throw new IOException("Enter a topic");JSONObject cfg=config();Vault.save(this,cfg.toString());generating=true;generate.setEnabled(false);status.setText("Generating English script…");new Thread(()->{try{JSONObject result=Cloud.plan(cfg,subject,duration);TextFiles.write(new File(getFilesDir(),"plan.json").toPath(),result.toString(2));runOnUiThread(()->{editor.setText(result.toString());status.setText("Plan ready. Review it before export.");});}catch(Exception e){runOnUiThread(()->alert(e.getMessage()));}finally{runOnUiThread(()->{generating=false;generate.setEnabled(true);});}}).start();}catch(Exception e){alert(e.getMessage());}}
 final Runnable poll=new Runnable(){public void run(){var p=getSharedPreferences("status",0);if(!generating){bar.setProgress(p.getInt("percent",0));status.setText(p.getString("message","Ready"));}handler.postDelayed(this,1000);}};
 public void onResume(){super.onResume();handler.post(poll);}public void onPause(){handler.removeCallbacks(poll);super.onPause();}
}
