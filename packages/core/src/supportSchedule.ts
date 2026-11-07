// ESCA-071（273 号 spec）排班：把一天的几段复制到其他几天。
import type { SupportScheduleWindow } from './types';

/** 目标几天原有的段先清掉，再换成来源那天的几段（同样的时间）；来源那天自己不动。结果按周几、开始时间排好。
 *  来源那天没有排班时什么都不改（不会把目标几天清空）。 */
export function copyScheduleDay(rows: SupportScheduleWindow[], from: number, to: number[]): SupportScheduleWindow[] {
  const src = rows.filter((w) => w.weekday === from);
  if (!src.length) return rows;
  const targets = new Set(to.filter((d) => d !== from));
  const kept = rows.filter((w) => !targets.has(w.weekday));
  const copies = [...targets].flatMap((weekday) => src.map((w) => ({ weekday, start: w.start, end: w.end })));
  return [...kept, ...copies].sort((a, b) => a.weekday - b.weekday || a.start.localeCompare(b.start));
}
