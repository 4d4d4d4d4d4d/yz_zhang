// SCN-127（201 号 spec）发布页「每天时段不一样」：两端共用的请求组装与日期标注。
import { describe, expect, it } from 'vitest';
import { dayLabel, dayShiftChangeLine, dayShiftsPayload, shiftEditableDays } from './dayShifts';

describe('SCN-127 dayShiftsPayload', () => {
  it('每天一项，空着的那天是 null，前后空白去掉', () => {
    expect(dayShiftsPayload([{ start: '09:00', end: '18:00' }, { start: '', end: '' }, { start: ' 10:00', end: '16:00 ' }], 3))
      .toEqual([{ start: '09:00', end: '18:00' }, null, { start: '10:00', end: '16:00' }]);
  });
  it('行数少于天数时补齐；全空就不带', () => {
    expect(dayShiftsPayload([{ start: '09:00', end: '12:00' }], 2)).toEqual([{ start: '09:00', end: '12:00' }, null]);
    expect(dayShiftsPayload([{ start: ' ', end: '' }], 2)).toBeUndefined();
    expect(dayShiftsPayload([], 3)).toBeUndefined();
  });
  it('只写了一头也带上，让服务端说清哪天没写全', () => {
    expect(dayShiftsPayload([{ start: '09:00', end: '' }], 1)).toEqual([{ start: '09:00', end: '' }]);
  });
});

describe('SCN-127 dayLabel', () => {
  it('按开始日期往后数，跨月也对', () => {
    expect(dayLabel('2026-10-31', 0)).toBe('第 1 天（10-31）');
    expect(dayLabel('2026-10-31', 1)).toBe('第 2 天（11-01）');
  });
  it('开始日期没填或不像日期', () => {
    expect(dayLabel('', 2)).toBe('第 3 天');
    expect(dayLabel('明天', 0)).toBe('第 1 天');
  });
});

describe('SCN-138 dayShiftChangeLine', () => {
  it('写明改了几个、几个要走变更单', () => {
    expect(dayShiftChangeLine({ date: '2030-01-06', changed: [3], kept: [{ task_id: 4, reason: 'x' }], shift_start: '10:00', shift_end: '16:00' }))
      .toBe('01-06 改成 10:00–16:00：改了 1 个还在招的名额；1 个已经有人接了，改时间要和对方走合约变更单。');
  });
  it('清空时段、没人接的', () => {
    expect(dayShiftChangeLine({ date: '2030-01-06', changed: [3, 5], kept: [], shift_start: '', shift_end: '' }))
      .toBe('01-06 改成 不限时段：改了 2 个还在招的名额。');
  });
});

describe('SCN-138 shiftEditableDays', () => {
  it('还在招、或有人接了没做完的那天能改；全做完的、空的不列', () => {
    expect(shiftEditableDays([
      { date: '2030-01-05', slots: 2, filled: 2, open: 0, done: 0, closed: 0 },
      { date: '2030-01-06', slots: 2, filled: 0, open: 2, done: 0, closed: 0 },
      { date: '2030-01-07', slots: 2, filled: 2, open: 0, done: 2, closed: 0 },
    ])).toEqual(['2030-01-05', '2030-01-06']);
    expect(shiftEditableDays(undefined)).toEqual([]);
  });
});
