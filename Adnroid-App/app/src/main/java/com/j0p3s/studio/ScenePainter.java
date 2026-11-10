package com.j0p3s.studio;
import android.graphics.*;
import org.json.*;

final class ScenePainter {
 final Paint p=new Paint(3); final Bitmap frame=Bitmap.createBitmap(1920,1080,Bitmap.Config.ARGB_8888);
 final Canvas c=new Canvas(frame);
 void line(float x,float y,float xx,float yy,int color,float width){p.setColor(color);p.setStrokeWidth(width);p.setStrokeCap(Paint.Cap.ROUND);c.drawLine(x,y,xx,yy,p);}
 void rect(float x,float y,float xx,float yy,int col){p.setColor(col);c.drawRect(x,y,xx,yy,p);}
 void text(String t,float x,float y,int size,int color){p.setTextSize(size);p.setColor(color);p.setTypeface(Typeface.create("sans-serif-medium",Typeface.BOLD));c.drawText(t,x,y,p);}
 Bitmap draw(JSONObject scene,double seconds,double progress) {
  c.drawColor(Color.rgb(8,17,28));int mint=Color.rgb(100,245,185),ink=Color.rgb(5,9,18);
  String set=scene.optString("setting","desk");
  c.save();float zoom=(float)(1+.025*Math.sin(progress*Math.PI));c.scale(zoom,zoom,960,540);
  if(set.equals("space")){for(int i=0;i<100;i++){p.setColor(Color.rgb(75+i%100,130,160));c.drawCircle(i*137%1920,i*89%850,2+i%3,p);}p.setColor(0xff536caf);c.drawCircle(1400,330,170,p);}
  else if(set.equals("diagram")){for(int x=0;x<1920;x+=80)line(x,0,x,1080,0xff173044,1);for(int y=0;y<1080;y+=80)line(0,y,1920,y,0xff173044,1);}
  else {rect(150,170,760,680,0xff244357);for(int i=0;i<12;i++){int h=150+(i*71%220);rect(160+i*48,680-h,200+i*48,680,0xff0b2030);}line(455,170,455,680,0xff071017,15);line(150,400,760,400,0xff071017,15);}
  rect(0,850,1920,1080,0xff12242e);
  if(set.equals("desk")){rect(650,690,1690,720,0xff315557);rect(700,720,735,950,ink);rect(1600,720,1635,950,ink);p.setColor(mint);c.drawCircle(1460,450,45,p);line(1460,495,1460,690,mint,9);}
  float bob=(float)Math.sin(seconds*2)*8,x=550+(float)Math.sin(progress*Math.PI)*140,y=550+bob;
  line(x,y+70,x,y+220,mint,30);line(x,y+70,x,y+220,ink,22);
  line(x,y+215,x-60,y+340,ink,19);line(x,y+215,x+60,y+340,ink,19);
  line(x,y+115,x-65,y+180,mint,20);line(x,y+115,x+100,y+65+(float)Math.sin(seconds*3)*25,mint,20);
  p.setColor(mint);c.drawCircle(x,y,63,p);p.setColor(ink);c.drawCircle(x,y,56,p);p.setColor(Color.WHITE);c.drawCircle(x-17,y-6,6,p);c.drawCircle(x+17,y-6,6,p);line(x-14,y+20,x+14,y+20,Color.WHITE,4);
  String prop=scene.optString("prop","book");float px=1120,py=590;
  if(prop.equals("clock")){p.setColor(mint);c.drawCircle(px,py,110,p);p.setColor(ink);c.drawCircle(px,py,100,p);double angle=seconds*Math.PI/3;line(px,py,px+(float)Math.sin(angle)*65,py-(float)Math.cos(angle)*65,mint,10);}
  else if(prop.equals("phone")){rect(1030,420,1180,675,0xff0b0e14);rect(1042,438,1168,645,mint);}
  else if(prop.equals("steps")){for(int i=0;i<5;i++)rect(900+i*95,750-i*75,995+i*95,850,mint);}
  else {rect(900,535,1320,690,mint);rect(910,545,1102,680,0xfff6f0c9);rect(1118,545,1310,680,0xfff6f0c9);for(int i=0;i<7;i++){line(930,565+i*14,1080,565+i*14,0xff7b826b,3);line(1135,565+i*14,1290,565+i*14,0xff7b826b,3);}}
  c.restore();String heading=scene.optString("caption").toUpperCase(java.util.Locale.US);text(heading.length()>45?heading.substring(0,45):heading,100,110,48,mint);
  // Sentence-level captions are exactly the narration associated with this audio segment.
  rect(60,900,1860,1050,0xe607101c);String[] words=scene.optString("narration").split("\\s+");String row="";int yy=950;
  p.setTextSize(30);for(String w:words){if(p.measureText(row+w)>1720){text(row,90,yy,30,Color.WHITE);yy+=39;row="";}if(yy>1030)break;row+=w+" ";}if(yy<=1030)text(row,90,yy,30,Color.WHITE);
  return frame;
 }
}
