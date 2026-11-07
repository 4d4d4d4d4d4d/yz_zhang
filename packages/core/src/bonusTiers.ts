/** OUT-050（443 号 spec）浮动对价的说法：两端的任务详情共用，与合同条款一致。 */
import { fmtYuan } from './client';
import type { BonusTier } from './types';

/** 任务详情上的一行：没分档的照旧「达标可加付至多 X」，分档的逐档写出来、说明取最高一档不累加。畸形的档跳过。 */
export function bonusLine(bonusCents: number, tiers: BonusTier[] | null | undefined): string {
  const ok = (Array.isArray(tiers) ? tiers : [])
    .filter((t) => t && Number.isFinite(t.min_passed) && Number.isFinite(t.bonus_cents) && t.bonus_cents > 0);
  if (!ok.length) return `达标可加付至多 ${fmtYuan(bonusCents)}（按验收指标判定）`;
  const parts = ok.map((t) => `过 ${t.min_passed} 条加付 ${fmtYuan(t.bonus_cents)}`);
  return `按通过的平台判定指标分档加付：${parts.join('，')}（取最高一档，不累加）`;
}
