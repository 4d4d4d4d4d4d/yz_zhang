import { describe, expect, it } from 'vitest';
import { isUrgentCockpitAlert, projectedFinishLine, scheduleConflictNote, timelineBars, timelineBasisLabel } from './cockpit';

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

describe('AI-DEC-021c 驾驶舱时间线（384 号 spec）', () => {
  const row = (task_id: number, start: string | null, end: string | null, basis = 'estimate', late = false) =>
    ({ task_id, start, end, basis, late }) as never;

  it('按工期估计赶不上截止的两种预警都标红', () => {
    expect(isUrgentCockpitAlert({ kind: 'projected_late' })).toBe(true);
    expect(isUrgentCockpitAlert({ kind: 'estimate_past_deadline' })).toBe(true);
  });

  it('条从最早的开始排到最晚的结束，后一步接在前一步后面', () => {
    const bars = timelineBars({ rows: [
      row(1, '2026-11-10T12:00:00Z', '2026-11-12T12:00:00Z'),
      row(2, '2026-11-12T12:00:00Z', '2026-11-20T12:00:00Z', 'deadline', true),
      row(3, null, null, 'done'),
      row(4, null, null, 'unknown'),
    ], projected_finish: '2026-11-20T12:00:00Z', unknown_steps: [] });
    expect(bars.map((b) => b.task_id)).toEqual([1, 2]);
    expect(bars[0]).toMatchObject({ offsetPct: 0, widthPct: 20, basis: 'estimate', late: false });
    expect(bars[1]).toMatchObject({ offsetPct: 20, widthPct: 80, basis: 'deadline', late: true });
  });

  it('很短的一步也至少看得见；畸形与缺失不报错', () => {
    const bars = timelineBars({ rows: [
      row(1, '2026-11-01T12:00:00Z', '2026-11-01T13:00:00Z'),
      row(2, '2026-11-01T12:00:00Z', '2026-12-31T12:00:00Z'),
      row(5, '2026-11-05T12:00:00Z', '2026-11-01T12:00:00Z'),
      { task_id: 'x', start: '2026-11-01T12:00:00Z', end: '2026-11-02T12:00:00Z' } as never,
      null as never,
    ], projected_finish: null, unknown_steps: [] });
    expect(bars.map((b) => b.task_id)).toEqual([1, 2]);
    expect(bars[0].widthPct).toBe(2);
    expect(timelineBars(undefined)).toEqual([]);
    expect(timelineBars({ rows: 'x' } as never)).toEqual([]);
  });

  it('完成日那一句：排得出来写日期，排不出来说清几步没填，老服务端为空', () => {
    expect(projectedFinishLine({ timeline: { rows: [], projected_finish: '2026-11-20T12:00:00Z', unknown_steps: [] } }, 'zh-CN'))
      .toMatch(/^按各步工期排下来，预计 .*20.* 做完$/);
    expect(projectedFinishLine({ timeline: { rows: [], projected_finish: null, unknown_steps: [3, 4] } }))
      .toBe('有 2 步没填工期也没填截止，排不出整件事的完成日：给每一步填上要几天');
    expect(projectedFinishLine({})).toBe('');
    expect(projectedFinishLine(null)).toBe('');
    expect(projectedFinishLine({ timeline: { rows: [], projected_finish: null, unknown_steps: [] } })).toBe('');
  });

  it('每一条的说明', () => {
    expect(timelineBasisLabel('estimate')).toBe('按工期估计');
    expect(timelineBasisLabel('deadline', true)).toBe('没填工期，按截止排（赶不上这一步的截止）');
    expect(timelineBasisLabel('unknown')).toBe('排不出来：没填工期也没填截止');
  });
});
