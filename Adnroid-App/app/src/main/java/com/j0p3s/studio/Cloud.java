package com.j0p3s.studio;
import org.json.*;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

final class Cloud {
 static byte[] post(String url,Map<String,String> headers,byte[] body) throws Exception {
  if(Thread.currentThread().isInterrupted())throw new InterruptedException();
  HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();
  try {
   c.setConnectTimeout(30000);c.setReadTimeout(180000);c.setRequestMethod("POST");c.setDoOutput(true);
   c.setRequestProperty("Content-Type","application/json");for(var h:headers.entrySet())c.setRequestProperty(h.getKey(),h.getValue());
   try(var o=c.getOutputStream()){o.write(body);}
   int status=c.getResponseCode();
   if(status<200||status>=300)throw new IOException("Service HTTP "+status+". Check credentials, model, region and quota.");
   try(var in=c.getInputStream()){return in.readAllBytes();}
  } finally {c.disconnect();}
 }
 static JSONObject plan(JSONObject cfg,String topic,int minutes) throws Exception {
  String model=cfg.getString("model").trim();if(!model.matches("[a-zA-Z0-9._:/-]+"))throw new IOException("Enter a valid model ID");
  String prompt="Create an English-only narrated educational animation about: "+topic+
   ". Target "+minutes+" minutes, no more than "+(minutes*125)+" spoken words. Return ONLY JSON: {\"title\":\"English title\",\"language\":\"en\",\"scenes\":[{\"narration\":\"English spoken words, 10-30 words per scene\",\"caption\":\"short English heading\",\"setting\":\"desk|city|space|diagram\",\"prop\":\"book|phone|clock|steps\",\"mood\":\"calm|hopeful|tense\"}]}. Maximum 100 scenes. Varied literal visuals, clear opening and ending. No unsupported statistics. No Markdown.";
  JSONObject body;String url,reply;Map<String,String> headers=new HashMap<>();String provider=cfg.getString("provider"),key=cfg.getString("apiKey");
  if(key.isBlank()||model.isBlank())throw new IOException("Configure provider API key and model");
  if(provider.equals("Gemini")) {
   url="https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent";headers.put("x-goog-api-key",key);
   body=new JSONObject().put("contents",new JSONArray().put(new JSONObject().put("parts",new JSONArray().put(new JSONObject().put("text",prompt)))))
    .put("generationConfig",new JSONObject().put("responseMimeType","application/json"));
   JSONObject r=new JSONObject(new String(post(url,headers,body.toString().getBytes(StandardCharsets.UTF_8)),StandardCharsets.UTF_8));
   reply=r.getJSONArray("candidates").getJSONObject(0).getJSONObject("content").getJSONArray("parts").getJSONObject(0).getString("text");
  } else {
   body=new JSONObject().put("model",model).put("messages",new JSONArray().put(new JSONObject().put("role","user").put("content",prompt)));
   if(provider.equals("Claude")){url="https://api.anthropic.com/v1/messages";headers.put("x-api-key",key);headers.put("anthropic-version","2023-06-01");body.put("max_tokens",12000);}
   else {url="https://api.openai.com/v1/chat/completions";headers.put("Authorization","Bearer "+key);body.put("response_format",new JSONObject().put("type","json_object"));}
   JSONObject r=new JSONObject(new String(post(url,headers,body.toString().getBytes(StandardCharsets.UTF_8)),StandardCharsets.UTF_8));
   reply=provider.equals("Claude")?r.getJSONArray("content").getJSONObject(0).getString("text"):r.getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content");
  }
  reply=reply.trim();if(reply.startsWith("```")){reply=reply.substring(reply.indexOf('\n')+1,reply.lastIndexOf("```"));}
  JSONObject p=new JSONObject(reply);validate(p);return p;
 }
 static void validate(JSONObject p)throws Exception {
  if(!p.getString("language").equals("en"))throw new IOException("Plan language must be en");
  JSONArray a=p.getJSONArray("scenes");if(a.length()<1||a.length()>100)throw new IOException("Use 1–100 scenes");
  int words=0;for(int i=0;i<a.length();i++){
   JSONObject s=a.getJSONObject(i);String n=s.getString("narration").trim();if(n.isEmpty()||n.length()>1200)throw new IOException("Scene narration empty or too long");
   int count=n.split("\\s+").length;if(count>36)throw new IOException("Split narration into scenes of at most 36 words");words+=count;if(s.getString("caption").length()>100)throw new IOException("Caption too long");
  }
  if(words>1500)throw new IOException("Plan exceeds 1500 words / ten-minute budget");
 }
 static byte[] speech(JSONObject cfg,String text)throws Exception {
  String region=cfg.getString("region").trim();if(!region.matches("[a-z0-9]+"))throw new IOException("Invalid Azure region");
  String escaped=text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;");
  String ssml="<speak version='1.0' xml:lang='en-US'><voice name='en-US-AndrewMultilingualNeural'>"+escaped+"</voice></speak>";
  return post("https://"+region+".tts.speech.microsoft.com/cognitiveservices/v1",
   Map.of("Content-Type","application/ssml+xml","Ocp-Apim-Subscription-Key",cfg.getString("speechKey"),"X-Microsoft-OutputFormat","raw-24khz-16bit-mono-pcm","User-Agent","StudioAndroid"),ssml.getBytes(StandardCharsets.UTF_8));
 }
}
