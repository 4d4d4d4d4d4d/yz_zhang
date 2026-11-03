import { describe, expect, it } from 'vitest';
import { budgetCycleLine, parseBudgetCycleDay } from './teamBudget';

describe('TEAM-056 预算池账期（370 号 spec）', () => {
  it('写清每月几号重置与下次重置；1 号说「按自然月」；老服务端没字段不显示', () => {
    expect(budgetCycleLine({ budget_cycle_day: 15, budget_cycle_resets_at: '2026-11-15T12:00:00+00:00' })).toMatch(/^每月 15 日重置 · 下次 2026\/11\/15/);
    expect(budgetCycleLine({ budget_cycle_day: 1, budget_cycle_resets_at: '2026-12-01T12:00:00+00:00' })).toMatch(/^按自然月重置（每月 1 日） · 下次 /);
    expect(budgetCycleLine({ budget_cycle_day: 15 })).toBe('每月 15 日重置');
    expect(budgetCycleLine({})).toBe('');
    expect(budgetCycleLine({ budget_cycle_day: 31 })).toBe('');
    expect(budgetCycleLine(null)).toBe('');
  });

  it('账期只收 1~28 的整数', () => {
    expect(parseBudgetCycleDay('15')).toBe(15);
    expect(parseBudgetCycleDay(' 1 ')).toBe(1);
    expect(parseBudgetCycleDay('28')).toBe(28);
    for (const bad of ['0', '29', '31', '1.5', 'abc', '', '-3']) expect(parseBudgetCycleDay(bad)).toBeNull();
  });
});
