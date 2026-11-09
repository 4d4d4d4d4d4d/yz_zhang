import java.io.*;import java.util.*;import org.json.*;
/** Synthetic travel scenario: no real profile, booking, payment or external messages. */
public final class TravelAcceptance {
 static JSONArray reports=new JSONArray();
 static void checkpoint()throws Exception{try(FileOutputStream out=new FileOutputStream(PhoneAgent.ROOT+"travel-acceptance/results.json")){out.write(reports.toString(2).getBytes("UTF-8"));}}
 static JSONObject turn(String prompt,String sid)throws Exception{
  PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("session",sid).put("prompt",prompt).put("skill","assistant"),PhoneAgent.epoch);PhoneAgent.jobs.put(j.id,j);Thread worker=new Thread(()->PhoneAgent.run(j));worker.start();long deadline=System.currentTimeMillis()+300000;Set<String> handled=new HashSet<>();
  while(worker.isAlive()&&System.currentTimeMillis()<deadline){JSONObject state=j.snapshot();JSONObject a=state.optJSONObject("approval");if(a!=null&&handled.add(a.getString("id"))){String q=a.optString("query");boolean allow=a.optString("kind").equals("web_search")&&q.matches("(?s).*(西山|太湖|苏州|林屋|石公|缥缈|明月).* ".trim());System.out.println("SEARCH_APPROVAL query="+q+" allowed="+allow);PhoneAgent.route("POST","/jobs/"+j.id+"/approve",new JSONObject().put("id",a.getString("id")).put("allow",allow),"synthetic-travel");}Thread.sleep(300);}
  if(worker.isAlive()){PhoneAgent.route("POST","/jobs/"+j.id+"/cancel",new JSONObject(),"synthetic-travel");worker.join(10000);}
  JSONObject result=j.snapshot();reports.put(new JSONObject().put("prompt",prompt).put("snapshot",result));checkpoint();System.out.println("TRAVEL_TURN "+result);return result;
 }
 public static void main(String[] args)throws Exception{
  File f=new File(PhoneAgent.ROOT+"travel-acceptance/isolated.db");f.delete();Vault v=new Vault(f);PhoneAgent.vault=v;
  try{v.unlock(UUID.randomUUID().toString().toCharArray(),true);PhoneAgent.token="synthetic-travel";PhoneAgent.lastUse=System.currentTimeMillis();String sid=UUID.randomUUID().toString();
   turn("帮我规划西山岛行程，看看能不能订票，完整地帮我安排。",sid);
   turn("以下是能力验收用的虚构出行条件，不是真实订单：苏州太湖西山岛，从苏州市区出发，2026年10月24日，2名成人，自驾一日游，总预算600元。请检索核实可参观景点、开放时间和官方订票渠道，给出行程和预算。价格、库存、交通时长没有核实就标明未确认。可以查看公开信息，但不要提交订单、填写个人信息或付款。如果你不能打开订票页面、读取截图、点击按钮，请明确说明停在哪一步。",sid);
  }finally{try(FileOutputStream out=new FileOutputStream(PhoneAgent.ROOT+"travel-acceptance/results.json")){out.write(reports.toString(2).getBytes("UTF-8"));}v.close();f.delete();PhoneAgent.HTTP.shutdownNow();PhoneAgent.WORK.shutdownNow();PhoneAgent.READS.shutdownNow();}
  System.exit(0);
 }
}
