"""Compile actual query action policy and verify business-side-effect boundaries."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
j=Path('/Applications/PyCharm.app/Contents/jbr/Contents/Home/bin')
with tempfile.TemporaryDirectory() as folder:
 d=Path(folder);(d/'QueryPolicy.java').write_text((root/'android/src/QueryPolicy.java').read_text())
 (d/'QueryPolicyTest.java').write_text('''package org.qwen.local;
 public class QueryPolicyTest {
  static void ok(boolean b){if(!b)throw new AssertionError();}
  public static void main(String[] a){
   ok(QueryPolicy.click("机票","首页"));ok(QueryPolicy.click("查 询","机票"));ok(QueryPolicy.click("查\u3000询","机票"));ok(!QueryPolicy.click("查 询 并 付 款","机票"));ok(QueryPolicy.click("查询","机票 单程"));
   for(String text:new String[]{"支付","提交订单","预订","发送","确认付款","删除","允许","查询并付款","29"})ok(!QueryPolicy.click(text,"首页"));
   ok(QueryPolicy.click("29","选择出发日期"));ok(!QueryPolicy.click("-1","选择出发日期"));
   ok(QueryPolicy.cityInput("搜索城市或拼音","选择城市","Shanghai"));
   ok(QueryPolicy.cityInput("搜索城市或拼音","选择城市","北京"));
   ok(!QueryPolicy.cityInput("密码","选择城市","secret"));
   ok(!QueryPolicy.cityInput("搜索城市","选择城市","13800138000"));
   ok(!QueryPolicy.cityInput("搜索城市","选择城市","北京;付款"));
   System.out.println("QUERY_POLICY_OK: navigation allowed; purchase/send/account and non-city input denied");
  }
 }''')
 subprocess.run([str(j/'javac'),'-d',str(d),str(d/'QueryPolicy.java'),str(d/'QueryPolicyTest.java')],check=True)
 subprocess.run([str(j/'java'),'-cp',str(d),'org.qwen.local.QueryPolicyTest'],check=True)
