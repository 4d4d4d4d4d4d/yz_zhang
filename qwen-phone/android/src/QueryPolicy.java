package org.qwen.local;
import java.util.Arrays;
/** Deliberately narrow navigation policy; no purchase, account, or messaging actions. */
final class QueryPolicy {
 static final String PACKAGE="ctrip.android.view";
 static boolean click(String label,String screen){
  label=label.replaceAll("[\\s\\p{Z}]+", "");
  if(Arrays.asList("机票","查询","单程","经济舱","关闭","取消","返回","出发早-晚","价格排序","直飞优先").contains(label))return true;
  if(screen.contains("选择出发日期"))return label.matches("[0-9]{1,2}");
  return false;
 }
 static boolean cityInput(String label,String screen,String value){
  return value.length()>0&&value.length()<=40&&value.matches("[\\p{L} -]+")
   &&(label.contains("城市")||label.contains("拼音"))
   &&(screen.contains("城市")||screen.contains("机场"));
 }
}
