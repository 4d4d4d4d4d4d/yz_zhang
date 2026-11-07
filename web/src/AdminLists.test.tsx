// ADMIN-061 审计日志与 PAY-043 提现复核台的筛选、总数、导出（143 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '合规', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['super'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const AUDIT = { id: 3, admin_id: 7, action: 'withdraw_approve', target_type: 'withdraw', target_id: 5, detail: '大额', created_at: '2026-10-01T00:00:00Z' };

function open(urls: string[], totals: Record<string, string> = {}) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    urls.push(full);
    const path = full.split('?')[0];
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/audit-log' ? [AUDIT]
      : path === '/admin/audit-log/export' ? { filename: 'audit-log.csv', rows: 2, total: 12000, truncated: true, timezone: '北京时间 UTC+8', csv: 'a,b\n' }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    const key = Object.keys(totals).find((k) => full.startsWith(k));
    return { ok: true, status: 200, text: async () => JSON.stringify(body),
      headers: { get: (h: string) => (h === 'X-Total-Count' && key ? totals[key] : null) } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ADMIN-061 审计日志', () => {
  it('按管理员、对象、日期筛选；显示总条数与页码，翻页带 offset', async () => {
    const urls: string[] = [];
    open(urls, { '/admin/audit-log': '120' });
    await waitFor(() => expect(screen.getByTestId('audit-pages').textContent).toContain('第 1 / 3 页 · 共 120 条'));
    fireEvent.change(screen.getByLabelText('管理员编号'), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText('对象类型'), { target: { value: 'withdraw' } });
    fireEvent.change(screen.getByLabelText('开始日期'), { target: { value: '2026-10-01' } });
    fireEvent.click(within(screen.getByLabelText('管理员审计日志')).getByText('查询'));
    await waitFor(() => expect(urls.some((u) => u.startsWith('/admin/audit-log?') && u.includes('admin_id=7')
      && u.includes('target_type=withdraw') && u.includes('since=2026-10-01T00%3A00%3A00%2B08%3A00'))).toBe(true));
    fireEvent.click(within(screen.getByLabelText('管理员审计日志')).getByText('下一页'));
    await waitFor(() => expect(urls.some((u) => u.includes('offset=50'))).toBe(true));
  });

  it('导出 CSV：说清时区、截断与「导出已记入审计」', async () => {
    const urls: string[] = [];
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    open(urls);
    fireEvent.click(await screen.findByText('导出 CSV'));
    const msg = await screen.findByText(/已导出 2 行/);
    expect(msg.textContent).toContain('北京时间 UTC+8');
    expect(msg.textContent).toContain('共 12000 行');
    expect(msg.textContent).toContain('导出已记入审计');
  });
});

describe('PAY-043 提现复核台', () => {
  it('筛选进查询串、显示两个队列的总数', async () => {
    const urls: string[] = [];
    open(urls, { '/wallet/withdraw-requests?status=pending': '230', '/wallet/withdraw-requests?status=awaiting_second': '4' });
    await waitFor(() => expect(screen.getByTestId('wd-totals').textContent).toContain('待初审 230 笔，待二次确认 4 笔'));
    fireEvent.change(screen.getByLabelText('金额下限'), { target: { value: '5000' } });
    fireEvent.click(screen.getByLabelText('只看命中风控的'));
    fireEvent.click(screen.getByLabelText('先看金额大的'));
    await waitFor(() => expect(urls).toContain('/wallet/withdraw-requests?status=pending&min_amount_cents=500000&flagged_only=true&sort=largest'));
  });
});
