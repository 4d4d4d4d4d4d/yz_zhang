import { describe, expect, it } from 'vitest';
import {
  REPORT_CATEGORY_OPTIONS, reportCategoryLabel, reportStatusLine, reportSubmittedNote, reportTargetLabel,
} from './reports';

describe('RISK-010~014 举报说法（399 号 spec）', () => {
  it('类型与服务端同序，「其他」放最后', () => {
    expect(REPORT_CATEGORY_OPTIONS.map((o) => o.value)).toEqual(
      ['illegal', 'porn', 'fraud', 'harassment', 'infringement', 'other']);
    expect(reportCategoryLabel('fraud')).toBe('诈骗或骗钱');
    expect(reportCategoryLabel('spam')).toBe('其他');
    expect(reportCategoryLabel(undefined)).toBe('其他');
  });

  it('对象名畸形时不显示 undefined', () => {
    expect(reportTargetLabel('message')).toBe('私信');
    expect(reportTargetLabel('nope')).toBe('对象');
    expect(reportTargetLabel(3)).toBe('对象');
  });

  it('重复举报说清已经在处理', () => {
    expect(reportSubmittedNote({ id: 1, status: 'pending', duplicate: true })).toContain('已经举报过');
    expect(reportSubmittedNote({ id: 1, status: 'pending', duplicate: false })).toContain('我的举报');
    expect(reportSubmittedNote(null)).toContain('已提交');
  });

  it('处理结果一行', () => {
    expect(reportStatusLine({ status: 'pending', result: '' })).toBe('处理中');
    expect(reportStatusLine({ status: 'resolved', result: '已下架违规内容' })).toBe('已处理：已下架违规内容');
    expect(reportStatusLine({ status: 'resolved', result: '' })).toBe('已处理：已处理');
    expect(reportStatusLine(null)).toBe('处理中');
  });
});

describe('RISK-010/013 client', () => {
  it('report 不传类型时请求体与以前一样；传了才带 category', async () => {
    const { PlatformClient } = await import('./client');
    const calls: Array<[string, RequestInit]> = [];
    const fetchImpl = (async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      return { ok: true, status: 200, text: async () => JSON.stringify({ id: 1, status: 'pending', items: [], categories: {} }) };
    }) as unknown as typeof fetch;
    const c = new PlatformClient({ baseUrl: 'http://x', getToken: () => 't', fetchImpl });
    await c.report('task', 3, '不当');
    await c.report('user', 4, '骗钱', 'fraud');
    await c.myReports();
    expect(JSON.parse(String(calls[0][1].body))).toEqual({ target_type: 'task', target_id: 3, reason: '不当' });
    expect(JSON.parse(String(calls[1][1].body))).toEqual({ target_type: 'user', target_id: 4, reason: '骗钱', category: 'fraud' });
    expect(calls[2][0]).toBe('http://x/api/v1/reports/mine');
    expect(calls[2][1].method).toBe('GET');
  });
});

describe('RISK-016 处置队列时限（401 号 spec）', () => {
  it('等了多久、时限多少、超没超；字段缺了不显示', async () => {
    const { reportSlaLine } = await import('./reports');
    expect(reportSlaLine({ waited_hours: 5, sla_hours: 24, overdue: false })).toBe('已等 5 小时（24 小时内处理）');
    expect(reportSlaLine({ waited_hours: 80, sla_hours: 72, overdue: true })).toBe('已等 80 小时（72 小时内处理） · 已超时');
    expect(reportSlaLine({})).toBe('');
    expect(reportSlaLine(null)).toBe('');
  });

  it('adminReports 不传排序时地址与以前一样', async () => {
    const { PlatformClient } = await import('./client');
    const urls: string[] = [];
    const fetchImpl = (async (url: string) => { urls.push(url); return { ok: true, status: 200, text: async () => '[]' }; }) as unknown as typeof fetch;
    const c = new PlatformClient({ baseUrl: 'http://x', getToken: () => 't', fetchImpl });
    await c.adminReports();
    await c.adminReports('pending', 'urgent');
    expect(urls).toEqual(['http://x/api/v1/admin/reports?status=pending', 'http://x/api/v1/admin/reports?status=pending&sort=urgent']);
  });
});
