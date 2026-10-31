// SEC-061f / PAY-042c 四眼按金额分级在后台的提示（155 号 spec）。
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

const WD = { id: 9, user_id: 3, amount_cents: 15000000, status: 'awaiting_second', created_at: '2026-10-15T00:00:00Z', first_approved_by: 2,
  needs_super_second: true, nickname: '提现的人', is_verified: true, registered_at: '2026-01-01T00:00:00Z', withdrawn_total_cents: 0, flags: [] };

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
      : path === '/wallet/withdraw-requests' ? [WD]
      : path === '/admin/aml/activities' ? { items: [], note: '' } : method === 'POST' ? { ...REQ, status: 'settled', balance_cents: 100000 } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SEC-061f 四眼按金额分级', () => {
  it('大额结算与大额提现都标出「须超级管理员确认」，小额的不标', async () => {
    open([], [{ ...REQ, id: 5, needs_super_second: true }, { ...REQ, id: 6, amount_cents: 20000, needs_super_second: false }]);
    expect((await screen.findByTestId('settle-super-5')).textContent).toContain('须超级管理员确认');
    expect(screen.queryByTestId('settle-super-6')).toBeNull();
    expect((await screen.findAllByTestId('withdraw-super-9'))[0].textContent).toContain('第二人须是超级管理员');
  });
});
