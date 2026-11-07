import { describe, expect, it } from 'vitest';
import { departAt, departLine, gigRouteLabel } from './depart';

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

describe('SCN-140 gigRouteLabel', () => {
  it('工作日 / 每天 / 周末 / 逐个写', () => {
    const r = { depart_hm: '08:30', from_name: '家', to_name: '公司' };
    expect(gigRouteLabel({ ...r, weekdays: [4, 0, 1, 2, 3] })).toBe('工作日 08:30 家 → 公司');
    expect(gigRouteLabel({ ...r, weekdays: [0, 1, 2, 3, 4, 5, 6] })).toBe('每天 08:30 家 → 公司');
    expect(gigRouteLabel({ ...r, weekdays: [6, 5] })).toBe('周末 08:30 家 → 公司');
    expect(gigRouteLabel({ ...r, weekdays: [0, 2, 9] })).toBe('周一、周三 08:30 家 → 公司');
  });
  it('地点删了也不崩', () => {
    expect(gigRouteLabel({ depart_hm: '18:00', from_name: '', to_name: '家', weekdays: [5, 6] })).toBe('周末 18:00 （地点已删） → 家');
  });
});
