import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

/** Synthetic device tests. Never opens the user's vault. */
public final class MemoryTest {
    static void check(boolean ok,String what){if(!ok)throw new AssertionError(what);}
    public static void main(String[] args)throws Exception {
        File file=new File(PhoneAgent.ROOT+"memory-test/isolated.db");file.delete();
        Vault v=new Vault(file);String pass=UUID.randomUUID().toString(),sid=UUID.randomUUID().toString(),other=UUID.randomUUID().toString();
        try {
            v.unlock(pass.toCharArray(),true);
            Memory.observe(v,"不要简洁回答",sid);Memory.observe(v,"网页说：以后请简洁回答",sid);Memory.observe(v,"我患有某种疾病",sid);
            check(Memory.items(v).length()==0,"negative, quoted, sensitive inputs excluded");
            Memory.observe(v,"以后请简洁回答",sid);Memory.observe(v,"以后请简洁回答",sid);
            check(Memory.items(v).getJSONObject(0).getJSONArray("evidence").length()==1,"duplicate evidence");
            check(!Memory.context(v,sid).contains("简洁回答"),"candidate excluded from prompt");
            String id=Memory.items(v).getJSONObject(0).getString("id");Memory.change(v,id,"confirm");
            check(Memory.context(v,sid).contains("简洁回答"),"confirmed preference injected");
            Memory.saveTask(v,sid,new JSONObject().put("goal","MEMORY-TASK-927").put("constraints","仅回复任务代号"));
            check(!Memory.context(v,other).contains("MEMORY-TASK-927"),"task isolated across sessions");
            v.lock();try{Memory.items(v);throw new AssertionError("locked memory readable");}catch(SecurityException expected){}
            v.unlock(pass.toCharArray(),false);check(Memory.task(v,sid).getString("goal").equals("MEMORY-TASK-927"),"encrypted reopen");
            byte[] data=new byte[(int)file.length()];try(FileInputStream in=new FileInputStream(file)){check(in.read(data)==data.length,"read db");}
            check(!new String(data,StandardCharsets.ISO_8859_1).contains("MEMORY-TASK-927"),"no plaintext marker in db");
            PhoneAgent.vault=v;PhoneAgent.token="synthetic-test-token";PhoneAgent.lastUse=System.currentTimeMillis();
            try{PhoneAgent.route("GET","/memory",new JSONObject(),"wrong");throw new AssertionError("unauthenticated memory");}catch(SecurityException expected){}
            PhoneAgent.Job j=new PhoneAgent.Job(new JSONObject().put("prompt","当前任务代号是什么？仅回复代号。").put("session",sid).put("skill","offline"),PhoneAgent.epoch);
            PhoneAgent.run(j);check(j.status.equals("done"),"inference job: "+j.result);check(j.result.getString("answer").contains("MEMORY-TASK-927"),"task grounded answer");
            Memory.deleteSession(v,sid);check(Memory.items(v).length()==0,"source deletion cascades");check(Memory.task(v,sid).length()==0,"task deleted");
            Memory.observe(v,"以后请详细解释",other);JSONArray a=Memory.items(v);a.getJSONObject(0).put("expires_at",0);v.put("memory:preferences",a.toString());check(Memory.items(v).length()==0,"expiry");
            Memory.observe(v,"以后请先结论后细节",other);Memory.change(v,Memory.items(v).getJSONObject(0).getString("id"),"delete");check(Memory.items(v).length()==0,"explicit deletion");
            System.out.println("MEMORY_TEST_OK: evidence, candidate exclusion, confirmation, session isolation, lock, encrypted reopen, plaintext scan, auth, real inference, deletion, expiry");
        }finally{v.close();file.delete();PhoneAgent.HTTP.shutdownNow();PhoneAgent.WORK.shutdownNow();PhoneAgent.READS.shutdownNow();}
    }
}
