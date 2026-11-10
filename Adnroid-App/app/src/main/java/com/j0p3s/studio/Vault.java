package com.j0p3s.studio;
import android.content.Context;
import android.security.keystore.*;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

final class Vault {
 static javax.crypto.SecretKey key() throws Exception {
  KeyStore s=KeyStore.getInstance("AndroidKeyStore"); s.load(null);
  if(!s.containsAlias("studio")) {
   KeyGenerator g=KeyGenerator.getInstance("AES","AndroidKeyStore");
   g.init(new KeyGenParameterSpec.Builder("studio",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());g.generateKey();
  }
  return (javax.crypto.SecretKey)s.getKey("studio",null);
 }
 static void save(Context c,String value) throws Exception {
  Cipher x=Cipher.getInstance("AES/GCM/NoPadding");x.init(Cipher.ENCRYPT_MODE,key());
  c.getSharedPreferences("vault",0).edit().putString("iv",Base64.encodeToString(x.getIV(),2))
   .putString("data",Base64.encodeToString(x.doFinal(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)),2)).commit();
 }
 static String load(Context c) throws Exception {
  var p=c.getSharedPreferences("vault",0); if(!p.contains("data"))return "{}";
  Cipher x=Cipher.getInstance("AES/GCM/NoPadding");x.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(p.getString("iv",""),2)));
  return new String(x.doFinal(Base64.decode(p.getString("data",""),2)),java.nio.charset.StandardCharsets.UTF_8);
 }
}
