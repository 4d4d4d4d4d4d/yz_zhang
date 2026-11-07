// OPC-104 申报截止这类「北京时间日期」的换算：不随浏览器所在时区漂。
import { describe, expect, it } from 'vitest';
import { chinaDateAt, chinaQuarter, chinaToday } from './time';

describe('北京时间日期', () => {
  it('截止日 18:00 = UTC 10:00；提前 3 天提醒跨月也对', () => {
    expect(chinaDateAt('2026-10-15')).toBe('2026-10-15T10:00:00.000Z');
    expect(chinaDateAt('2026-11-02', '18:00', 3)).toBe('2026-10-30T10:00:00.000Z');
    expect(chinaDateAt('2026-10-15', '07:30')).toBe('2026-10-14T23:30:00.000Z');
    expect(chinaDateAt('2026/10/15')).toBe('');
  });

  it('UTC 晚上 20 点已经是北京时间第二天；季度按北京日期算', () => {
    const utc = Date.UTC(2026, 8, 30, 20, 0);   // UTC 9-30 20:00 = 北京 10-01 04:00
    expect(chinaToday(utc)).toBe('2026-10-01');
    expect(chinaQuarter(utc)).toBe('2026-Q4');
    expect(chinaQuarter(Date.UTC(2026, 8, 30, 10, 0))).toBe('2026-Q3');
  });
});
