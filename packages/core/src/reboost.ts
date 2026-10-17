import { fmtYuan } from './client';
import type { ReboostDayResult } from './types';

/** SCN-121（196 号 spec）补招之后的一句话：哪天、几个名额再推了一次、加了多少。两端同一句。 */
export function reboostLine(r: Pick<ReboostDayResult, 'date' | 'slot_ids' | 'raise_cents'>): string {
  const n = Array.isArray(r.slot_ids) ? r.slot_ids.length : 0;
  const extra = r.raise_cents > 0 ? `，每个名额加价 ${fmtYuan(r.raise_cents)}` : '';
  return `已补招 ${String(r.date).slice(5)}：${n} 个还在招的名额再推了一次${extra}。6 小时后可以再补一次。`;
}

/** 补招表单里「每个名额加价（元）」的输入换成分：空着是 0（只再推一次）；不是正数返回 null（表单提示）。 */
export function raiseToCents(yuan: string): number | null {
  const t = yuan.trim();
  if (!t) return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(Number(t) * 100);
}
