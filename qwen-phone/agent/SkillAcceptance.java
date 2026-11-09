import java.io.*;import java.util.*;import org.json.*;
public final class SkillAcceptance {
 public static void main(String[] args)throws Exception{File dir=new File(PhoneAgent.ROOT+"skill-acceptance");dir.mkdirs();File f=new File(dir,"isolated.db");f.delete();Vault v=new Vault(f);PhoneAgent.vault=v;JSONArray results=new JSONArray();
 try{v.unlock(UUID.randomUUID().toString().toCharArray(),true);PhoneAgent.lastUse=System.currentTimeMillis();
  String[] skills={"travel","message"};String[] prompts={"帮我安排西山岛攻略和订票。出发地、日期、人数和预算还没确定，请先向我核实这些条件，本轮不联网不下单。","这是测试，请拟一条发给微信文件传输助手的消息，正文是「本地助手消息能力测试，请忽略。」。任务要求：只生成草稿，不发送，不联网。"};
  for(int i=(args.length>0&&args[0].equals("message")?1:0);i<skills.length;i++){PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("session",UUID.randomUUID().toString()).put("skill",skills[i]).put("prompt",prompts[i]),PhoneAgent.epoch);PhoneAgent.run(j);results.put(new JSONObject().put("skill",skills[i]).put("result",j.snapshot()));try(FileOutputStream out=new FileOutputStream(new File(dir,"results.json"))){out.write(results.toString(2).getBytes("UTF-8"));}System.out.println(skills[i]+" "+j.snapshot());}
 }finally{v.close();f.delete();PhoneAgent.HTTP.shutdownNow();PhoneAgent.WORK.shutdownNow();PhoneAgent.READS.shutdownNow();}System.exit(0);}
}
