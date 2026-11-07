import type { DayShiftChangeResult, DayShiftInput, TaskDaySummary } from './types';

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

/** SCN-138（202 号 spec）改了某一天的时段之后的一句话：改了几个、几个有人接了要走变更单。两端同一句。 */
export function dayShiftChangeLine(r: Pick<DayShiftChangeResult, 'date' | 'changed' | 'kept' | 'shift_start' | 'shift_end'>): string {
  const n = Array.isArray(r.changed) ? r.changed.length : 0;
  const kept = Array.isArray(r.kept) ? r.kept : [];
  // SCN-139 有人接的名额：发出了变更单的说「对方同意后生效」，没发出的照旧说要走变更单
  const sent = kept.filter((x) => typeof x?.change_order_id === 'number').length;
  const rest = kept.length - sent;
  const when = r.shift_start ? `${r.shift_start}–${r.shift_end}` : '不限时段';
  return `${String(r.date).slice(5)} 改成 ${when}：改了 ${n} 个还在招的名额`
    + (sent ? `；${sent} 个已经有人接了，已给对方发了变更单，对方同意后生效` : '')
    + (rest ? `；${rest} 个已经有人接了，改时间要和对方走合约变更单` : '') + '。';
}

/** SCN-138 哪些天还能改时段：还有在招的名额，或有人接了还没做完（后者服务端会写明要走变更单）。两端同一条判断。 */
export function shiftEditableDays(days: TaskDaySummary[] | undefined): string[] {
  return (days ?? []).filter((d) => d.open > 0 || d.filled > d.done).map((d) => d.date);
}
