from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];j=Path('/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin')
with tempfile.TemporaryDirectory() as d:
 d=Path(d)
 for n in ['TaskScope','QueryPolicy']:(d/(n+'.java')).write_text((r/'android/src'/(n+'.java')).read_text())
 (d/'ScopeTest.java').write_text('''package org.qwen.local;
 public class ScopeTest {
 static void ok(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] a){
 ok(TaskScope.packageName("telegram").equals("org.telegram.messenger"));
 try{TaskScope.packageName("any.package");throw new AssertionError();}catch(IllegalArgumentException e){}
 ok(TaskScope.navigation("telegram","Saved Messages","",false));
 ok(!TaskScope.navigation("telegram","Alice","",false));
 ok(!TaskScope.navigation("telegram","Send","",true));
 ok(!TaskScope.navigation("telegram","More options","",true));
 ok(TaskScope.sendLabel("Send"));ok(!TaskScope.sendLabel("Forward and Send"));
 for(String label:new String[]{"提交订单","付款","确认支付","立即购买","发送"})ok(!TaskScope.navigation("food",label,"",false));
 ok(TaskScope.foodInput("搜索商家", "面条"));ok(!TaskScope.foodInput("手机号","12345"));
 ok(TaskScope.navigation("travel","查 询","",false));
 System.out.println("TASK_SCOPE_OK: native package allowlist, self navigation, send separation, checkout blocked");
 }}''')
 subprocess.run([str(j/'javac'),'-d',str(d),*[str(x) for x in d.glob('*.java')]],check=True)
 subprocess.run([str(j/'java'),'-cp',str(d),'org.qwen.local.ScopeTest'],check=True)
