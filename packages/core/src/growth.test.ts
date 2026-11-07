// APP-074d（420 号 spec）
import { describe, expect, it } from 'vitest';
import { newcomerLine, prefLabel, referralLine } from './growth';

describe('通知类目的叫法', () => {
  it('认得的说人话，新类目原样', () => {
    expect(prefLabel('interaction')).toBe('互动（评论、关注、私信）');
    expect(prefLabel('promo')).toBe('promo');
  });
});

describe('新人任务与邀请战绩', () => {
  it('没做完写进度，做完或畸形不写', () => {
    expect(newcomerLine({ finished: 2, total: 5, completed: false })).toBe('新人任务 2/5');
    expect(newcomerLine({ finished: 5, total: 5, completed: true })).toBe('');
    expect(newcomerLine({ finished: '2', total: 5 })).toBe('');
    expect(newcomerLine({ finished: 0, total: 0 })).toBe('');
    expect(newcomerLine(null)).toBe('');
  });
  it('邀请战绩', () => {
    expect(referralLine({ invited_count: 3, achieved_count: 1, earned_cents: 1000 })).toBe('已邀请 3 人 · 达成 1 人 · 累计奖励 ¥10.00');
    expect(referralLine({ invited_count: 3 })).toBe('');
    expect(referralLine(undefined)).toBe('');
  });
});
