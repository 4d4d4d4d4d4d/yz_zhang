package org.qwen.local;
import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;
import android.view.Display;
import android.graphics.Bitmap;
import android.os.*;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;
/** User-triggered, one-shot capture. No event content, gestures or background collection. */
public final class ScreenCaptureService extends AccessibilityService {
 static volatile ScreenCaptureService instance;static volatile String state="未启用截屏服务";
 private static byte[] pending;private static long expires;private static int generation;
 AppQueryBridge query;
 private final Handler handler=new Handler(Looper.getMainLooper());
 @Override protected void onServiceConnected(){instance=this;query=new AppQueryBridge(this);PhoneAgent.uiDriver=query;state="截屏服务就绪";}
 @Override public void onAccessibilityEvent(AccessibilityEvent event){}
 @Override public void onInterrupt(){if(query!=null)query.stop();clear();state="截屏已中止";}
 static synchronized void clear(){generation++;if(pending!=null)Arrays.fill(pending,(byte)0);pending=null;expires=0;}
 static final class Delivery {final int ticket;final String image;Delivery(int ticket,String image){this.ticket=ticket;this.image=image;}}
 static synchronized Delivery prepare(){if(pending==null){state="没有可用截图，请先截屏";return null;}if(SystemClock.elapsedRealtime()>expires){clear();state="截图已过期清除，请重新截屏";return null;}return new Delivery(generation,"data:image/jpeg;base64,"+android.util.Base64.encodeToString(pending,android.util.Base64.NO_WRAP));}
 static synchronized void acknowledge(int ticket,boolean accepted){if(ticket!=generation)return;if(accepted){clear();state="已附图，请检查预览并选择任务后发送";}else if(SystemClock.elapsedRealtime()>expires){clear();state="截图已过期清除，请重新截屏";}else state="页面尚未接收截图，请等待任务结束或解锁后重试";}
 private void notifyResult(){handler.post(()->android.widget.Toast.makeText(this,state,android.widget.Toast.LENGTH_LONG).show());}
 void captureOnce(){clear();final int ticket=generation;state="15秒后截取当前屏幕，请切到目标页面并保持静止";handler.postDelayed(()->{
  if(ticket!=generation)return;if(Build.VERSION.SDK_INT<30){state="截屏需要Android 11及以上";return;}
  try{takeScreenshot(Display.DEFAULT_DISPLAY,getMainExecutor(),new TakeScreenshotCallback(){
   public void onFailure(int code){if(ticket==generation){state="截图失败（"+code+"），请确认目标页面允许截图";notifyResult();}}
   public void onSuccess(ScreenshotResult shot){Bitmap hardware=null,copy=null,small=null;
    try{hardware=Bitmap.wrapHardwareBuffer(shot.getHardwareBuffer(),shot.getColorSpace());if(hardware==null)throw new IllegalStateException();copy=hardware.copy(Bitmap.Config.ARGB_8888,false);float scale=Math.min(1f,1280f/Math.max(copy.getWidth(),copy.getHeight()));small=Bitmap.createScaledBitmap(copy,Math.max(1,(int)(copy.getWidth()*scale)),Math.max(1,(int)(copy.getHeight()*scale)),true);ByteArrayOutputStream out=new ByteArrayOutputStream();small.compress(Bitmap.CompressFormat.JPEG,80,out);byte[] bytes=out.toByteArray();synchronized(ScreenCaptureService.class){if(ticket!=generation||bytes.length>1024*1024){Arrays.fill(bytes,(byte)0);if(ticket==generation)state="截图过大，请使用系统截图裁剪后导入";return;}pending=bytes;expires=SystemClock.elapsedRealtime()+60000;state="截图已就绪，60秒内返回小千解锁并点使用截屏";}notifyResult();handler.postDelayed(()->{synchronized(ScreenCaptureService.class){if(ticket==generation){clear();state="截图已过期清除";}}},60000);
    }catch(Exception e){if(ticket==generation)state="截图处理失败";}finally{if(small!=null&&small!=copy)small.recycle();if(copy!=null)copy.recycle();if(hardware!=null)hardware.recycle();shot.getHardwareBuffer().close();}
   }
  });}catch(RuntimeException e){if(ticket==generation)state="截屏权限不可用，请重新启用服务";}
 },15000);}
 @Override public void onDestroy(){if(query!=null){query.stop();if(PhoneAgent.uiDriver==query)PhoneAgent.uiDriver=null;}clear();instance=null;state="截屏服务已关闭";handler.removeCallbacksAndMessages(null);super.onDestroy();}
}
