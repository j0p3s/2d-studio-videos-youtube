package com.j0p3s.studio;
import org.junit.Test;
import org.json.*;
import static org.junit.Assert.*;
public class PlanTest {
 JSONObject plan(String language,String narration)throws Exception{return new JSONObject().put("language",language).put("scenes",new JSONArray().put(new JSONObject().put("narration",narration).put("caption","Start small")));}
 @Test public void acceptsEnglishScene()throws Exception{Cloud.validate(plan("en","Open the book. Read one paragraph. Then decide whether to continue."));}
 @Test public void rejectsOtherLanguage()throws Exception{try{Cloud.validate(plan("pt","Começa pequeno."));fail();}catch(java.io.IOException expected){assertTrue(expected.getMessage().contains("language"));}}
 @Test public void rejectsCaptionOverflow()throws Exception{try{Cloud.validate(plan("en","word ".repeat(40)));fail();}catch(java.io.IOException expected){assertTrue(expected.getMessage().contains("36 words"));}}
}
