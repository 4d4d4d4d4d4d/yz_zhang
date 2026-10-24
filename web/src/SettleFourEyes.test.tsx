// SEC-061c / PAY-042b 大额平台结算的四眼在后台（148 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '财务', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['finance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const REQ = { id: 5, amount_cents: 800000, memo: '季度对公结算', requested_by: 7, status: 'awaiting_second', decided_by: null,
  decision_reason: '', created_at: '2026-10-15T00:00:00Z', decided_at: null };

function open(calls: Array<{ method: string; path: string; body: unknown }>, pending: unknown[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/platform-finance' ? { balance_cents: 900000, total_fee_cents: 900000, settled_cents: 0, fee_count: 4 }
      : path === '/admin/platform-finance/settle-requests' ? pending
      : path === '/admin/platform-finance/settle' ? { status: 'awaiting_second', request_id: 6, amount_cents: 600000, balance_cents: 900000,
          message: '达到 ¥10000.00 的结算要另一位财务确认后才会划出' }
      : path === '/admin/platform-finance/periods' ? { granularity: 'month', periods: [] }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : method === 'POST' ? { ...REQ, status: 'settled', balance_cents: 100000 } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SEC-061c 大额结算的四眼', () => {
  it('大额结算说清「要另一位财务确认、钱还没动」', async () => {
    open([], []);
    fireEvent.change(await screen.findByPlaceholderText('结算金额（元）'), { target: { value: '6000' } });
    fireEvent.click(screen.getByRole('button', { name: '结算划出' }));
    expect(await screen.findByText('达到 ¥10000.00 的结算要另一位财务确认后才会划出')).toBeTruthy();
  });

  it('待确认的结算列出发起人；确认与驳回打到各自的端点', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    open(calls, [REQ]);
    const box = await screen.findByLabelText('待确认的结算');
    expect(box.textContent).toContain('由财务 #7');
    expect(box.textContent).toContain('钱还没划出');
    fireEvent.click(within(box).getByText('确认划出'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/platform-finance/settle-requests/5/approve')).toBe(true));
    vi.spyOn(window, 'prompt').mockReturnValue('金额与对账单不符');
    fireEvent.click(within(box).getByText('驳回 / 撤回'));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/platform-finance/settle-requests/5/reject')?.body).toEqual({ reason: '金额与对账单不符' }));
  });
});
