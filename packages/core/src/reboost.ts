import { fmtYuan } from './client';
import type { ReboostDayResult } from './types';

/** SCN-121（196 号 spec）补招之后的一句话：哪天、几个名额再推了一次、加了多少。两端同一句。 */
export function reboostLine(r: Pick<ReboostDayResult, 'date' | 'slot_ids' | 'raise_cents' | 'invited'>, askedInvite = false): string {
  const n = Array.isArray(r.slot_ids) ? r.slot_ids.length : 0;
  const extra = r.raise_cents > 0 ? `，每个名额加价 ${fmtYuan(r.raise_cents)}` : '';
  // SCN-137 顺带邀请了谁：写人数与昵称；勾了却没找到合适的人也说一声
  const invited = Array.isArray(r.invited) ? r.invited : [];
  const who = invited.length
    ? `；邀请了 ${invited.length} 个那天有空、做过这类活的人（${invited.map((x) => x.nickname).join('、')}）`
    : askedInvite ? '；这天没找到做过这类活、又正好有空的人可邀' : '';
  return `已补招 ${String(r.date).slice(5)}：${n} 个还在招的名额再推了一次${extra}${who}。6 小时后可以再补一次。`;
}

/** 补招表单里「每个名额加价（元）」的输入换成分：空着是 0（只再推一次）；不是正数返回 null（表单提示）。 */
export function raiseToCents(yuan: string): number | null {
  const t = yuan.trim();
  if (!t) return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(Number(t) * 100);
}

/** SCN-137 两端补招时勾「顺带邀请」一次邀几个人（服务端上限 5）。 */
export const REBOOST_INVITE_COUNT = 3;
