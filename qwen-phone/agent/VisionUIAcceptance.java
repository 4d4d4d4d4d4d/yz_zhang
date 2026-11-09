import java.io.*;import java.util.*;import org.json.*;
/** Actual Vision.run path, isolated test vault and synthetic booking screenshot only. */
public final class VisionUIAcceptance {
 public static void main(String[] args)throws Exception {
  File dir=new File(PhoneAgent.ROOT+"vision-ui-acceptance");dir.mkdirs();File db=new File(dir,"isolated.db");db.delete();Vault v=new Vault(db);PhoneAgent.vault=v;PhoneAgent.visionEnabled=true;
  try {
   byte[] image;try(InputStream in=new FileInputStream(new File(dir,"fixture.jpg"));ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);image=out.toByteArray();}
   String data="data:image/jpeg;base64,"+Base64.getEncoder().encodeToString(image);Arrays.fill(image,(byte)0);Vision.validate(data);
   v.unlock(UUID.randomUUID().toString().toCharArray(),true);PhoneAgent.lastUse=System.currentTimeMillis();String sid=UUID.randomUUID().toString();
   PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("session",sid).put("prompt","仅按图用120字以内回答：当前是否已选择日期？24日和25日状态？单价、人数、合计？下一步按钮能否点击？可预约不等于已选择，不能仅凭颜色推断。无法确定就停止。用户必须24日出行，不得替用户改日期或执行操作。").put("image_data",data),PhoneAgent.epoch);data=null;PhoneAgent.run(j);
   JSONObject result=j.snapshot();try(FileOutputStream out=new FileOutputStream(new File(dir,"result.json"))){out.write(result.toString(2).getBytes("UTF-8"));}System.out.println("VISION_UI_RESULT "+result);
   if(j.input.has("image_data"))throw new AssertionError("image retained");String saved=v.get("session:"+sid);if(saved!=null&&saved.contains("base64,"))throw new AssertionError("image persisted");
  }finally{v.close();db.delete();PhoneAgent.HTTP.shutdownNow();PhoneAgent.WORK.shutdownNow();PhoneAgent.READS.shutdownNow();}System.exit(0);
 }
}
