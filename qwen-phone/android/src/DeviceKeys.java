package org.qwen.local;
import android.content.Context;import android.security.keystore.*;import java.io.*;import java.security.*;import java.util.*;import javax.crypto.*;
final class DeviceKeys {
 static boolean install(Context context)throws Exception{
  KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);String alias="qwen-vault-binding-v1";
  if(!ks.containsAlias(alias)){if(new File(context.getFilesDir(),"private/vault.db").exists())throw new SecurityException("设备密钥丢失，请勿覆盖原资料库");KeyGenerator kg=KeyGenerator.getInstance("HmacSHA256","AndroidKeyStore");kg.init(new KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_SIGN).setDigests(KeyProperties.DIGEST_SHA256).build());kg.generateKey();}
  SecretKey key=(SecretKey)ks.getKey(alias,null);KeyInfo info=(KeyInfo)SecretKeyFactory.getInstance(key.getAlgorithm(),"AndroidKeyStore").getKeySpec(key,KeyInfo.class);
  Vault.deviceBinding=derived->{byte[] out=new byte[64];for(int i=0;i<2;i++){Mac m=Mac.getInstance("HmacSHA256");m.init(key);m.update((byte)i);System.arraycopy(m.doFinal(derived),0,out,i*32,32);}return out;};return info.isInsideSecureHardware();
 }
}
