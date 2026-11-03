// TEAM-056（370 号 spec）：团队预算池按每月几号重置。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [], is_verified: true,
  is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2' };
const TEAM = (role: string) => ({
  id: 9, name: '小团队', owner_id: 2, company_name: '', tax_number: '', verify_status: 'none', balance_cents: 0, my_role: role,
  my_spend_limit_cents: 0, invoice_block: '', monthly_budget_cents: 300000, month_spent_cents: 50000, my_month_spent_cents: 0,
  budget_cycle_day: 25, budget_cycle_starts_at: '2026-10-25T00:00:00+00:00', budget_cycle_resets_at: '2026-11-25T12:00:00+00:00',
  members: [{ user_id: 2, role: 'owner', spend_limit_cents: 0, nickname: '我' }, { user_id: 5, role: 'member', spend_limit_cents: 50000, nickname: '小林' }],
});
type Call = { method: string; path: string; body?: unknown };

function open(role: string, calls: Call[] = [], extra: Record<string, unknown> = {}) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = {
    '/users/me': ME, '/teams/mine': [{ ...TEAM(role), my_role: role, my_spend_limit_cents: 0 }], '/teams/9': TEAM(role), '/teams/9/spends': [],
    'POST /teams/9/budget': { id: 9, monthly_budget_cents: 300000, month_spent_cents: 50000, budget_cycle_day: 10 },
    ...extra,
  };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/teams']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  return calls;
}


describe('TEAM-056 预算池账期（370 号 spec）', () => {
  it('所有者：看到每月几号重置与下次重置，改账期时金额不变、只带账期', async () => {
    const calls = open('owner');
    fireEvent.click(await screen.findByText('打开'));
    const line = await screen.findByTestId('team-budget-cycle');
    expect(line.textContent).toContain('预算池账期：每月 25 日重置 · 下次 2026/11/25');
    fireEvent.change(screen.getByLabelText('预算池每月几号重置'), { target: { value: '10' } });
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/teams/9/budget')).toBe(true));
    const c = calls.find((x) => x.method === 'POST' && x.path === '/teams/9/budget')!;
    expect(c.body).toEqual({ monthly_budget_cents: 300000, budget_cycle_day: 10 });
  });

  it('成员只看不改；老服务端没有账期字段时整行不显示', async () => {
    open('member');
    fireEvent.click(await screen.findByText('打开'));
    expect((await screen.findByTestId('team-budget-cycle')).textContent).toContain('每月 25 日重置');
    expect(screen.queryByLabelText('预算池每月几号重置')).toBeNull();
  });

  it('老服务端：没有账期字段', async () => {
    const team = { ...TEAM('owner'), budget_cycle_day: undefined, budget_cycle_starts_at: undefined, budget_cycle_resets_at: undefined };
    open('owner', [], { '/teams/9': team });
    fireEvent.click(await screen.findByText('打开'));
    await screen.findByTestId('team-budget');
    expect(screen.queryByTestId('team-budget-cycle')).toBeNull();
  });
});
