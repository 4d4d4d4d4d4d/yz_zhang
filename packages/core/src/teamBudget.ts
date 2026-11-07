/**
 * TEAM-056（370 号 spec）团队预算池的账期：每月几号重置。两端共用的说法与输入校验。
 */
import { formatDateTime } from './time';
import type { BudgetTimezone, TeamDetail } from './types';

export const MAX_BUDGET_CYCLE_DAY = 28;

/** TEAM-056b（392 号 spec）账期时区的选项（与服务端 BUDGET_TIMEZONES 同一张表；第一项是默认） */
export const BUDGET_TIMEZONE_OPTIONS: ReadonlyArray<readonly [BudgetTimezone, string]> = [
  ['UTC', '协调世界时（UTC，默认）'],
  ['Asia/Shanghai', '北京时间'],
  ['Asia/Hong_Kong', '香港时间'],
  ['Asia/Taipei', '台北时间'],
  ['Asia/Tokyo', '东京时间'],
  ['Asia/Singapore', '新加坡时间'],
  ['Europe/London', '伦敦时间'],
  ['America/New_York', '纽约时间'],
  ['America/Los_Angeles', '洛杉矶时间'],
];

/** 时区的中文名；不认识的原样返回，空的当 UTC */
export function budgetTimezoneLabel(tz: string | null | undefined): string {
  const hit = BUDGET_TIMEZONE_OPTIONS.find(([v]) => v === (tz || 'UTC'));
  return hit ? hit[1].replace('（UTC，默认）', '（UTC）') : String(tz);
}

/** 「每月 15 日重置 · 下次 2026/11/15 08:00」；老服务端没有账期字段时为空串。
 *  TEAM-056b 选了时区的，写明「按北京时间 0 点」（下次重置的时刻仍按看的人本机时间显示） */
export function budgetCycleLine(team: Pick<TeamDetail, 'budget_cycle_day' | 'budget_cycle_resets_at' | 'budget_tz'> | null | undefined): string {
  const d = team?.budget_cycle_day;
  if (typeof d !== 'number' || !Number.isInteger(d) || d < 1 || d > MAX_BUDGET_CYCLE_DAY) return '';
  const next = formatDateTime(team?.budget_cycle_resets_at ?? null);
  // 没选时区（或选 UTC）与原来一字不变
  const tz = team?.budget_tz && team.budget_tz !== 'UTC' ? `按${budgetTimezoneLabel(team.budget_tz)} 0 点` : '';
  const head = d === 1 ? (tz ? `按自然月重置（每月 1 日，${tz}）` : '按自然月重置（每月 1 日）')
    : (tz ? `每月 ${d} 日重置（${tz}）` : `每月 ${d} 日重置`);
  return next ? `${head} · 下次 ${next}` : head;
}

/** 输入框里的账期：1~28 的整数，否则 null（29~31 号不是每个月都有） */
export function parseBudgetCycleDay(input: string): number | null {
  const s = (input ?? '').trim();
  if (!/^\d{1,2}$/.test(s)) return null;
  const n = Number(s);
  return n >= 1 && n <= MAX_BUDGET_CYCLE_DAY ? n : null;
}
