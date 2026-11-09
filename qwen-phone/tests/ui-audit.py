"""Actual receipt storage code: bound size, job isolation, privacy and cancelled writes."""
from pathlib import Path
import tempfile,subprocess
r=Path(__file__).resolve().parents[1];s=(r/'agent/PhoneAgent.java').read_text()
method=s[s.index('    static void recordUiStep('):s.index('    static String clean(')]
j=Path('/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin');jar=r/'tools/json.jar'
code='''import org.json.*;import java.util.*;
public class UiAuditTest {
 static final Object STATE=new Object();static Store vault=new Store();
 static class Store {Map<String,String> data=new HashMap<>();String get(String k){return data.get(k);}void put(String k,String v){data.put(k,v);}}
 static class Job {String id;boolean cancelled;Job(String s){id=s;}void check(){if(cancelled)throw new SecurityException();}}
'''+method+'''
 static void ok(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] a)throws Exception {
 Job one=new Job("first");JSONObject receipt=new JSONObject().put("action_dispatched",false).put("screen",new JSONObject().put("package","me.ele").put("nodes",new JSONArray().put("PRIVATE_ADDRESS"))).put("text","PRIVATE_MESSAGE");
 for(int i=0;i<40;i++)recordUiStep(one,"click","returned",receipt);
 String stored=vault.get("agent:last-ui-audit");JSONObject saved=new JSONObject(stored);ok(saved.getJSONArray("steps").length()==32);ok(!stored.contains("PRIVATE_"));ok(!saved.getJSONArray("steps").getJSONObject(0).getBoolean("action_dispatched"));
 Job second=new Job("second");recordUiStep(second,"send","started",null);ok(new JSONObject(vault.get("agent:last-ui-audit")).getJSONArray("steps").length()==1);
 String before=vault.get("agent:last-ui-audit");second.cancelled=true;try{recordUiStep(second,"send","returned",receipt);throw new AssertionError();}catch(SecurityException expected){}ok(before.equals(vault.get("agent:last-ui-audit")));
 System.out.println("UI_AUDIT_OK: bounded receipts; no screen/body stored; per-job isolation; cancellation enforced");
 }}'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'UiAuditTest.java';p.write_text(code)
 subprocess.run([str(j/'javac'),'-cp',str(jar),str(p)],check=True)
 subprocess.run([str(j/'java'),'-cp',str(jar)+':'+d,'UiAuditTest'],check=True)
