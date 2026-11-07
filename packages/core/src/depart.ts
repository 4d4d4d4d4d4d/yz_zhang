import type { GigAlong, GigRouteView } from './types';

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

const WEEKDAY = ['一', '二', '三', '四', '五', '六', '日'];

/** SCN-140（208 号 spec）常用路线的一句话：「工作日 08:30 家 → 公司」「周六、周日 10:00 …」「每天 …」。两端同一句。 */
export function gigRouteLabel(r: Pick<GigRouteView, 'weekdays' | 'depart_hm' | 'from_name' | 'to_name'>): string {
  const days = [...new Set(Array.isArray(r.weekdays) ? r.weekdays : [])].filter((d) => d >= 0 && d <= 6).sort();
  const key = days.join(',');
  const when = key === '0,1,2,3,4,5,6' ? '每天' : key === '0,1,2,3,4' ? '工作日' : key === '5,6' ? '周末'
    : days.map((d) => `周${WEEKDAY[d]}`).join('、');
  return `${when} ${r.depart_hm} ${r.from_name || '（地点已删）'} → ${r.to_name || '（地点已删）'}`;
}
