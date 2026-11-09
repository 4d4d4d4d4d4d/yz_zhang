import java.io.*;import java.util.*;import org.json.*;
public final class VisionTest {
 public static void main(String[] args)throws Exception{
  byte[] bytes;try(InputStream in=new FileInputStream(PhoneAgent.ROOT+"vision-fixture.png")){ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);bytes=out.toByteArray();}
  String data="data:image/png;base64,"+Base64.getEncoder().encodeToString(bytes);Vision.validate(data);
  for(String invalid:new String[]{"https://example.com/private.png","data:image/svg+xml;base64,AA==","data:image/png;base64,AA=="})try{Vision.validate(invalid);throw new AssertionError("bad image accepted");}catch(IllegalArgumentException expected){}
  File f=new File(PhoneAgent.ROOT+"vision-test/isolated.db");f.delete();Vault v=new Vault(f);PhoneAgent.vault=v;PhoneAgent.visionEnabled=true;
  try{v.unlock(UUID.randomUUID().toString().toCharArray(),true);PhoneAgent.lastUse=System.currentTimeMillis();String sid=UUID.randomUUID().toString();PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("session",sid).put("prompt","图片底部两个按钮分别写了什么？哪个在左，哪个在右？只按图片回答。").put("image_data",data),PhoneAgent.epoch);PhoneAgent.run(j);JSONObject r=j.snapshot();if(!r.getString("status").equals("done"))throw new AssertionError(r.toString());String answer=r.getJSONObject("result").getString("answer");if(!answer.toUpperCase(Locale.ROOT).contains("SAVE")||!answer.toUpperCase(Locale.ROOT).contains("CANCEL"))throw new AssertionError("visual labels not recognized: "+answer);if(j.input.has("image_data"))throw new AssertionError("image retained in job");String saved=v.get("session:"+sid);if(saved.contains("base64,")||saved.contains(data.substring(30,100)))throw new AssertionError("image saved in history");if(r.getJSONObject("result").getJSONArray("tools").length()!=0)throw new AssertionError("vision tool execution");System.out.println("VISION_TEST_OK "+r.getJSONObject("result").toString());
   PhoneAgent.Job cancelled=new PhoneAgent.Job(new JSONObject().put("session",sid).put("prompt","test").put("image_data",data),PhoneAgent.epoch);cancelled.cancelled=true;PhoneAgent.run(cancelled);if(!cancelled.status.equals("cancelled")||cancelled.input.has("image_data"))throw new AssertionError("cancel cleanup");
  }finally{v.close();f.delete();PhoneAgent.HTTP.shutdownNow();PhoneAgent.WORK.shutdownNow();PhoneAgent.READS.shutdownNow();}
  System.exit(0);
 }
}
