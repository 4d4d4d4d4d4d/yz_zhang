package org.qwen.local;
import android.app.KeyguardManager;
import android.content.*;
import android.graphics.Rect;
import android.os.*;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

/** Opt-in query-only adapter. Nodes are read on demand, kept in RAM, never logged. */
final class AppQueryBridge implements PhoneAgent.UiDriver {
 private final ScreenCaptureService service;
 private final Handler main=new Handler(Looper.getMainLooper());
 private long until;
 private String mode="travel",targetPackage=QueryPolicy.PACKAGE;
 public synchronized String scope(){return TaskScope.description(mode);}
 private int grant;
 private String owner="",snapshot="",fingerprint="";
 private final ArrayList<AccessibilityNodeInfo> nodes=new ArrayList<>();
 private String screen="";
 AppQueryBridge(ScreenCaptureService service){this.service=service;}
 synchronized void arm(){arm("travel");}
 synchronized void arm(String selected){targetPackage=TaskScope.packageName(selected);mode=selected;clear();owner="";until=SystemClock.elapsedRealtime()+10*60*1000;final int ticket=++grant;main.postDelayed(()->{synchronized(this){if(ticket==grant)stop();}},10*60*1000);}
 public synchronized boolean available(){return until>SystemClock.elapsedRealtime();}
 public synchronized void stop(){grant++;until=0;owner="";clear();}
 public synchronized void finish(String job){if(owner.equals(job)){stop();main.post(()->{
  AccessibilityNodeInfo r=service.getRootInActiveWindow();boolean target=r!=null&&targetPackage.contentEquals(r.getPackageName()==null?"":r.getPackageName());if(r!=null)r.recycle();
  if(target)service.startActivity(new Intent(service,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP));
 });}}
 private void clear(){for(AccessibilityNodeInfo n:nodes)n.recycle();nodes.clear();snapshot="";fingerprint="";screen="";}
 private synchronized void check(PhoneAgent.Job job){
  job.check();if(!available())throw new SecurityException("请在小千顶部开启应用查询，本次授权已结束");
  if(((KeyguardManager)service.getSystemService(Context.KEYGUARD_SERVICE)).isKeyguardLocked())throw new SecurityException("系统已锁屏，停止应用操作");
  if(owner.isEmpty())owner=job.id;else if(!owner.equals(job.id))throw new SecurityException("应用查询授权已绑定其他任务");
 }
 private <T>T ui(Callable<T> action)throws Exception{
  FutureTask<T> f=new FutureTask<>(action);main.post(f);
  try{return f.get(8,TimeUnit.SECONDS);}catch(TimeoutException e){f.cancel(false);throw new IllegalStateException("界面操作超时，请重新读取页面");}
 }
 public JSONObject call(JSONObject args,PhoneAgent.Job job)throws Exception{
  String op=args.getString("op");
  JSONObject result=ui(()->execute(op,args,job));
  if(!op.equals("read")){
   int attempts=op.equals("launch")?30:1;
   for(int i=0;i<attempts;i++){
    Thread.sleep(1500);job.check();
    try{result.put("screen",ui(()->execute("read",new JSONObject(),job)));break;}
    catch(Exception e){if(i==attempts-1){Throwable cause=e instanceof ExecutionException&&e.getCause()!=null?e.getCause():e;result.put("screen_error",cause.getClass().getSimpleName()+": "+cause.getMessage()).put("hint","启动请求不等于启动成功；尚未观察到目标页面，可以read重试，不得猜测权限原因。");}}
   }
  }
  return result;
 }
 private AccessibilityNodeInfo root(){
  if(Build.VERSION.SDK_INT>=33)service.clearCache();
  AccessibilityNodeInfo r=service.getRootInActiveWindow();
  if(r==null)throw new IllegalStateException("没有可读取的界面，请稍后重试");
  if(!targetPackage.contentEquals(r.getPackageName()==null?"":r.getPackageName())){r.recycle();throw new SecurityException("当前不是本次授权应用："+targetPackage);}
  return r;
 }
 private void collect(AccessibilityNodeInfo n,List<AccessibilityNodeInfo> out,int depth,int[] visited){
  if(depth>24||++visited[0]>500||out.size()>=60)return;
  if(n.isVisibleToUser()&&!n.isPassword()&&(n.getText()!=null||n.getContentDescription()!=null||n.isEditable()))out.add(AccessibilityNodeInfo.obtain(n));
  for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null){try{collect(c,out,depth+1,visited);}finally{c.recycle();}}}
 }
 private String label(AccessibilityNodeInfo n){String t=n.getText()==null?"":n.getText().toString();if(t.isEmpty()&&n.getContentDescription()!=null)t=n.getContentDescription().toString();return t.length()>120?t.substring(0,120):t;}
 private String signature(List<AccessibilityNodeInfo> list){StringBuilder b=new StringBuilder();Rect r=new Rect();for(AccessibilityNodeInfo n:list){n.getBoundsInScreen(r);b.append(n.getWindowId()).append('|').append(label(n)).append('|').append(r).append('|').append(n.isEnabled()).append('|').append(n.getClassName()).append('|').append(n.getViewIdResourceName()).append('|').append(n.isEditable()).append('|').append(n.isClickable()).append(';');}return b.toString();}
 private JSONObject read()throws Exception{
  AccessibilityNodeInfo r=root();ArrayList<AccessibilityNodeInfo> next=new ArrayList<>();try{collect(r,next,0,new int[]{0});}finally{r.recycle();}
  clear();nodes.addAll(next);fingerprint=signature(nodes);snapshot=UUID.randomUUID().toString().substring(0,8);
  JSONArray items=new JSONArray();StringBuilder all=new StringBuilder();int bytes=0;
  for(int i=0;i<nodes.size();i++){
   AccessibilityNodeInfo n=nodes.get(i);String text=label(n);all.append(text).append('\n');
   if(bytes+text.length()>1800)continue;bytes+=text.length();
   items.put(new JSONObject().put("id",snapshot+":"+i).put("text",text).put("editable",n.isEditable()).put("enabled",n.isEnabled()));
  }
  screen=all.toString();return new JSONObject().put("package",targetPackage).put("nodes",items).put("scope",scope()).put("self_chat",mode.equals("telegram")&&selfChat());
 }
 private boolean selfChat(){
  if(!mode.equals("telegram"))return false;
  AccessibilityNodeInfo root=root();ArrayList<AccessibilityNodeInfo> current=new ArrayList<>();
  try{collect(root,current,0,new int[]{0});Rect bounds=new Rect();
   for(AccessibilityNodeInfo n:current){n.getBoundsInScreen(bounds);String title=label(n);
    if(!n.isEditable()&&bounds.top<450&&(title.equals("Saved Messages")||title.equals("收藏夹")||title.startsWith("Saved Messages\n")))return true;
   }return false;
  }finally{root.recycle();for(AccessibilityNodeInfo n:current)n.recycle();}
 }
 private AccessibilityNodeInfo target(String id){
  if(snapshot.isEmpty()||!id.startsWith(snapshot+":"))throw new SecurityException("控件引用已过期，先读取当前界面");
  int index;try{index=Integer.parseInt(id.substring(id.indexOf(':')+1));}catch(Exception e){throw new IllegalArgumentException("无效控件编号");}
  if(index<0||index>=nodes.size())throw new IllegalArgumentException("控件不存在");
  AccessibilityNodeInfo r=root();ArrayList<AccessibilityNodeInfo> now=new ArrayList<>();
  try{
   collect(r,now,0,new int[]{0});AccessibilityNodeInfo expected=nodes.get(index);boolean found=false;
   String before=signature(Collections.singletonList(expected));
   for(AccessibilityNodeInfo candidate:now)if(candidate.equals(expected)&&before.equals(signature(Collections.singletonList(candidate)))){found=true;break;}
   if(!found)throw new SecurityException("目标控件已经变化或被遮挡，先重新读取，未执行操作");
  }
  finally{r.recycle();for(AccessibilityNodeInfo n:now)n.recycle();}
  AccessibilityNodeInfo n=nodes.get(index);if(!n.refresh()||!n.isVisibleToUser()||!n.isEnabled()||n.isPassword())throw new SecurityException("控件不可操作");return n;
 }
 private synchronized JSONObject execute(String op,JSONObject args,PhoneAgent.Job job)throws Exception{
  check(job);
  if(op.equals("read"))return read();
  if(op.equals("launch")){
   Intent intent=service.getPackageManager().getLaunchIntentForPackage(targetPackage);
   if(intent==null&&mode.equals("travel"))intent=new Intent().setClassName(targetPackage,"ctrip.business.splash.CtripSplashActivity");
   if(intent==null)throw new IllegalStateException("尚未安装或无法启动："+targetPackage);
   service.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));clear();return new JSONObject().put("launch_requested",targetPackage);
  }
  if(op.equals("back")){AccessibilityNodeInfo r=root();r.recycle();boolean ok=service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);clear();return new JSONObject().put("action_dispatched",ok);}
  if(!op.equals("click")&&!op.equals("type")&&!op.equals("send"))throw new IllegalArgumentException("仅支持launch/read/click/type/back");
  AccessibilityNodeInfo n=target(args.getString("node"));String text=label(n);boolean ok;
  if(op.equals("type")){
   String value=args.getString("text");boolean allowed=mode.equals("travel")?QueryPolicy.cityInput(text,screen,value):mode.equals("food")?TaskScope.foodInput(text,value):selfChat()&&value.equals(TaskScope.TEST_MESSAGE)&&(text.isEmpty()||text.equals("Message")||text.equals("消息")||text.equals(value));
   if(!n.isEditable()||!allowed)throw new SecurityException("输入内容或控件不符合本次任务范围");
   Bundle b=new Bundle();b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);ok=n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,b);
  }else{
   if(op.equals("send")){
    if(!mode.equals("telegram")||!selfChat()||!TaskScope.sendLabel(text))throw new SecurityException("仅允许收藏夹中的测试消息发送");
    boolean exact=false;for(AccessibilityNodeInfo item:nodes)if(item.refresh()&&item.isVisibleToUser()&&!item.isPassword()&&item.isEditable()&&TaskScope.TEST_MESSAGE.equals(label(item)))exact=true;
    if(!exact)throw new SecurityException("发送前正文不匹配，未发送");
   }else if(!TaskScope.navigation(mode,text,screen,selfChat()))throw new SecurityException("此控件不在本次导航范围，未点击："+text);
   AccessibilityNodeInfo clickable=AccessibilityNodeInfo.obtain(n);
   try{for(int i=0;i<3&&!clickable.isClickable();i++){AccessibilityNodeInfo parent=clickable.getParent();if(parent==null)break;clickable.recycle();clickable=parent;}if(op.equals("send")){
     if(!clickable.isClickable())throw new IllegalStateException("发送控件不可点击");
     synchronized(PhoneAgent.STATE){job.check();if(PhoneAgent.vault.get("agent:telegram-self-test")!=null)throw new SecurityException("已尝试发送过此测试消息，先核验记录，禁止重复发送");PhoneAgent.vault.put("agent:telegram-self-test","attempted:"+System.currentTimeMillis());}
    }
    ok=clickable.isClickable()&&clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK);}finally{clickable.recycle();}
  }
  clear();return new JSONObject().put("action_dispatched",ok).put("op",op).put("target",text).put("delivery_status",op.equals("send")?"unverified":"not_applicable").put("note","必须以操作后界面核验结果，不代表业务成功");
 }
}
