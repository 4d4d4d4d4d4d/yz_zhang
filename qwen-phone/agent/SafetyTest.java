import java.io.*;import java.util.*;import java.util.concurrent.*;import org.json.*;
public final class SafetyTest {
 static void ok(boolean b,String s){if(!b)throw new AssertionError(s);}
 static JSONObject awaitApproval(PhoneAgent.Job j)throws Exception{for(int i=0;i<100;i++){synchronized(j){if(j.approval!=null)return new JSONObject(j.approval.toString());}Thread.sleep(10);}throw new AssertionError("approval missing");}
 public static void main(String[] args)throws Exception{
  File f=new File(PhoneAgent.ROOT+"safety-test/isolated.db");f.delete();Vault v=new Vault(f);PhoneAgent.vault=v;ExecutorService pool=Executors.newSingleThreadExecutor();String sid=UUID.randomUUID().toString();
  try{v.unlock(UUID.randomUUID().toString().toCharArray(),true);PhoneAgent.token="synthetic";PhoneAgent.lastUse=System.currentTimeMillis();
   for(boolean allow:new boolean[]{false,true}){
    PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("session",sid).put("skill","assistant"),PhoneAgent.epoch);PhoneAgent.jobs.put(j.id,j);
    Future<JSONObject> pending=pool.submit(()->PhoneAgent.localTool("write_note",new JSONObject().put("name","safe").put("content","MARKER-ALLOW-927"),j));
    JSONObject a=awaitApproval(j);ok(a.getString("kind").equals("write_note"),"write approval type");ok(v.get("note:safe")==null,"no write before consent");
    PhoneAgent.route("POST","/jobs/"+j.id+"/approve",new JSONObject().put("id",a.getString("id")).put("allow",allow),"synthetic");pending.get(5,TimeUnit.SECONDS);
    ok((v.get("note:safe")!=null)==allow,"allow/deny enforced");
    try{PhoneAgent.route("POST","/jobs/"+j.id+"/approve",new JSONObject().put("id",a.getString("id")).put("allow",true),"synthetic");throw new AssertionError("replay accepted");}catch(IllegalArgumentException expected){}
   }
   PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("session",sid),PhoneAgent.epoch);PhoneAgent.jobs.put(j.id,j);
   Future<JSONObject> pending=pool.submit(()->PhoneAgent.localTool("write_note",new JSONObject().put("name","safe").put("content","SHOULD-NOT-OVERWRITE"),j));
   ok(awaitApproval(j).getBoolean("overwrite"),"overwrite warning");PhoneAgent.route("POST","/jobs/"+j.id+"/cancel",new JSONObject(),"synthetic");
   try{pending.get(5,TimeUnit.SECONDS);throw new AssertionError("cancel not enforced");}catch(ExecutionException expected){ok(expected.getCause() instanceof SecurityException,"cancel security");}
   ok(v.get("note:safe").equals("MARKER-ALLOW-927"),"cancel preserved old note");
   PhoneAgent.Job off=new PhoneAgent.Job(new JSONObject().put("skill","offline"),PhoneAgent.epoch);
   try{PhoneAgent.localTool("web_search",new JSONObject().put("query","public"),off);throw new AssertionError("offline network allowed");}catch(SecurityException expected){}
   PhoneAgent.Job messageJob=new PhoneAgent.Job(new JSONObject().put("skill","message"),PhoneAgent.epoch);
   try{PhoneAgent.localTool("web_search",new JSONObject().put("query","public"),messageJob);throw new AssertionError("message skill network allowed");}catch(SecurityException expected){}
   try{PhoneAgent.route("POST","/sessions/read",new JSONObject().put("session",sid),"wrong");throw new AssertionError("history unauthenticated");}catch(SecurityException expected){}
   ok(PhoneAgent.route("POST","/sessions/read",new JSONObject().put("session",sid),"synthetic").getJSONArray("history").length()==0,"empty history");
   PhoneAgent.jobs.clear();j.status="cancelled";PhoneAgent.jobs.put(j.id,j);
   ok(j.terminal(),"cancelled is terminal");
   ok(PhoneAgent.route("POST","/sessions/delete",new JSONObject().put("session",sid),"synthetic").getBoolean("deleted"),"cancelled task permits session deletion");
   System.out.println("SAFETY_TEST_OK: approval denial/allow, pre-consent write prevention, replay rejection, overwrite display, cancel, offline executor gate, history auth");
  }finally{pool.shutdownNow();v.close();f.delete();PhoneAgent.HTTP.shutdownNow();PhoneAgent.WORK.shutdownNow();PhoneAgent.READS.shutdownNow();}
 }
}
