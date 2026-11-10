package com.j0p3s.studio;
import android.content.Context;
import android.media.*;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.*;
import java.nio.*;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;

final class EdgeSpeech {
 static synchronized void initialize(Context context){if(!Python.isStarted())Python.start(new AndroidPlatform(context.getApplicationContext()));}
 static byte[] synthesize(Context context,String text)throws Exception {
  initialize(context);byte[] hash=MessageDigest.getInstance("SHA-256").digest(("Andrew-en-v1\n"+text).getBytes(StandardCharsets.UTF_8));StringBuilder name=new StringBuilder();for(byte b:hash)name.append(String.format("%02x",b));
  File folder=new File(context.getCacheDir(),"edge-speech");folder.mkdirs();File mp3=new File(folder,name+".mp3");
  if(!mp3.exists()||mp3.length()<100){Diagnostics.event("speech", "Edge request · characters="+text.length());Python.getInstance().getModule("edge_voice").callAttr("synthesize",text,mp3.toString());}
  else Diagnostics.event("speech","Edge audio cache hit");
  return decode(mp3);
 }
 static byte[] decode(File file)throws Exception {
  MediaExtractor extractor=new MediaExtractor();MediaCodec decoder=null;boolean started=false;
  try {
   extractor.setDataSource(file.toString());int track=-1;for(int t=0;t<extractor.getTrackCount();t++)if(extractor.getTrackFormat(t).getString(MediaFormat.KEY_MIME).startsWith("audio/")){track=t;break;}
   if(track<0)throw new IOException("Edge MP3 has no audio track");extractor.selectTrack(track);MediaFormat format=extractor.getTrackFormat(track);decoder=MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME));decoder.configure(format,null,null,0);decoder.start();started=true;
   ByteArrayOutputStream pcm=new ByteArrayOutputStream();MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();boolean inputEnded=false,outputEnded=false;long deadline=System.nanoTime()+60_000_000_000L;
   while(!outputEnded){VideoEncoder.check();if(System.nanoTime()>deadline)throw new IOException("MP3 decoder timeout");
    if(!inputEnded){int id=decoder.dequeueInputBuffer(10000);if(id>=0){ByteBuffer b=decoder.getInputBuffer(id);b.clear();int n=extractor.readSampleData(b,0);inputEnded=n<0;decoder.queueInputBuffer(id,0,Math.max(0,n),inputEnded?0:extractor.getSampleTime(),inputEnded?MediaCodec.BUFFER_FLAG_END_OF_STREAM:0);if(!inputEnded)extractor.advance();}}
    int id=decoder.dequeueOutputBuffer(info,10000);
    if(id==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){MediaFormat f=decoder.getOutputFormat();if(f.getInteger(MediaFormat.KEY_SAMPLE_RATE)!=24000||f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)!=1)throw new IOException("Expected 24kHz mono Edge audio");if(f.containsKey(MediaFormat.KEY_PCM_ENCODING)&&f.getInteger(MediaFormat.KEY_PCM_ENCODING)!=android.media.AudioFormat.ENCODING_PCM_16BIT)throw new IOException("Expected 16-bit Edge PCM");}
    if(id>=0){ByteBuffer b=decoder.getOutputBuffer(id);b.position(info.offset);b.limit(info.offset+info.size);byte[] bytes=new byte[info.size];b.get(bytes);pcm.write(bytes);outputEnded=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;decoder.releaseOutputBuffer(id,false);}
   }
   if(pcm.size()==0)throw new IOException("Edge decoded audio is empty");return pcm.toByteArray();
  }finally{if(decoder!=null){if(started)decoder.stop();decoder.release();}extractor.release();}
 }
}
