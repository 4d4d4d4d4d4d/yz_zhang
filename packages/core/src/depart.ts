import type { GigAlong } from './types';

/** SCN-134（203 号 spec）顺路单的出发时间：「今天 / 明天」+「HH:MM」换成北京时间的 YYYY-MM-DDTHH:MM。
 *  没填是 undefined（按「现在有空」）；写错是 null（不发请求，就地说明）。两端同一条换算。 */
export function departAt(dayOffset: number, hm: string, now: Date = new Date()): string | null | undefined {
  const t = hm.trim();
  if (!t) return undefined;
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(t)) return null;
  const beijing = new Date(now.getTime() + 8 * 3600_000 + dayOffset * 86400_000);
  return `${beijing.toISOString().slice(0, 10)}T${t}`;
}

export const DEPART_HINT = '出发时间按 24 小时制写成 HH:MM（例如 08:30）；不填就按「现在有空」';

/** 顺路单结果按出发时间筛过时的一句话；没带出发时间是空串。 */
export function departLine(r: Pick<GigAlong, 'depart_at' | 'within_hours'> | null | undefined): string {
  if (!r?.depart_at || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(r.depart_at)) return '';
  return `按 ${r.depart_at.slice(5, 10)} ${r.depart_at.slice(11, 16)} 出发、之后 ${r.within_hours ?? 3} 小时内的名额筛`;
}
