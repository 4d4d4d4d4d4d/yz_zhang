package org.qwen.local;
import java.util.Arrays;
/** Native-selected task scope; page text and model arguments cannot change it. */
final class TaskScope {
 static final String TEST_MESSAGE="本地助手功能测试，请忽略";
 static String packageName(String mode){
  if(mode.equals("telegram"))return "org.telegram.messenger";
  if(mode.equals("food"))return "me.ele";
  if(mode.equals("travel"))return QueryPolicy.PACKAGE;
  throw new IllegalArgumentException("未知应用任务");
 }
 static boolean navigation(String mode,String label,String screen,boolean selfChat){
  if(mode.equals("travel"))return QueryPolicy.click(label,screen);
  if(mode.equals("telegram"))return label.equals("Saved Messages")||label.equals("收藏夹")||(!selfChat&&Arrays.asList("More options","Open navigation menu","更多选项","打开导航菜单").contains(label));
  return Arrays.asList("搜索","搜索商家、商品名称","外卖","美食","美食外卖","取消","关闭","返回").contains(label);
 }
 static boolean sendLabel(String label){return label.equals("Send")||label.equals("发送");}
 static boolean foodInput(String label,String value){return (label.contains("搜索")||label.contains("Search"))&&value.length()>0&&value.length()<=64&&!value.contains("\n");}
 static String description(String mode){
  if(mode.equals("telegram"))return "Telegram收藏夹测试。launch打开Telegram，点击More options和Saved Messages；只有收藏夹内可type固定正文“"+TEST_MESSAGE+"”。send使用发送按钮node发送这条测试消息（仅一次），之后read核验。Connecting或Sending表示未确认送达，不得重复发送。禁止其他收件人。";
  if(mode.equals("food"))return "饿了么/淘宝闪购浏览测试。launch打开App，read读取页面，click仅搜索/外卖/美食/关闭/取消/返回，type仅搜索框。当前不能加购、提交订单或付款。遇到登录、定位和商品选择能力不足时报告具体阻塞。";
  return "携程查询。launch打开携程，read读取页面，click查询导航，type城市搜索，back返回。禁止下单和付款。";
 }
}
