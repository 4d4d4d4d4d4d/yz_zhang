// SCN-127（201 号 spec）发布页「每天时段不一样」：两端共用的请求组装与日期标注。
import { describe, expect, it } from 'vitest';
import { dayLabel, dayShiftsPayload } from './dayShifts';

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
