package com.j0p3s.studio;

public final class Timeline {
 public static final int WIDTH=1920, HEIGHT=1080, FPS=24;
 public static final long MAX_US=600_000_000L;
 public static long pcmDuration(long bytes) { return bytes*1_000_000L/48000; }
 public static int frames(long us) {
  if(us<=0 || us>MAX_US) throw new IllegalArgumentException("Audio must be between 0 and 600 seconds");
  return (int)((us*FPS+999999)/1000000);
 }
 public static long frameTime(int index) { return index*1_000_000L/FPS; }
}
