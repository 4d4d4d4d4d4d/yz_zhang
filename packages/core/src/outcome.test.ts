// OUT-052（444 号 spec）发单页「按结果计价」的请求体，两端共用。
import { describe, expect, it } from 'vitest';
import { outcomeCriteria, outcomePayload } from './outcome';

describe('outcomeCriteria', () => {
  it('关键词按逗号顿号换行拆开、去空去重，每个变成一条平台判定指标', () => {
    expect(outcomeCriteria(' 已自测，已附文档、\n已自测,, ')).toEqual([
      { text: '交付说明写明「已自测」', kind: 'auto', check: { op: 'contains', value: '已自测' } },
      { text: '交付说明写明「已附文档」', kind: 'auto', check: { op: 'contains', value: '已附文档' } },
    ]);
  });
});

describe('outcomePayload', () => {
  it('没关键词、分档只填一半、上限和分档都没写：当场说清', () => {
    expect(outcomePayload({ keywords: ' ', bonusYuan: '50', tiers: [] })).toHaveProperty('error');
    expect(outcomePayload({ keywords: '已自测', bonusYuan: '', tiers: [{ min_passed: '1', yuan: '' }] }))
      .toEqual({ error: '每一档都要写「通过几条」和「加付多少元」' });
    expect(outcomePayload({ keywords: '已自测', bonusYuan: '0', tiers: [{ min_passed: '', yuan: '' }] }))
      .toEqual({ error: '写一个加付上限（元），或者写分档' });
  });

  it('只写上限：带 bonus_cents；写了分档：带 bonus_tiers、不带 bonus_cents（服务端取最高一档），整行空的忽略', () => {
    expect(outcomePayload({ keywords: '已自测', bonusYuan: '50.5', tiers: [] }))
      .toEqual({ acceptance_criteria: outcomeCriteria('已自测'), bonus_cents: 5050 });
    const p = outcomePayload({ keywords: '已自测，已部署', bonusYuan: '999',
      tiers: [{ min_passed: '1', yuan: '20' }, { min_passed: '', yuan: '' }, { min_passed: '2', yuan: '90' }] });
    expect(p).toEqual({ acceptance_criteria: outcomeCriteria('已自测，已部署'),
      bonus_tiers: [{ min_passed: 1, bonus_cents: 2000 }, { min_passed: 2, bonus_cents: 9000 }] });
    expect(p).not.toHaveProperty('bonus_cents');
  });
});
