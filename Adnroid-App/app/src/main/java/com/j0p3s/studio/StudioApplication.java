package com.j0p3s.studio;
public class StudioApplication extends android.app.Application {
 public void onCreate(){super.onCreate();Diagnostics.initialize(this);}
}
