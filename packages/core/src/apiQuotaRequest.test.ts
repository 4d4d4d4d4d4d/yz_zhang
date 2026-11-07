// API-057（241 号 spec）提额申请的一句话。
import { describe, expect, it } from 'vitest';
import { quotaRequestLine } from './apiQuota';

const base = { id: 3, daily_quota: 5000, days: 30 as number | null, purpose: '接 ERP', decision_note: '', granted_quota: null as number | null,
  granted_days: null as number | null };

describe('API-057 quotaRequestLine', () => {
  it('待批、撤回只写申请的量与状态；长期写「长期」', () => {
    expect(quotaRequestLine({ ...base, status: 'pending' })).toBe('#3 申请每天 5000 次、30 天（接 ERP） · 待批');
    expect(quotaRequestLine({ ...base, days: null, status: 'withdrawn' })).toBe('#3 申请每天 5000 次、长期（接 ERP） · 已撤回');
  });
  it('批准：按申请的不重复写；批的不同写明批了多少；备注带上', () => {
    expect(quotaRequestLine({ ...base, status: 'approved', granted_quota: 5000, granted_days: 30 })).toBe('#3 申请每天 5000 次、30 天（接 ERP） · 已批准');
    expect(quotaRequestLine({ ...base, status: 'approved', granted_quota: 3000, granted_days: null, decision_note: '先长期给 3000' }))
      .toBe('#3 申请每天 5000 次、30 天（接 ERP） · 已批准：批了每天 3000 次、长期（先长期给 3000）');
    expect(quotaRequestLine({ ...base, status: 'approved', granted_quota: 5000, granted_days: 7 }))
      .toBe('#3 申请每天 5000 次、30 天（接 ERP） · 已批准：批了每天 5000 次、7 天');
  });
  it('驳回写明理由', () => {
    expect(quotaRequestLine({ ...base, status: 'rejected', decision_note: '用途不清楚' })).toBe('#3 申请每天 5000 次、30 天（接 ERP） · 没通过：用途不清楚');
  });
});
