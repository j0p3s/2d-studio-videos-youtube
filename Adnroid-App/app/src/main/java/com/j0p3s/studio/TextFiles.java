package com.j0p3s.studio;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
final class TextFiles {
 static String read(Path p)throws java.io.IOException{return new String(Files.readAllBytes(p),StandardCharsets.UTF_8);}
 static void write(Path p,String value)throws java.io.IOException{Files.write(p,value.getBytes(StandardCharsets.UTF_8));}
}
