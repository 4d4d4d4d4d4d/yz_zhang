// SCN-129（192 号 spec）接单卡片上「哪天几点」：两端共用一个函数。
import { describe, expect, it } from 'vitest';
import { gigWhenLabel } from './decompose';

describe('SCN-129 gigWhenLabel', () => {
  it.each([
    [{ work_date: '2026-10-24', shift_start: '09:00', shift_end: '18:00' }, '10-24 09:00–18:00'],
    [{ work_date: '2026-10-24', shift_start: '', shift_end: '' }, '10-24 全天'],
    [{ work_date: '2026-10-24', shift_start: '09:00', shift_end: '' }, '10-24 全天'],   // 不成对按全天（服务端本来就不许）
    [{ work_date: null, shift_start: '09:00', shift_end: '18:00' }, ''],
    [{}, ''],
    [{ work_date: '下周三' }, ''],                                                        // 不像日期不写
  ] as Array<[Parameters<typeof gigWhenLabel>[0], string]>)('%j → %s', (c, want) => {
    expect(gigWhenLabel(c)).toBe(want);
  });
});
