package com.j0p3s.studio;
import android.media.*;
import android.opengl.*;
import android.view.Surface;
import java.io.*;
import java.nio.*;
import org.json.*;

final class VideoEncoder {
 interface Progress {void update(int percent,String stage)throws Exception;}
 static void check()throws InterruptedException {if(Thread.currentThread().isInterrupted())throw new InterruptedException("Cancelled");}
 static MediaCodec codec(String type)throws Exception {
  MediaCodecInfo fallback=null;for(MediaCodecInfo i:new MediaCodecList(MediaCodecList.REGULAR_CODECS).getCodecInfos())if(i.isEncoder())for(String t:i.getSupportedTypes())if(t.equalsIgnoreCase(type)){if(i.isHardwareAccelerated())return MediaCodec.createByCodecName(i.getName());fallback=i;}
  if(fallback==null)throw new IOException("No encoder for "+type);return MediaCodec.createByCodecName(fallback.getName());
 }
 static final class Drain implements AutoCloseable {
  MediaCodec codec;MediaMuxer mux;int track=-1;boolean started=false,ended=false;
  Drain(MediaCodec c,File f)throws Exception{codec=c;mux=new MediaMuxer(f.toString(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);}
  void pump(boolean end)throws Exception {
   MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();long deadline=System.nanoTime()+30_000_000_000L;
   while(true){check();int id=codec.dequeueOutputBuffer(info,end?10000:0);
    if(id==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){track=mux.addTrack(codec.getOutputFormat());mux.start();started=true;}
    else if(id>=0){ByteBuffer b=codec.getOutputBuffer(id);if((info.flags&MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0&&info.size>0){if(!started)throw new IOException("Muxer not ready");b.position(info.offset);b.limit(info.offset+info.size);mux.writeSampleData(track,b,info);}ended=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;codec.releaseOutputBuffer(id,false);if(ended)return;}
    else if(!end)return;
    if(System.nanoTime()>deadline)throw new IOException("Encoder drain timed out");
   }
  }
  public void close(){try{if(started)mux.stop();}finally{mux.release();}}
 }
 static void video(JSONArray scenes,File out,Progress progress)throws Exception {
  long total=scenes.getJSONObject(scenes.length()-1).getLong("endUs");int frames=Timeline.frames(total);
  MediaCodec enc=codec("video/avc");Surface surface=null;Gl gl=null;boolean running=false;
  try {
   MediaFormat f=MediaFormat.createVideoFormat("video/avc",1920,1080);f.setInteger(MediaFormat.KEY_COLOR_FORMAT,MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);f.setInteger(MediaFormat.KEY_BIT_RATE,8_000_000);f.setInteger(MediaFormat.KEY_FRAME_RATE,24);f.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL,2);
   enc.configure(f,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);surface=enc.createInputSurface();enc.start();running=true;gl=new Gl(surface);ScenePainter painter=new ScenePainter();int shot=0;
   try(Drain d=new Drain(enc,out)){
    for(int i=0;i<frames;i++){check();long time=Timeline.frameTime(i);while(shot<scenes.length()-1&&time>=scenes.getJSONObject(shot).getLong("endUs"))shot++;
     JSONObject s=scenes.getJSONObject(shot);long start=s.getLong("startUs"),end=s.getLong("endUs");
     gl.draw(painter.draw(s,time/1e6,(time-start)/(double)(end-start)),time*1000);d.pump(false);if(i%24==0)progress.update(i*100/frames,"1080p render · "+enc.getName());
    }
    enc.signalEndOfInputStream();d.pump(true);
   } finally{painter.frame.recycle();}
  } finally {if(gl!=null)gl.close();if(running)enc.stop();enc.release();if(surface!=null)surface.release();}
 }
 static void audio(File pcm,File out)throws Exception {
  MediaCodec enc=codec("audio/mp4a-latm");boolean running=false;
  try {
   MediaFormat f=MediaFormat.createAudioFormat("audio/mp4a-latm",24000,1);f.setInteger(MediaFormat.KEY_AAC_PROFILE,MediaCodecInfo.CodecProfileLevel.AACObjectLC);f.setInteger(MediaFormat.KEY_BIT_RATE,128000);f.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE,16384);enc.configure(f,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);enc.start();running=true;
   try(InputStream in=new FileInputStream(pcm);Drain d=new Drain(enc,out)){
    byte[] bytes=new byte[8192];long sent=0;boolean eof=false;
    while(!eof){check();int id=enc.dequeueInputBuffer(10000);if(id>=0){ByteBuffer b=enc.getInputBuffer(id);b.clear();int n=in.read(bytes,0,Math.min(bytes.length,b.remaining()));eof=n<0;if(n>0)b.put(bytes,0,n);enc.queueInputBuffer(id,0,Math.max(0,n),sent*1000000L/48000,eof?MediaCodec.BUFFER_FLAG_END_OF_STREAM:0);if(n>0)sent+=n;}d.pump(false);}
    d.pump(true);
   }
  }finally{if(running)enc.stop();enc.release();}
 }
 static void mux(File video,File audio,File out)throws Exception {
  MediaMuxer m=new MediaMuxer(out.toString(),MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);MediaExtractor v=new MediaExtractor(),a=new MediaExtractor();boolean started=false;
  try{v.setDataSource(video.toString());a.setDataSource(audio.toString());int vt=m.addTrack(v.getTrackFormat(0)),at=m.addTrack(a.getTrackFormat(0));m.start();started=true;copy(v,m,vt);copy(a,m,at);}finally{if(started)m.stop();m.release();v.release();a.release();}
 }
 static void copy(MediaExtractor e,MediaMuxer m,int track)throws Exception {e.selectTrack(0);ByteBuffer b=ByteBuffer.allocate(8*1024*1024);MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();while(true){check();b.clear();int n=e.readSampleData(b,0);if(n<0)break;info.set(0,n,e.getSampleTime(),(e.getSampleFlags() & MediaExtractor.SAMPLE_FLAG_SYNC)!=0 ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0);m.writeSampleData(track,b,info);e.advance();}}
 static final class Gl implements AutoCloseable {
  EGLDisplay display;EGLContext context;EGLSurface window;int program,texture;FloatBuffer vertices;
  Gl(Surface surface){
   display=EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY);int[] ver=new int[2];if(!EGL14.eglInitialize(display,ver,0,ver,1))throw new IllegalStateException("EGL init failed");
   EGLConfig[] configs=new EGLConfig[1];int[] n=new int[1];EGL14.eglChooseConfig(display,new int[]{EGL14.EGL_RED_SIZE,8,EGL14.EGL_GREEN_SIZE,8,EGL14.EGL_BLUE_SIZE,8,EGL14.EGL_RENDERABLE_TYPE,4,0x3142,1,EGL14.EGL_NONE},0,configs,0,1,n,0);
   if(n[0]==0)throw new IllegalStateException("No recordable EGL config");context=EGL14.eglCreateContext(display,configs[0],EGL14.EGL_NO_CONTEXT,new int[]{EGL14.EGL_CONTEXT_CLIENT_VERSION,2,EGL14.EGL_NONE},0);
   window=EGL14.eglCreateWindowSurface(display,configs[0],surface,new int[]{EGL14.EGL_NONE},0);if(!EGL14.eglMakeCurrent(display,window,window,context))throw new IllegalStateException("EGL context failed");
   program=GLES20.glCreateProgram();GLES20.glAttachShader(program,shader(35633,"attribute vec2 p; attribute vec2 t; varying vec2 uv; void main(){gl_Position=vec4(p,0.,1.);uv=t;}"));GLES20.glAttachShader(program,shader(35632,"precision mediump float; varying vec2 uv; uniform sampler2D image; void main(){gl_FragColor=texture2D(image,uv);}"));GLES20.glLinkProgram(program);
   int[] ok=new int[1];GLES20.glGetProgramiv(program,GLES20.GL_LINK_STATUS,ok,0);if(ok[0]==0)throw new IllegalStateException(GLES20.glGetProgramInfoLog(program));
   vertices=ByteBuffer.allocateDirect(64).order(ByteOrder.nativeOrder()).asFloatBuffer();vertices.put(new float[]{-1,-1,0,1,1,-1,1,1,-1,1,0,0,1,1,1,0}).position(0);int[] tex=new int[1];GLES20.glGenTextures(1,tex,0);texture=tex[0];GLES20.glBindTexture(3553,texture);GLES20.glTexParameteri(3553,10241,9729);GLES20.glTexParameteri(3553,10240,9729);GLES20.glTexParameteri(3553,10242,33071);GLES20.glTexParameteri(3553,10243,33071);
  }
  static int shader(int type,String source){int s=GLES20.glCreateShader(type);GLES20.glShaderSource(s,source);GLES20.glCompileShader(s);int[] ok=new int[1];GLES20.glGetShaderiv(s,GLES20.GL_COMPILE_STATUS,ok,0);if(ok[0]==0)throw new IllegalStateException(GLES20.glGetShaderInfoLog(s));return s;}
  void draw(android.graphics.Bitmap bitmap,long ns){GLES20.glViewport(0,0,1920,1080);GLES20.glUseProgram(program);GLES20.glBindTexture(3553,texture);GLUtils.texImage2D(3553,0,bitmap,0);int p=GLES20.glGetAttribLocation(program,"p"),t=GLES20.glGetAttribLocation(program,"t");vertices.position(0);GLES20.glVertexAttribPointer(p,2,5126,false,16,vertices);GLES20.glEnableVertexAttribArray(p);vertices.position(2);GLES20.glVertexAttribPointer(t,2,5126,false,16,vertices);GLES20.glEnableVertexAttribArray(t);GLES20.glDrawArrays(5,0,4);EGLExt.eglPresentationTimeANDROID(display,window,ns);if(!EGL14.eglSwapBuffers(display,window))throw new IllegalStateException("EGL frame failed");}
  public void close(){EGL14.eglMakeCurrent(display,EGL14.EGL_NO_SURFACE,EGL14.EGL_NO_SURFACE,EGL14.EGL_NO_CONTEXT);EGL14.eglDestroySurface(display,window);EGL14.eglDestroyContext(display,context);EGL14.eglTerminate(display);}
 }
}
