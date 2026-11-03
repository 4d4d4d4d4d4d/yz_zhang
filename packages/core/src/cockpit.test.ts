import { describe, expect, it } from 'vitest';
import { isUrgentCockpitAlert, scheduleConflictNote } from './cockpit';

describe('AI-DEC-021b 驾驶舱排期冲突（368 号 spec）', () => {
  it('款项冻结、逾期、排期排不开都标红；等你验收、没人报名、超预算不标', () => {
    for (const k of ['dispute', 'overdue', 'schedule_conflict', 'past_parent_deadline']) expect(isUrgentCockpitAlert({ kind: k })).toBe(true);
    for (const k of ['to_accept', 'no_applicants', 'over_budget', 'unknown']) expect(isUrgentCockpitAlert({ kind: k })).toBe(false);
    expect(isUrgentCockpitAlert(null)).toBe(false);
    expect(isUrgentCockpitAlert({ kind: 3 })).toBe(false);
  });

  it('截止那一格写清不晚于哪几步；字段缺失或畸形不报错', () => {
    const title = (id: number) => ({ 1: '设计稿', 2: '文案' } as Record<number, string>)[id] ?? `#${id}`;
    expect(scheduleConflictNote({ schedule_conflicts: [1, 2] }, title)).toBe('（不晚于要等的「设计稿」、「文案」）');
    expect(scheduleConflictNote({ schedule_conflicts: [] }, title)).toBe('');
    expect(scheduleConflictNote({} as never, title)).toBe('');
    expect(scheduleConflictNote({ schedule_conflicts: 'x' } as never, title)).toBe('');
    expect(scheduleConflictNote(null, title)).toBe('');
  });
});
