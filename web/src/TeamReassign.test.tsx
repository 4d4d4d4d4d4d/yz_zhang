// TEAM-073（243 号 spec）团队页待批申请「改派给…」：只有所有者看得到；候选只有所有者 / 管理员、去掉发起人与当前指派的人。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const TEAM = { id: 9, name: '小团队', owner_id: 2, company_name: '', tax_number: '', verify_status: 'none', balance_cents: 0, my_role: 'owner',
  my_spend_limit_cents: 0, invoice_block: '', monthly_budget_cents: 0, month_spent_cents: 0, my_month_spent_cents: 0, approval_mode: 'rotate',
  members: [{ user_id: 2, role: 'owner', spend_limit_cents: 0, nickname: '我' }, { user_id: 5, role: 'admin', spend_limit_cents: 0, nickname: '主管' },
    { user_id: 6, role: 'admin', spend_limit_cents: 0, nickname: '财务主管' }, { user_id: 7, role: 'member', spend_limit_cents: 0, nickname: '员工' }] };
const SPEND = { id: 21, requester_id: 7, amount_cents: 200000, purpose: '物料', status: 'pending', task_id: null, decided_by: null, decision_reason: '',
  created_at: '2026-10-15T00:00:00Z', can_decide: true, returned_cents: 0, returnable_cents: 0, assignee_id: 5 };
type Call = { method: string; path: string; body: unknown };

function open(team: unknown, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : null });
    const body = p === '/users/me' ? ME : p === '/teams/mine' ? [team] : p === '/teams/9' ? team : p === '/teams/9/spends' ? [SPEND]
      : p === '/teams/9/spends/21/assign' ? { id: 21, assignee_id: 6, assignee_nickname: '财务主管', previous_assignee_id: 5 } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/teams']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('TEAM-073 改派', () => {
  it('所有者：候选是别的审批人；选了就发请求并提示', async () => {
    const calls: Call[] = [];
    open(TEAM, calls);
    fireEvent.click(await screen.findByText('打开'));
    const sel = await screen.findByLabelText('改派 #21');
    const options = Array.from(sel.querySelectorAll('option')).map((o) => o.textContent);
    expect(options).toEqual(['改派给…', '我', '财务主管']);
    fireEvent.change(sel, { target: { value: '6' } });
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/teams/9/spends/21/assign')?.body).toEqual({ assignee_id: 6 }));
    expect((await screen.findByTestId('spend-notice')).textContent).toBe('已改派给 财务主管，已通知他');
  });

  it('管理员看不到改派', async () => {
    open({ ...TEAM, my_role: 'admin' }, []);
    fireEvent.click(await screen.findByText('打开'));
    await screen.findByText(/轮到 主管 审批/);
    expect(screen.queryByLabelText('改派 #21')).toBeNull();
  });
});
