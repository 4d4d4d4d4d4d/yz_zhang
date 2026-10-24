// SCN-133（211 号 spec）服务包发单模板的预填：带清单的模板再加上门次数与清单。两端共用。
import { describe, expect, it } from 'vitest';
import { templatePrefill, templatePublishQuery } from './packTemplates';

const BASE = { key: 'v', title: '异地代看房', category: '跑腿', description: '只看、拍、问' };

describe('SCN-133 templatePrefill', () => {
  it('带清单的模板：上门次数与清单用顿号连起来', () => {
    expect(templatePrefill({ ...BASE, visits_planned: 1, visit_checklist: ['门牌', ' ', '水电表'] }))
      .toEqual({ title: '异地代看房', category: '跑腿', description: '只看、拍、问', visits: '1', checklist: '门牌、水电表' });
  });
  it('没有清单的模板与以前一样只带三项', () => {
    expect(templatePublishQuery(BASE)).toBe(new URLSearchParams({ title: '异地代看房', category: '跑腿', description: '只看、拍、问' }).toString());
    expect(templatePrefill({ ...BASE, visits_planned: 0 }).visits).toBe('');
  });
});
