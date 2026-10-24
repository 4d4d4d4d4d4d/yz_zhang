// PAY-042d 税款缴库前的人工确认在后台（287 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '财务', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['finance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const DRAFT = { id: 9, amount_cents: 12345600, status: 'awaiting_confirm', decided_by: null, decision_reason: '',
  created_at: '2026-10-24T00:00:00Z', decided_at: null };

function open(calls: Array<{ method: string; path: string; body: unknown }>, pending: unknown[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/platform-finance' ? { balance_cents: 900000, total_fee_cents: 900000, settled_cents: 0, fee_count: 4 }
      : path === '/finance/tax-remits' ? pending
      : path === '/finance/tax-remits/9/confirm' ? { ...DRAFT, status: 'remitted', decided_by: 1, balance_cents: 4500 }
      : path === '/finance/tax-remits/9/reject' ? { ...DRAFT, status: 'rejected', decided_by: 1, decision_reason: '与申报表差 12 元' }
      : path === '/admin/platform-finance/periods' ? { granularity: 'month', periods: [] }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('PAY-042d 待确认的缴库', () => {
  it('没有草稿时不出现这一块', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    open(calls, []);
    await waitFor(() => expect(calls.some((c) => c.path === '/finance/tax-remits')).toBe(true));
    expect(screen.queryByLabelText('待确认的缴库')).toBeNull();
  });

  it('列出草稿金额、提醒先与申报数核对；确认后说出专户余额', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    open(calls, [DRAFT]);
    const box = await screen.findByLabelText('待确认的缴库');
    expect(box.textContent).toContain('¥123456.00');
    expect(box.textContent).toContain('请与本期申报数核对');
    fireEvent.click(within(box).getByText('核对无误，确认缴库'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/finance/tax-remits/9/confirm')).toBe(true));
    expect((await within(box).findByRole('status')).textContent).toBe('已确认缴库 ¥123456.00，专户余额 ¥45.00');
  });

  it('驳回要写原因，带着原因打到驳回端点；取消就不发', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    open(calls, [DRAFT]);
    const box = await screen.findByLabelText('待确认的缴库');
    const ask = vi.spyOn(window, 'prompt').mockReturnValueOnce(null).mockReturnValueOnce('与申报表差 12 元');
    fireEvent.click(within(box).getByText('驳回'));
    expect(calls.some((c) => c.path === '/finance/tax-remits/9/reject')).toBe(false);
    fireEvent.click(within(box).getByText('驳回'));
    await waitFor(() => expect(calls.find((c) => c.path === '/finance/tax-remits/9/reject')?.body).toEqual({ reason: '与申报表差 12 元' }));
    ask.mockRestore();
  });
});
