package org.qwen.local;
import android.app.*;import android.os.*;import android.content.*;import android.view.*;import android.widget.*;import java.io.*;import java.net.*;import java.util.*;import org.json.*;
/** Debug builds only. All secrets and fixtures are synthetic; never initializes the user's vault. */
public final class BetaInstrumentation extends Instrumentation {
 private String mode="security";
 public static final class Foreground extends Activity {
  public void onCreate(Bundle b){super.onCreate(b);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_SECURE);TextView v=new TextView(this);v.setText("小千 · 工程自检\n\n只使用隔离测试数据\n测试期间请保持此页开启");v.setTextSize(20);v.setPadding(40,80,40,40);setContentView(v);}
 }
 public void onCreate(Bundle args){super.onCreate(args);if(args!=null)mode=args.getString("mode","security");start();}
 void progress(String text){Bundle b=new Bundle();b.putString("stream",text+"\n");sendStatus(1,b);}
 public void onStart(){Thread runner=Thread.currentThread();Timer watchdog=new Timer(true);watchdog.schedule(new TimerTask(){public void run(){StringBuilder s=new StringBuilder("TEST_WAIT ");for(StackTraceElement e:runner.getStackTrace())s.append(e.toString()).append("\n");progress(s.toString());}},30000,30000);Bundle out=new Bundle();Activity foreground=null;
  try{foreground=startActivitySync(new Intent(getTargetContext(),Foreground.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));progress("APK_TEST_START mode="+mode);
   PhoneAgent.ROOT=getTargetContext().getFilesDir().getAbsolutePath()+"/";
   if(mode.equals("model")){modelTest();out.putString("stream","APK_MODEL_OK: private UID text + vision, app HTTP key gate, user vault uninitialized\n");}
   else{boolean hardware=DeviceKeys.install(getTargetContext());progress("KEYSTORE_READY hardware="+hardware);SafetyTest.main(new String[0]);progress("SAFETY_COMPLETE");
    File f=new File(getTargetContext().getFilesDir(),"binding-test/vault.db");f.delete();Vault v=new Vault(f);String pass=UUID.randomUUID().toString();try{
     v.unlock(pass.toCharArray(),true);v.put("test","DEVICE-BOUND-927");v.lock();Vault.DeviceBinding binding=Vault.deviceBinding;Vault.deviceBinding=null;boolean rejected=false;
     try{v.unlock(pass.toCharArray(),false);}catch(Exception expected){rejected=true;}finally{Vault.deviceBinding=binding;}
     if(!rejected)throw new AssertionError("device binding bypass");v.unlock(pass.toCharArray(),false);if(!v.get("test").equals("DEVICE-BOUND-927"))throw new AssertionError("reopen");
    }finally{v.close();f.delete();}
    out.putString("stream","APK_SAFETY_OK uid="+android.os.Process.myUid()+" hardware_keystore="+hardware+"; consent/cancel/offline gates and device-bound encryption passed\n");
   }
   watchdog.cancel();if(foreground!=null){Activity f=foreground;runOnMainSync(()->f.finish());}finish(Activity.RESULT_OK,out);
  }catch(Throwable e){watchdog.cancel();out.putString("stream","APK_TEST_FAILED "+e+"\n");if(foreground!=null){Activity f=foreground;runOnMainSync(()->f.finish());}finish(Activity.RESULT_CANCELED,out);}
 }
 static String call(String url,JSONObject body,String header,String secret)throws Exception{
  HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setConnectTimeout(5000);c.setReadTimeout(240000);if(header!=null)c.setRequestProperty(header,secret);
  try{if(body!=null){c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");try(OutputStream out=c.getOutputStream()){out.write(body.toString().getBytes("UTF-8"));}}
   if(c.getResponseCode()!=200)throw new IOException("HTTP "+c.getResponseCode());try(InputStream in=c.getInputStream()){return PhoneAgent.readAll(in,1024*1024);}
  }finally{c.disconnect();}
 }
 void modelTest()throws Exception{
  getTargetContext().startForegroundService(new Intent(getTargetContext(),LocalService.class));long deadline=System.currentTimeMillis()+180000;
  while(!LocalService.ready&&System.currentTimeMillis()<deadline){if(LocalService.state.startsWith("启动失败"))throw new IOException(LocalService.state);Thread.sleep(500);}if(!LocalService.ready)throw new IOException("model readiness timeout");progress("MODEL_READY");
  JSONObject health=new JSONObject(call("http://127.0.0.1:8092/health",null,"X-App-Key",LocalService.boot));if(health.getBoolean("vault_initialized"))throw new AssertionError("formal vault must stay uninitialized");
  try{call("http://127.0.0.1:8092/health",null,null,null);throw new AssertionError("missing app key accepted");}catch(IOException expected){if(!expected.getMessage().equals("HTTP 403"))throw expected;}
  String key;try(InputStream in=new FileInputStream(new File(getTargetContext().getFilesDir(),"inference.key"))){key=PhoneAgent.readAll(in,512).trim();}
  JSONObject request=new JSONObject().put("model","qwen3.5-4b").put("messages",new JSONArray().put(PhoneAgent.message("user","只回复 LOCAL_OK"))).put("max_tokens",64).put("temperature",0).put("chat_template_kwargs",new JSONObject().put("enable_thinking",false));
  long started=System.currentTimeMillis();String text=new JSONObject(call("http://127.0.0.1:8082/v1/chat/completions",request,"Authorization","Bearer "+key)).getJSONArray("choices").getJSONObject(0).getJSONObject("message").optString("content");if(!text.contains("LOCAL_OK"))throw new AssertionError("text response mismatch");progress("TEXT_OK elapsed_ms="+(System.currentTimeMillis()-started));
  byte[] png;try(InputStream in=getTargetContext().getAssets().open("vision-fixture.png")){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);png=out.toByteArray();}
  request.put("messages",Vision.messages("底部左右按钮分别写着什么？", "data:image/png;base64,"+Base64.getEncoder().encodeToString(png))).put("max_tokens",160);started=System.currentTimeMillis();String answer=new JSONObject(call("http://127.0.0.1:8082/v1/chat/completions",request,"Authorization","Bearer "+key)).getJSONArray("choices").getJSONObject(0).getJSONObject("message").optString("content");if(!answer.toUpperCase(Locale.ROOT).contains("SAVE")||!answer.toUpperCase(Locale.ROOT).contains("CANCEL"))throw new AssertionError("vision label mismatch");progress("VISION_OK elapsed_ms="+(System.currentTimeMillis()-started));
 }
}
