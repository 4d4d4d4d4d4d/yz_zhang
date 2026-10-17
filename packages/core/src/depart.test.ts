import { describe, expect, it } from 'vitest';
import { departAt, departLine } from './depart';

describe('SCN-134 departAt', () => {
  const now = new Date('2030-01-06T17:30:00Z'); // 北京时间 01-07 01:30
  it('按北京时间的日子拼上时间；明天加一天', () => {
    expect(departAt(0, '08:30', now)).toBe('2030-01-07T08:30');
    expect(departAt(1, ' 18:05 ', now)).toBe('2030-01-08T18:05');
  });
  it('没填是 undefined，写错是 null', () => {
    expect(departAt(0, '  ', now)).toBeUndefined();
    for (const bad of ['8:30', '24:00', '08:60', '0830']) expect(departAt(0, bad, now)).toBeNull();
  });
});

describe('SCN-134 departLine', () => {
  it('带了出发时间写一句，没带是空串', () => {
    expect(departLine({ depart_at: '2030-01-07T08:30', within_hours: 2 })).toBe('按 01-07 08:30 出发、之后 2 小时内的名额筛');
    expect(departLine({ depart_at: null, within_hours: null })).toBe('');
    expect(departLine(undefined)).toBe('');
  });
});
