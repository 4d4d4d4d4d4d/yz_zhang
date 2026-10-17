// SCN-121（196 号 spec）补招：结果说明与加价输入。两端共用。
import { describe, expect, it } from 'vitest';
import { raiseToCents, reboostLine } from './reboost';

describe('SCN-121 reboostLine', () => {
  it('加价时写明每个名额加多少', () => {
    expect(reboostLine({ date: '2026-10-24', slot_ids: [3, 4], raise_cents: 1000 }))
      .toBe('已补招 10-24：2 个还在招的名额再推了一次，每个名额加价 ¥10.00。6 小时后可以再补一次。');
  });
  it('只再推一次时不提加价；响应不像样也不崩', () => {
    expect(reboostLine({ date: '2026-10-24', slot_ids: [3], raise_cents: 0 })).toBe('已补招 10-24：1 个还在招的名额再推了一次。6 小时后可以再补一次。');
    expect(reboostLine({ date: '2026-10-24', slot_ids: null as never, raise_cents: 0 })).toContain('0 个');
  });
});

describe('SCN-121 raiseToCents', () => {
  it.each([['', 0], [' ', 0], ['10', 1000], ['10.5', 1050], ['0.01', 1], ['-1', null], ['abc', null], ['1.234', null]] as Array<[string, number | null]>)(
    '%j → %s', (y, want) => { expect(raiseToCents(y)).toBe(want); });
});

describe('SCN-137 补招时顺带邀请', () => {
  const base = { date: '2030-01-07', slot_ids: [35], raise_cents: 0 };
  it('邀请了谁写人数与昵称', () => {
    expect(reboostLine({ ...base, invited: [{ user_id: 3, nickname: '小王', task_id: 35 }, { user_id: 4, nickname: '小李', task_id: 35 }] }, true))
      .toBe('已补招 01-07：1 个还在招的名额再推了一次；邀请了 2 个那天有空、做过这类活的人（小王、小李）。6 小时后可以再补一次。');
  });
  it('勾了却没找到人也说一声；没勾不提', () => {
    expect(reboostLine({ ...base, invited: [] }, true)).toBe('已补招 01-07：1 个还在招的名额再推了一次；这天没找到做过这类活、又正好有空的人可邀。6 小时后可以再补一次。');
    expect(reboostLine({ ...base, invited: [] })).toBe('已补招 01-07：1 个还在招的名额再推了一次。6 小时后可以再补一次。');
  });
});
