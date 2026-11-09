"""Exercise the actual stale-target check with a minimal Android node double."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'android/src/AppQueryBridge.java').read_text()
sig=s[s.index(' private String signature('):s.index(' private JSONObject read(')]
target=s[s.index(' private AccessibilityNodeInfo target('):s.index(' private synchronized JSONObject execute(')]
code='''import java.util.*;
public class QueryTargetTest {
 static class Rect {int x; public String toString(){return "x="+x;}}
 static class AccessibilityNodeInfo {
  int id,x;String text;boolean visible=true,enabled=true,password=false;
  AccessibilityNodeInfo(int id,String text,int x){this.id=id;this.text=text;this.x=x;}
  public boolean equals(Object o){return o instanceof AccessibilityNodeInfo&&id==((AccessibilityNodeInfo)o).id;}
  void getBoundsInScreen(Rect r){r.x=x;}int getWindowId(){return 1;}
  boolean isEnabled(){return enabled;}String getClassName(){return "Button";}
  String getViewIdResourceName(){return "button";}boolean isEditable(){return false;}
  boolean isClickable(){return true;}void recycle(){}boolean refresh(){return true;}
  boolean isVisibleToUser(){return visible;}boolean isPassword(){return password;}
 }
 String snapshot="snap";ArrayList<AccessibilityNodeInfo> nodes=new ArrayList<>(),current=new ArrayList<>();
 AccessibilityNodeInfo root(){return new AccessibilityNodeInfo(0,"root",0);}
 void collect(AccessibilityNodeInfo r,List<AccessibilityNodeInfo> out,int d,int[] v){out.addAll(current);}
 String label(AccessibilityNodeInfo n){return n.text;}
'''+sig+target+'''
 static void denied(Runnable r){try{r.run();throw new AssertionError("accepted stale target");}catch(SecurityException expected){}}
 public static void main(String[] args){
  QueryTargetTest t=new QueryTargetTest();t.nodes.add(new AccessibilityNodeInfo(1,"机票",100));t.nodes.add(new AccessibilityNodeInfo(2,"旧广告",200));
  t.current.add(new AccessibilityNodeInfo(1,"机票",100));t.current.add(new AccessibilityNodeInfo(2,"新广告",200));
  if(t.target("snap:0")!=t.nodes.get(0))throw new AssertionError();
  t.current.get(0).x=110;denied(()->t.target("snap:0"));t.current.get(0).x=100;
  t.current.get(0).text="付款";denied(()->t.target("snap:0"));t.current.get(0).text="机票";
  t.current.get(0).id=3;denied(()->t.target("snap:0"));t.current.get(0).id=1;
  t.current.get(0).enabled=false;denied(()->t.target("snap:0"));t.current.get(0).enabled=true;
  t.nodes.get(0).password=true;denied(()->t.target("snap:0"));t.nodes.get(0).password=false;
  denied(()->t.target("old:0"));t.current.clear();denied(()->t.target("snap:0"));
  System.out.println("QUERY_TARGET_OK: unrelated changes allowed; moved/replaced/disabled/missing/password/stale targets denied");
 }
}'''
j=Path('/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin')
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'QueryTargetTest.java';p.write_text(code)
 subprocess.run([str(j/'javac'),str(p)],check=True)
 subprocess.run([str(j/'java'),'-cp',d,'QueryTargetTest'],check=True)
