// TEAM-071（230 号 spec）团队页支出列表「提醒退回」：所有者 / 管理员可见、写上次提醒时间；普通成员看不到。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const TEAM = { id: 9, name: '小团队', owner_id: 2, company_name: '', tax_number: '', verify_status: 'none', balance_cents: 0, my_role: 'owner',
  my_spend_limit_cents: 0, invoice_block: '', monthly_budget_cents: 0, month_spent_cents: 0, my_month_spent_cents: 0,
  members: [{ user_id: 2, role: 'owner', spend_limit_cents: 0, nickname: '我' }] };
const S = (id: number, extra: Record<string, unknown>) => ({ id, requester_id: 7, amount_cents: 8000, purpose: '物料', status: 'executed',
  task_id: null, decided_by: 2, decision_reason: '', created_at: '2026-10-15T00:00:00Z', can_decide: false, returned_cents: 0, returnable_cents: 8000, ...extra });
type Call = { method: string; path: string };

function open(team: unknown, spends: unknown[], calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p });
    const body = p === '/users/me' ? ME : p === '/teams/mine' ? [team] : p === '/teams/9' ? team : p === '/teams/9/spends' ? spends
      : p === '/teams/9/spends/21/ask-return' ? { id: 21, returnable_cents: 8000, return_asked_at: '2026-10-22T02:00:00Z' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/teams']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('TEAM-071 提醒退回', () => {
  it('所有者：有可退的才显示，写上次提醒时间；点了发请求并提示', async () => {
    const calls: Call[] = [];
    open(TEAM, [S(21, { return_asked_at: '2026-10-20T02:00:00Z' }), S(22, { returnable_cents: 0, returned_cents: 8000 })], calls);
    fireEvent.click(await screen.findByText('打开'));
    const btn = await screen.findByTestId('ask-return-21');
    expect(btn.textContent).toContain('提醒退回（上次 ');
    expect(screen.queryByTestId('ask-return-22')).toBeNull();
    fireEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/teams/9/spends/21/ask-return')).toBe(true));
    expect((await screen.findByTestId('spend-notice')).textContent).toBe('已提醒 #7 退回没用完的拨款');
  });

  it('普通成员看不到', async () => {
    open({ ...TEAM, my_role: 'member' }, [S(21, {})], []);
    fireEvent.click(await screen.findByText('打开'));
    await screen.findByText('支出申请');
    expect(screen.queryByTestId('ask-return-21')).toBeNull();
  });
});
