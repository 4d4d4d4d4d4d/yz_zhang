import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;
import org.json.*;

/** Authenticated field encryption: SQLite never receives plaintext private values. */
final class Vault {
    interface DeviceBinding {byte[] bind(byte[] derived)throws Exception;}
    static DeviceBinding deviceBinding;
    private final SQLiteDatabase db;
    private byte[] key, indexKey;
    private static final int ROUNDS = 600000;
    private static final SecureRandom RNG = new SecureRandom();
    Vault(File file) throws Exception {
        File dir = file.getParentFile(); dir.mkdirs();
        dir.setReadable(false, false); dir.setWritable(false, false); dir.setExecutable(false, false);
        dir.setReadable(true, true); dir.setWritable(true, true); dir.setExecutable(true, true);
        db = SQLiteDatabase.openOrCreateDatabase(file, null);
        try (Cursor c=db.rawQuery("PRAGMA journal_mode=DELETE",null)) { c.moveToFirst(); }
        db.execSQL("PRAGMA temp_store=MEMORY");
        try (Cursor c=db.rawQuery("PRAGMA secure_delete=ON",null)) { c.moveToFirst(); }
        db.execSQL("CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY, salt BLOB NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL)");
        file.setReadable(false, false); file.setWritable(false, false);
        file.setReadable(true, true); file.setWritable(true, true);
    }
    synchronized boolean initialized() { try(Cursor c=db.rawQuery("SELECT id FROM meta",null)){return c.moveToFirst();} }
    synchronized boolean unlocked() {return key!=null;}
    synchronized void unlock(char[] pass, boolean create) throws Exception {
        byte[] oldKey=key,oldIndex=indexKey; boolean success=false;
        byte[] salt = new byte[16]; boolean exists = initialized();
        if (exists && create) throw new IllegalStateException("资料库已存在，请解锁");
        if (!exists && !create) throw new IllegalStateException("请先创建资料库");
        if(pass.length<12 || pass.length>256) throw new IllegalArgumentException("口令需要 12–256 个字符");
        if(exists){try(Cursor c=db.rawQuery("SELECT salt FROM meta WHERE id=1",null)){c.moveToFirst();salt=c.getBlob(0);}}
        else RNG.nextBytes(salt);
        PBEKeySpec spec=new PBEKeySpec(pass,salt,ROUNDS,512); byte[] derived=null;
        try {
            derived=SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            if(deviceBinding!=null){byte[] bound=deviceBinding.bind(derived);Arrays.fill(derived,(byte)0);derived=bound;}
            key=Arrays.copyOfRange(derived,0,32); indexKey=Arrays.copyOfRange(derived,32,64);
            if(exists){if(!"phone-vault-v1".equals(get("verifier")))throw new GeneralSecurityException("Bad verifier");}
            else {db.beginTransaction();try{db.execSQL("INSERT INTO meta(id,salt) VALUES(1,?)",new Object[]{salt});put("verifier","phone-vault-v1");db.setTransactionSuccessful();}finally{db.endTransaction();}}
            success=true;
        } catch(Exception e){lock();key=oldKey;indexKey=oldIndex;throw new GeneralSecurityException("口令错误或资料库完整性校验失败",e);}
        finally {if(success){if(oldKey!=null)Arrays.fill(oldKey,(byte)0);if(oldIndex!=null)Arrays.fill(oldIndex,(byte)0);}spec.clearPassword();Arrays.fill(pass,'\0');if(derived!=null)Arrays.fill(derived,(byte)0);}
    }
    synchronized void lock(){if(key!=null)Arrays.fill(key,(byte)0);if(indexKey!=null)Arrays.fill(indexKey,(byte)0);key=null;indexKey=null;}
    private String id(String name)throws Exception{
        if(key==null)throw new SecurityException("资料库已锁定");
        Mac mac=Mac.getInstance("HmacSHA256");mac.init(new SecretKeySpec(indexKey,"HmacSHA256"));
        return Base64.getEncoder().encodeToString(mac.doFinal(name.getBytes(StandardCharsets.UTF_8)));
    }
    synchronized String get(String name)throws Exception{
        String id=id(name);
        try(Cursor c=db.rawQuery("SELECT nonce,ciphertext FROM records WHERE id=?",new String[]{id})){
            if(!c.moveToFirst())return null;
            Cipher aes=Cipher.getInstance("AES/GCM/NoPadding");aes.init(Cipher.DECRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,c.getBlob(0)));
            aes.updateAAD(("phone-vault-v1:"+id).getBytes(StandardCharsets.UTF_8));
            byte[] clear=aes.doFinal(c.getBlob(1));try{return new String(clear,StandardCharsets.UTF_8);}finally{Arrays.fill(clear,(byte)0);}
        }
    }
    synchronized void put(String name,String value)throws Exception{
        String id=id(name);byte[] nonce=new byte[12];RNG.nextBytes(nonce);
        Cipher aes=Cipher.getInstance("AES/GCM/NoPadding");aes.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,nonce));
        aes.updateAAD(("phone-vault-v1:"+id).getBytes(StandardCharsets.UTF_8));byte[] clear=value.getBytes(StandardCharsets.UTF_8);
        try{db.execSQL("INSERT OR REPLACE INTO records(id,nonce,ciphertext) VALUES(?,?,?)",new Object[]{id,nonce,aes.doFinal(clear)});}finally{Arrays.fill(clear,(byte)0);}
    }
    synchronized void delete(String name)throws Exception{db.execSQL("DELETE FROM records WHERE id=?",new Object[]{id(name)});}
    synchronized void close(){lock();db.close();}
    static void selfTest()throws Exception{
        File f=new File("/data/local/tmp/qwen-phone/vault-test/isolated.db");f.delete();Vault v=new Vault(f);
        String secret="PRIVATE_MARKER_"+UUID.randomUUID(), pass=UUID.randomUUID().toString();
        v.unlock(pass.toCharArray(),true);v.put("profile",secret);
        if(!secret.equals(v.get("profile")))throw new AssertionError("roundtrip");
        try{v.unlock("wrong-password-123".toCharArray(),false);throw new AssertionError("wrong reauthentication accepted");}catch(GeneralSecurityException expected){}
        if(!secret.equals(v.get("profile")))throw new AssertionError("bad login destroyed active key");
        v.unlock(pass.toCharArray(),false);if(!secret.equals(v.get("profile")))throw new AssertionError("reauthentication");
        v.close();v=new Vault(f);
        try{v.unlock("wrong-password-123".toCharArray(),false);throw new AssertionError("wrong key accepted");}catch(GeneralSecurityException expected){}
        v.unlock(pass.toCharArray(),false);if(!secret.equals(v.get("profile")))throw new AssertionError("reopen");
        try(InputStream in=new FileInputStream(f)){if(PhoneAgent.readAll(in,1024*1024).contains(secret))throw new AssertionError("plaintext on disk");}
        v.db.execSQL("UPDATE records SET ciphertext=zeroblob(length(ciphertext)) WHERE id=?",new Object[]{v.id("profile")});
        try{v.get("profile");throw new AssertionError("tamper accepted");}catch(GeneralSecurityException expected){}
        v.close();f.delete();System.out.println("VAULT_OK: roundtrip, reopen, wrong-password, plaintext-scan, tamper");
    }
}
