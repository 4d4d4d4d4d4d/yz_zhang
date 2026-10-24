import { describe, expect, it } from 'vitest';
import { copyScheduleDay } from './supportSchedule';

const MON = [{ weekday: 0, start: '08:00', end: '12:00' }, { weekday: 0, start: '18:00', end: '22:00' }];

describe('ESCA-071 把一天的排班复制到其他几天', () => {
  it('目标几天换成来源那天的几段，排好序；来源那天不动', () => {
    const rows = [...MON, { weekday: 2, start: '09:00', end: '18:00' }, { weekday: 5, start: '10:00', end: '12:00' }];
    expect(copyScheduleDay(rows, 0, [0, 1, 2])).toEqual([
      ...MON,
      { weekday: 1, start: '08:00', end: '12:00' }, { weekday: 1, start: '18:00', end: '22:00' },
      { weekday: 2, start: '08:00', end: '12:00' }, { weekday: 2, start: '18:00', end: '22:00' },
      { weekday: 5, start: '10:00', end: '12:00' },
    ]);
  });
  it('来源那天没有排班：什么都不改', () => {
    const rows = [{ weekday: 2, start: '09:00', end: '18:00' }];
    expect(copyScheduleDay(rows, 0, [2])).toBe(rows);
  });
});
