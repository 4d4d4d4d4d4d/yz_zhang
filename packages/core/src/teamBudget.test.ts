import { describe, expect, it } from 'vitest';
import { BUDGET_TIMEZONE_OPTIONS, budgetCycleLine, budgetTimezoneLabel, parseBudgetCycleDay } from './teamBudget';

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

describe('TEAM-056b 账期按团队选的时区起算（392 号 spec）', () => {
  it('选了时区写明按哪里的 0 点；UTC 或没选与原来一字不变', () => {
    expect(budgetCycleLine({ budget_cycle_day: 15, budget_tz: 'Asia/Shanghai' })).toBe('每月 15 日重置（按北京时间 0 点）');
    expect(budgetCycleLine({ budget_cycle_day: 1, budget_tz: 'America/New_York' })).toBe('按自然月重置（每月 1 日，按纽约时间 0 点）');
    expect(budgetCycleLine({ budget_cycle_day: 15, budget_tz: 'UTC' })).toBe('每月 15 日重置');
    expect(budgetCycleLine({ budget_cycle_day: 1 })).toBe('按自然月重置（每月 1 日）');
  });

  it('选项第一项是默认的 UTC；与服务端同一张表', () => {
    expect(BUDGET_TIMEZONE_OPTIONS[0][0]).toBe('UTC');
    expect(BUDGET_TIMEZONE_OPTIONS.map(([v]) => v)).toEqual(['UTC', 'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Taipei', 'Asia/Tokyo',
      'Asia/Singapore', 'Europe/London', 'America/New_York', 'America/Los_Angeles']);
    expect(budgetTimezoneLabel('Asia/Tokyo')).toBe('东京时间');
    expect(budgetTimezoneLabel('UTC')).toBe('协调世界时（UTC）');
    expect(budgetTimezoneLabel(null)).toBe('协调世界时（UTC）');
    expect(budgetTimezoneLabel('Mars/Olympus')).toBe('Mars/Olympus');
  });
});
