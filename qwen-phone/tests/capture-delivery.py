"""Exercise real delivery methods with a deterministic clock and desktop Base64."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'android/src/ScreenCaptureService.java').read_text()
methods=s[s.index(' static synchronized void clear()'):s.index(' private void notifyResult()')]
methods=methods.replace('SystemClock.elapsedRealtime()','now').replace('android.util.Base64.encodeToString(pending,android.util.Base64.NO_WRAP)','java.util.Base64.getEncoder().encodeToString(pending)')
code='''import java.util.Arrays;
public class CaptureDeliveryTest {
 static byte[] pending;static long expires,now;static int generation;static String state;
'''+methods+'''
 static void check(boolean ok){if(!ok)throw new AssertionError();}
 static void capture(){clear();pending=new byte[]{1,2,3};expires=now+60000;}
 public static void main(String[] args){
  capture();byte[] original=pending;Delivery first=prepare();check(first!=null&&pending==original);
  acknowledge(first.ticket,false);check(pending==original);check(prepare()!=null);
  acknowledge(first.ticket,true);check(pending==null);check(Arrays.equals(original,new byte[3]));
  capture();Delivery old=prepare();capture();byte[] newer=pending;acknowledge(old.ticket,true);check(pending==newer);
  Delivery current=prepare();now=expires+1;acknowledge(current.ticket,false);check(pending==null);
  capture();byte[] expired=pending;now=expires+1;check(prepare()==null);check(Arrays.equals(expired,new byte[3]));
  check(prepare()==null);System.out.println("CAPTURE_DELIVERY_OK: retry, accepted cleanup, stale callback, expiry");
 }
}
'''
java=Path('/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin')
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'CaptureDeliveryTest.java';p.write_text(code)
 subprocess.run([str(java/'javac'),str(p)],check=True)
 subprocess.run([str(java/'java'),'-cp',d,'CaptureDeliveryTest'],check=True)
