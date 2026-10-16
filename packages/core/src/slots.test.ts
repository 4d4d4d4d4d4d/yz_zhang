// SCN-116 多天名额按天汇总的那句话（174 号 spec）：两端同一份。
import { describe, expect, it } from 'vitest';
import { daySummaryLine, daysStillShort, hasChildTasks, shiftLabel } from './decompose';

const d = (date: string, slots: number, filled: number, open: number, done = 0, closed = 0) =>
  ({ date, slots, filled, open, done, closed });

describe('SCN-116 多天名额按天汇总', () => {
  it('一天一行：日期、名额、招到、还缺；做完与取消有才说', () => {
    expect(daySummaryLine(d('2026-10-18', 2, 1, 1))).toBe('10-18 · 2 个名额：招到 1，还缺 1');
    expect(daySummaryLine(d('2026-10-19', 2, 1, 0, 1, 1))).toBe('10-19 · 2 个名额：招到 1，不缺人了，做完 1，取消 1');
  });

  it('还缺人的那几天；没有汇总（单天多人）时是空表', () => {
    const days = [d('2026-10-18', 2, 2, 0), d('2026-10-19', 2, 0, 2), d('2026-10-20', 2, 1, 1)];
    expect(daysStillShort(days).map((x) => x.date)).toEqual(['2026-10-19', '2026-10-20']);
    expect(daysStillShort(undefined)).toEqual([]);
  });

  it('多人或多天的根任务也拉子任务进度（以前只有项目型才拉，名额在详情页上看不到）', () => {
    const t = { parent_id: null, task_type: 'service', days: 1, people_needed: 1 };
    expect(hasChildTasks(t)).toBe(false);
    expect(hasChildTasks({ ...t, task_type: 'project' })).toBe(true);
    expect(hasChildTasks({ ...t, days: 3 })).toBe(true);
    expect(hasChildTasks({ ...t, people_needed: 2 })).toBe(true);
    expect(hasChildTasks({ ...t, people_needed: 2, parent_id: 9 })).toBe(false);
    expect(hasChildTasks({ parent_id: null, task_type: 'service' })).toBe(false);
  });

  it('SCN-117 时段一句话：多天写「每天」，单天写「时段」，没写是空串', () => {
    expect(shiftLabel({ shift_start: '09:00', shift_end: '18:30', days: 3, parent_id: null })).toBe('每天 09:00–18:30');
    expect(shiftLabel({ shift_start: '09:00', shift_end: '18:30', days: 1, parent_id: 5 })).toBe('时段 09:00–18:30');
    expect(shiftLabel({ shift_start: '', shift_end: '', days: 3, parent_id: null })).toBe('');
    expect(shiftLabel({ parent_id: null })).toBe('');
  });
});
