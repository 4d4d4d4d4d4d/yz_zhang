import java.io.*;
public final class LifecycleTest {
 public static void main(String[] args)throws Exception{
  ProcessBuilder b=new ProcessBuilder("/system/bin/sh","-c","echo $$; exec /system/bin/sleep 120");b.environment().put("LD_PRELOAD",PhoneAgent.ROOT+"libqwen-lifecycle.so");b.environment().put("QWEN_PARENT_PID",String.valueOf(android.os.Process.myPid()));Process child=b.start();String pid=new BufferedReader(new InputStreamReader(child.getInputStream())).readLine();Thread.sleep(600);if(!child.isAlive())throw new AssertionError("child died while parent alive");System.out.println("LIFECYCLE_CHILD_PID="+pid);System.out.flush();System.exit(0);
 }
}
