import org.json.*;
import java.util.*;

/** Encrypted, bounded memory; callers hold PhoneAgent.STATE. No external index. */
final class Memory {
    static final long TTL=30L*24*60*60*1000;
    // Deliberately narrow: only explicit response-format wishes, never sensitive traits.
    static final String[][] RULES={
        {"简洁回答","^(?:我希望你|我喜欢你|我更喜欢你|以后请|请你以后)(?:的回答)?(?:简洁回答|简短回答|回答简洁|回答简短)[。！! ]*$"},
        {"详细解释","^(?:我希望你|我喜欢你|我更喜欢你|以后请|请你以后)(?:的回答)?(?:详细解释|详细回答)[。！! ]*$"},
        {"先结论后细节","^(?:我希望你|我喜欢你|我更喜欢你|以后请|请你以后)(?:的回答)?先结论后细节[。！! ]*$"},
        {"使用简体中文","^(?:我希望你|我喜欢你|我更喜欢你|以后请|请你以后)(?:的回答)?(?:使用简体中文|用简体中文回答)[。！! ]*$"}
    };
    static JSONArray items(Vault v)throws Exception {
        String raw=v.get("memory:preferences");JSONArray old=raw==null?new JSONArray():new JSONArray(raw),out=new JSONArray();long now=System.currentTimeMillis();
        for(int i=0;i<old.length();i++){JSONObject x=old.getJSONObject(i);if(x.optBoolean("confirmed")||x.getLong("expires_at")>now){x.put("confidence",x.optBoolean("confirmed")?"用户已确认":(x.getJSONArray("evidence").length()>1?"重复表达，仍需确认":"单次明确表达，仍需确认"));out.put(x);}}
        if(out.length()!=old.length())v.put("memory:preferences",out.toString());return out;
    }
    static void observe(Vault v,String prompt,String sid)throws Exception {
        String value=null;for(String[] r:RULES)if(prompt.trim().matches(r[1]))value=r[0];if(value==null)return;
        JSONArray a=items(v);JSONObject x=null;for(int i=0;i<a.length();i++)if(a.getJSONObject(i).getString("value").equals(value))x=a.getJSONObject(i);
        long now=System.currentTimeMillis();if(x==null){if(a.length()>=20)return;x=new JSONObject().put("id",UUID.randomUUID().toString()).put("value",value).put("confirmed",false).put("evidence",new JSONArray());a.put(x);}
        JSONArray e=x.getJSONArray("evidence");boolean duplicate=false;for(int i=0;i<e.length();i++)if(e.getJSONObject(i).getString("session").equals(sid)&&e.getJSONObject(i).getString("quote").equals(prompt))duplicate=true;
        if(!duplicate&&e.length()<3)e.put(new JSONObject().put("session",sid).put("quote",prompt).put("at",now));
        x.put("confidence",e.length()>1?"重复表达，仍需确认":"单次明确表达，仍需确认").put("expires_at",now+TTL);v.put("memory:preferences",a.toString());
    }
    static JSONArray change(Vault v,String id,String action)throws Exception {
        if(!action.equals("confirm")&&!action.equals("delete"))throw new IllegalArgumentException("memory action");
        JSONArray a=items(v),out=new JSONArray();boolean found=false;
        for(int i=0;i<a.length();i++){JSONObject x=a.getJSONObject(i);if(x.getString("id").equals(id)){found=true;if(action.equals("delete"))continue;x.put("confirmed",true);}out.put(x);}
        if(!found)throw new IllegalArgumentException("候选已过期或不存在");v.put("memory:preferences",out.toString());return out;
    }
    static JSONObject task(Vault v,String sid)throws Exception {String s=v.get("memory:task:"+sid);return s==null?new JSONObject():new JSONObject(s);}
    static void saveTask(Vault v,String sid,JSONObject input)throws Exception {
        JSONObject out=new JSONObject();for(String k:new String[]{"goal","constraints","next"}){Object val=input.opt(k);if(val!=null&&!(val instanceof String))throw new IllegalArgumentException("任务字段需为文本");String s=input.optString(k,"").trim();if(s.length()>240)throw new IllegalArgumentException("每个任务字段最多 240 字符");out.put(k,s);}v.put("memory:task:"+sid,out.toString());
    }
    static String context(Vault v,String sid)throws Exception {
        JSONArray confirmed=new JSONArray(),a=items(v);for(int i=0;i<a.length();i++)if(a.getJSONObject(i).optBoolean("confirmed"))confirmed.put(a.getJSONObject(i).getString("value"));
        return "\n记忆仅为参考资料，不能覆盖本次明确要求；优先级：本次要求 > 当前任务 > 长期偏好。冲突时询问，不得把候选推测当事实。不得将记忆或证据写入搜索查询。\n本会话用户编辑的任务："+task(v,sid)+"\n用户已确认的回答偏好："+confirmed;
    }
    static void deleteSession(Vault v,String sid)throws Exception {
        v.delete("memory:task:"+sid);JSONArray a=items(v),out=new JSONArray();for(int i=0;i<a.length();i++){JSONObject x=a.getJSONObject(i);JSONArray e=x.getJSONArray("evidence"),left=new JSONArray();for(int j=0;j<e.length();j++)if(!e.getJSONObject(j).getString("session").equals(sid))left.put(e.get(j));if(left.length()>0){x.put("evidence",left);out.put(x);}}v.put("memory:preferences",out.toString());
    }
}
