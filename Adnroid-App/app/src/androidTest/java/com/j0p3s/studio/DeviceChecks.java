package com.j0p3s.studio;
import android.app.*;
import android.content.*;
import android.os.Bundle;
import java.io.*;
import java.util.zip.*;
import org.json.*;

/** Explicit on-device integration checks, launched only with adb am instrument. */
public class DeviceChecks extends Instrumentation {
 boolean skipUi,longRender,crash;
 public void onCreate(Bundle args){super.onCreate(args);skipUi="true".equals(args.getString("skipUi"));longRender="true".equals(args.getString("longRender"));crash="true".equals(args.getString("crash"));start();}
 void require(boolean condition,String message){if(!condition)throw new AssertionError(message);}
 public void onStart(){Bundle result=new Bundle();try{
  Context c=getTargetContext();MainActivity activity=(MainActivity)startActivitySync(new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
  if(crash){runOnMainSync(()->new android.os.Handler(android.os.Looper.getMainLooper()).post(()->{throw new IllegalStateException("User-requested diagnostic crash test");}));Thread.sleep(10000);throw new AssertionError("Crash test did not terminate process");}
  if(!skipUi){getUiAutomation();runOnMainSync(activity::options);waitForIdleSync();Thread.sleep(500);
  require(getUiAutomation().getRootInActiveWindow().findAccessibilityNodeInfosByText("Debug / Diagnostics").size()>0,"Options menu missing debug entry");
  sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);runOnMainSync(activity::debugMenu);waitForIdleSync();Thread.sleep(300);
  require(getUiAutomation().getRootInActiveWindow().findAccessibilityNodeInfosByText("Export diagnostic ZIP").size()>0,"Debug export entry missing");sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);}
  Diagnostics.failure("device-check",new IllegalStateException("Test exception persisted without crashing"));File report=Diagnostics.export();
  try(ZipFile zip=new ZipFile(report)){require(zip.getEntry("events.log")!=null,"Missing app log");require(zip.getEntry("device.json")!=null,"Missing device info");require(zip.getEntry("process-exits.json")!=null,"Missing crash history");require(zip.getEntry("plan.json")==null,"Scene plan must not be exported");}
  require(!Diagnostics.clean("Bearer private-test-token").contains("private-test-token"),"Redaction failed");
  byte[] pcm=EdgeSpeech.synthesize(c,"Start small. This English Microsoft Neural voice is generated without an Azure API key.");require(pcm.length>48000,"Free Edge voice too short");
  File dir=new File(c.getFilesDir(),"device-check");dir.mkdirs();File raw=new File(dir,"voice.pcm"),audio=new File(dir,"voice.m4a"),video=new File(dir,"video.mp4"),out=new File(dir,"final.mp4");try(FileOutputStream f=new FileOutputStream(raw)){f.write(pcm);}VideoEncoder.audio(raw,audio);
  if(longRender){try(FileOutputStream f=new FileOutputStream(raw)){byte[] silence=new byte[48000];for(int second=0;second<600;second++)f.write(silence);}VideoEncoder.audio(raw,audio);}
  JSONArray scenes=new JSONArray().put(new JSONObject().put("startUs",0).put("endUs",longRender?Timeline.MAX_US:Timeline.pcmDuration(pcm.length)).put("narration",longRender?"Ten-minute silent 1080p device stress test.":"Start small. This English Microsoft Neural voice is generated without an Azure API key.").put("caption",longRender?"1080p / 10-minute stress test":"Free Microsoft Neural speech").put("setting","desk").put("prop","book"));
  VideoEncoder.video(scenes,video,(p,stage)->Diagnostics.event("device-render",p+"% "+stage));VideoEncoder.mux(video,audio,out);
  android.media.MediaMetadataRetriever metadata=new android.media.MediaMetadataRetriever();try{metadata.setDataSource(out.toString());require("1920".equals(metadata.extractMetadata(18)),"Wrong width");require("1080".equals(metadata.extractMetadata(19)),"Wrong height");}finally{metadata.release();}
  Diagnostics.event("device-check","PASSED: UI="+(!skipUi)+", logs ZIP, redaction, free Edge voice, AAC, 1080p AVC and mux");Diagnostics.export();result.putString("result","PASS: UI="+(!skipUi)+", diagnostics export, free Edge speech and 1080p narrated render");finish(Activity.RESULT_OK,result);
 }catch(Throwable error){Diagnostics.failure("device-check-failed",error);result.putString("result","FAIL: "+android.util.Log.getStackTraceString(error));finish(Activity.RESULT_CANCELED,result);}}
}
