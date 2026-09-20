// TZ-063 服务端时间的解析入口。这条测试存在的理由是一个具体的错：
// 服务端给 UTC 值却不带 `Z`，`new Date()` 把它当本地时间，全站显示偏一个时区。
import { describe, expect, it } from 'vitest';
import { formatDate, formatDateTime, localInputToServerTime, millisUntil, parseServerTime } from './time';

describe('parseServerTime', () => {
  it('不带偏移的按 UTC 解析——这正是那个错的反面', () => {
    const withZ = parseServerTime('2026-09-20T08:00:00Z')!;
    const bare = parseServerTime('2026-09-20T08:00:00')!;
    expect(bare.getTime()).toBe(withZ.getTime());
    expect(bare.toISOString()).toBe('2026-09-20T08:00:00.000Z');
  });

  it('带偏移的照常尊重偏移', () => {
    expect(parseServerTime('2026-09-20T16:00:00+08:00')!.toISOString())
      .toBe('2026-09-20T08:00:00.000Z');
  });

  it('空值与非法值给 null，不给 Invalid Date', () => {
    expect(parseServerTime(null)).toBeNull();
    expect(parseServerTime('')).toBeNull();
    expect(parseServerTime('不是时间')).toBeNull();
  });

  it('纯日期不动它（JS 本来就按 UTC 解析）', () => {
    expect(parseServerTime('2026-09-20')!.toISOString()).toBe('2026-09-20T00:00:00.000Z');
  });
});

describe('展示与提交', () => {
  it('formatDateTime / formatDate 对空值给空串，不给 "Invalid Date"', () => {
    expect(formatDateTime(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
  });

  it('formatDateTime 在给定时区下渲染的是同一时刻', () => {
    const s = formatDateTime('2026-09-20T08:00:00Z', 'zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
    expect(s).toContain('16');          // UTC 08:00 → 东八区 16:00
  });

  it('millisUntil 对带 Z 与不带 Z 给同一个结果（倒计时不再需要手工补 Z）', () => {
    const future = new Date(Date.now() + 3_600_000).toISOString();
    const bare = future.replace('Z', '');
    expect(Math.abs(millisUntil(future) - millisUntil(bare))).toBeLessThan(5);
  });

  it('localInputToServerTime 把 datetime-local 的本地值转成带 Z 的 UTC', () => {
    // datetime-local 给的是没有偏移的本地字符串；直接发出去服务端会当 UTC，
    // 那正是 TZ-062 那个洞的镜像
    const out = localInputToServerTime('2030-01-01T10:00');
    expect(out.endsWith('Z')).toBe(true);
    expect(new Date(out).getTime()).toBe(new Date('2030-01-01T10:00').getTime());
    expect(localInputToServerTime('')).toBe('');
  });
});
