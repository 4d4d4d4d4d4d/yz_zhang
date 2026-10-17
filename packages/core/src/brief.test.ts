// SCN-110（194 号 spec）任务详情上的需求九项：同一份数据，对发单人与接单的人换个说法。
import { describe, expect, it } from 'vitest';
import { briefHint } from './brief';

const BRIEF = { missing: 2, items: [
  { name: '用途', ok: true, ask: '用在哪儿？' }, { name: '改稿次数', ok: false, ask: '包含几次修改？' }, { name: '版权授权', ok: false, ask: '版权怎么约定？' }] };

describe('SCN-110 briefHint', () => {
  it('接单的人：报名前可以先问问发单人', () => {
    expect(briefHint(BRIEF, false)).toEqual({ title: '说明里没写的 2 项，报名前可以先问问发单人：',
      lines: ['改稿次数：包含几次修改？', '版权授权：版权怎么约定？'] });
  });
  it('发单人：已写几项、还可以补', () => {
    expect(briefHint(BRIEF, true)?.title).toBe('创作类需求一般写清九项，已写 1/3。还可以补：');
  });
  it('九项都写了、不是创作类、响应不像样：不显示', () => {
    expect(briefHint({ missing: 0, items: [{ name: '用途', ok: true, ask: 'x' }] }, false)).toBeNull();
    expect(briefHint(null, false)).toBeNull();
    expect(briefHint({ missing: 1 } as never, false)).toBeNull();
  });
  it('按 items 数，不信 missing 字段', () => {
    expect(briefHint({ ...BRIEF, missing: 0 }, false)?.lines).toHaveLength(2);
  });
});
