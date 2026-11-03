/**
 * TEAM-056（370 号 spec）团队预算池的账期：每月几号重置。两端共用的说法与输入校验。
 */
import { formatDateTime } from './time';
import type { TeamDetail } from './types';

export const MAX_BUDGET_CYCLE_DAY = 28;

/** 「每月 15 日重置 · 下次 2026/11/15 08:00」；老服务端没有账期字段时为空串 */
export function budgetCycleLine(team: Pick<TeamDetail, 'budget_cycle_day' | 'budget_cycle_resets_at'> | null | undefined): string {
  const d = team?.budget_cycle_day;
  if (typeof d !== 'number' || !Number.isInteger(d) || d < 1 || d > MAX_BUDGET_CYCLE_DAY) return '';
  const next = formatDateTime(team?.budget_cycle_resets_at ?? null);
  const head = d === 1 ? '按自然月重置（每月 1 日）' : `每月 ${d} 日重置`;
  return next ? `${head} · 下次 ${next}` : head;
}

/** 输入框里的账期：1~28 的整数，否则 null（29~31 号不是每个月都有） */
export function parseBudgetCycleDay(input: string): number | null {
  const s = (input ?? '').trim();
  if (!/^\d{1,2}$/.test(s)) return null;
  const n = Number(s);
  return n >= 1 && n <= MAX_BUDGET_CYCLE_DAY ? n : null;
}
