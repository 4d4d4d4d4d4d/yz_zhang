import type { DayShiftInput } from './types';

/** SCN-127（201 号 spec）发布页「每天时段不一样」：每天一行，全空就不带（沿用统一时段）；某天空着传 null。
 *  返回 undefined 表示请求里不带 day_shifts。两端同一个。 */
export function dayShiftsPayload(rows: DayShiftInput[], days: number): Array<DayShiftInput | null> | undefined {
  const list = Array.from({ length: Math.max(days, 0) }, (_, i) => rows[i] ?? { start: '', end: '' });
  const filled = (r: DayShiftInput) => !!(r.start.trim() || r.end.trim());
  if (!list.some(filled)) return undefined;
  return list.map((r) => (filled(r) ? { start: r.start.trim(), end: r.end.trim() } : null));
}

/** 第 i 天是哪天（MM-DD），给每一行标出来；开始日期没填或不像日期就写「第 N 天」。 */
export function dayLabel(startDate: string, i: number): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(startDate.trim());
  if (!m) return `第 ${i + 1} 天`;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + i));
  return `第 ${i + 1} 天（${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}）`;
}
