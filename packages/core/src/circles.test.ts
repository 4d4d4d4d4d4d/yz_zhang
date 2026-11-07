// APP-074e（439 号 spec）圈层文案两端共用。
import { describe, expect, it } from 'vitest';
import { CIRCLE_KIND_LABEL, circleJoinLabel, circleSummary } from './circles';

describe('圈层文案', () => {
  it('没加入：开放的写「加入圈层」，要审核的写「申请加入」；已加入、待审核的没有按钮', () => {
    expect(circleJoinLabel({ my_status: null, join_policy: 'open' })).toBe('加入圈层');
    expect(circleJoinLabel({ my_status: null, join_policy: 'approval' })).toBe('申请加入');
    expect(circleJoinLabel({ my_status: 'active', join_policy: 'open' })).toBeNull();
    expect(circleJoinLabel({ my_status: 'pending', join_policy: 'approval' })).toBeNull();
  });

  it('简介：有描述用描述、没有写人数，有信用分门槛的写出来；畸形人数当 0', () => {
    expect(circleSummary({ description: '上海保洁师傅', member_count: 12, min_credit: 0 })).toBe('上海保洁师傅');
    expect(circleSummary({ description: ' ', member_count: 12, min_credit: 80 })).toBe('12 位成员 · 信用分 ≥ 80');
    expect(circleSummary({ description: '', member_count: NaN, min_credit: 0 })).toBe('0 位成员');
    expect(Object.keys(CIRCLE_KIND_LABEL)).toEqual(['interest', 'skill', 'local']);
  });
});
