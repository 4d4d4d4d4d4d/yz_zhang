// SC-017（304 号 spec）交付文件挂到某一期的文案
import { describe, expect, it } from 'vitest';
import { deliverableLockedText, deliverableStageTag, licenseLine } from './deliverables';

describe('SC-017 交付文件按期解锁的文案', () => {
  it('全是整份合约的：与以前一字不差', () => {
    expect(deliverableLockedText([{}, {}])).toBe('原图 2 张：验收放款后可以下载');
    expect(deliverableStageTag({})).toBe('');
  });
  it('按期排好、说清各等哪一期，其余的等全部放款', () => {
    expect(deliverableLockedText([{ milestone_idx: 3 }, { milestone_idx: 1 }, { milestone_idx: 3 }, {}]))
      .toBe('原图 4 张：第 1 期 1 张在这一期放款后可以下载；第 3 期 2 张在这一期放款后可以下载；其余 1 张全部放款后可以下载');
    expect(deliverableStageTag({ milestone_idx: 2 })).toBe('（第 2 期）');
  });
});

describe('SCN-202 licenseLine', () => {
  it('写清类别、名称、来源；有范围才带括号', () => {
    expect(licenseLine({ kind: 'music', title: '《夏日》', source: '某曲库商用授权', scope: '仅限抖音' }))
      .toBe('音乐：《夏日》——某曲库商用授权（仅限抖音）');
    expect(licenseLine({ kind: 'font', title: '思源黑体', source: '开源 OFL', scope: '' })).toBe('字体：思源黑体——开源 OFL');
  });
});
