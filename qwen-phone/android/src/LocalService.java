package org.qwen.local;
import android.app.*;import android.content.*;import android.os.*;import android.security.keystore.*;import java.io.*;import java.net.*;import java.security.*;import java.util.*;import javax.crypto.*;
public final class LocalService extends Service {
 static volatile boolean ready=false;static volatile String state="未启动",boot="";private java.lang.Process model;
 public IBinder onBind(Intent i){return null;}
 public int onStartCommand(Intent intent,int flags,int id){if(intent!=null&&"stop".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}if(!state.equals("未启动"))return START_NOT_STICKY;
  NotificationManager nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("local","本地推理",NotificationManager.IMPORTANCE_LOW));
  PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE);
  PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,LocalService.class).setAction("stop"),PendingIntent.FLAG_IMMUTABLE);
  startForeground(1,new Notification.Builder(this,"local").setSmallIcon(android.R.drawable.ic_lock_lock).setContentTitle("小千本地助手").setContentText("模型在本机运行 · 点击停止可结束服务").setContentIntent(open).addAction(new Notification.Action.Builder(null,"停止",stop).build()).build());state="正在加载本地模型…";new Thread(()->startLocal(),"local-start").start();return START_NOT_STICKY;
 }
 void startLocal(){try{
  File root=getFilesDir();PhoneAgent.ROOT=root.getAbsolutePath()+"/";PhoneAgent.agentPort=8092;PhoneAgent.modelPort=8082;boot=UUID.randomUUID().toString()+UUID.randomUUID();PhoneAgent.appKey=boot;
  DeviceKeys.install(this);
  try(InputStream in=getAssets().open("index.html");OutputStream out=new FileOutputStream(new File(root,"index.html"))){copy(in,out);}
  File modelFile=new File(root,"model.gguf");if(!modelFile.exists())throw new IOException("请先导入 Qwen3.5-4B Q4_0 模型");
  File keyFile=new File(root,"inference.key");try(FileOutputStream out=new FileOutputStream(keyFile)){out.write((UUID.randomUUID().toString()+UUID.randomUUID()).getBytes("UTF-8"));}
  String lib=getApplicationInfo().nativeLibraryDir;
  // CPU first: app sandbox access to vendor DSP must be tested independently of shell access.
  ProcessBuilder pb=new ProcessBuilder(lib+"/libqwen-server.so","-m",modelFile.getPath(),"--alias","qwen3.5-4b","--host","127.0.0.1","--port","8082","--api-key-file",keyFile.getPath(),"-c","4096","--parallel","1","-b","256","-ub","64","-t","5","-tb","5","--device","none","-ngl","0","--fit","off","--jinja","--reasoning","auto","--reasoning-budget","128","--slots","--cache-ram","0","--no-context-shift","-fa","on","--log-disable");
  File projector=new File(root,"mmproj.gguf");PhoneAgent.visionEnabled=projector.exists();if(PhoneAgent.visionEnabled)pb.command().addAll(Arrays.asList("--mmproj",projector.getPath(),"--no-mmproj-offload","--image-max-tokens","1024"));
  pb.environment().put("LD_LIBRARY_PATH",lib);pb.environment().put("LD_PRELOAD",lib+"/libqwen-lifecycle.so");pb.environment().put("QWEN_PARENT_PID",String.valueOf(android.os.Process.myPid()));pb.redirectErrorStream(true);model=pb.start();java.lang.Process current=model;
  new Thread(()->{try(InputStream in=current.getInputStream()){byte[] b=new byte[4096];while(in.read(b)!=-1){} }catch(Exception ignored){}},"model-output-drain").start();
  boolean loaded=false;for(int i=0;i<150;i++){if(!current.isAlive())throw new IOException("模型进程启动失败（退出码"+current.exitValue()+"）");try{HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8082/health").openConnection();c.setConnectTimeout(500);c.setReadTimeout(500);try{loaded=c.getResponseCode()==200;}finally{c.disconnect();}if(loaded)break;}catch(IOException ignored){}Thread.sleep(1000);}
  if(!loaded)throw new IOException("模型加载超时");
  new Thread(()->{try{PhoneAgent.main(new String[0]);}catch(Exception e){state="助手服务退出，请停止后重开";ready=false;}},"agent-http").start();
  boolean agentReady=false;for(int i=0;i<30;i++){try{HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8092/health").openConnection();c.setRequestProperty("X-App-Key",boot);c.setConnectTimeout(500);c.setReadTimeout(500);try{if(c.getResponseCode()==200){agentReady=true;break;}}finally{c.disconnect();}}catch(IOException ignored){}Thread.sleep(200);}
  if(!agentReady)throw new IOException("助手服务启动超时");
  ready=true;state=PhoneAgent.visionEnabled?"就绪 · 本地文字与图片":"就绪 · CPU 本地推理";int exit=current.waitFor();ready=false;state="模型进程已退出（"+exit+"），请停止后重开";if(PhoneAgent.vault!=null)PhoneAgent.lock();
 }catch(Exception e){state="启动失败："+e.getMessage();ready=false;if(model!=null)model.destroy();}}
 static void copy(InputStream in,OutputStream out)throws IOException{byte[] b=new byte[1024*1024];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}
 @Override public void onDestroy(){ready=false;if(PhoneAgent.vault!=null)PhoneAgent.lock();if(model!=null)model.destroy();super.onDestroy();android.os.Process.killProcess(android.os.Process.myPid());}
}
