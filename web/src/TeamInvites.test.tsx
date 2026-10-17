// TEAM-066 团队邀请链接在网页上（147 号 spec）。
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
type Call = { method: string; path: string; body?: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('TEAM-066 团队邀请链接', () => {
  it('所有者生成链接（只显示一次）、看到状态、可作废', async () => {
    const calls = open('/teams', { '/users/me': ME, '/teams/mine': [TEAM], '/teams/9': TEAM, '/teams/9/spends': [],
      '/teams/9/invite-links': [{ id: 3, spend_limit_cents: 10000, uses: 0, max_uses: 1, expires_at: '2026-10-22T00:00:00Z', created_at: '2026-10-15T00:00:00Z', state: 'active' }],
      'POST /teams/9/invite-links': { id: 4, token: 'tk4', path: '/teams/join/tk4', warning: '', state: 'active', spend_limit_cents: 30000,
        uses: 0, max_uses: 2, expires_at: '2026-10-22T00:00:00Z', created_at: '2026-10-15T00:00:00Z' },
      'POST /teams/9/invite-links/3/revoke': {} });
    fireEvent.click(await screen.findByText('打开'));
    const box = await screen.findByLabelText('邀请链接');
    await waitFor(() => expect(box.textContent).toContain('已用 0/1 · 有效'));
    fireEvent.change(screen.getByLabelText('链接的月度额度'), { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('可用次数'), { target: { value: '2' } });
    fireEvent.click(screen.getByText('生成邀请链接（7 天有效）'));
    expect((await screen.findByTestId('fresh-invite')).textContent).toContain('/teams/join/tk4');
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ spend_limit_cents: 30000, max_uses: 2 });
    fireEvent.click(screen.getByText('作废'));
    await waitFor(() => expect(calls.some((c) => c.path === '/teams/9/invite-links/3/revoke')).toBe(true));
  });

  it('点开链接：先说清楚团队、邀请人与额度，再自己加入', async () => {
    const calls = open('/teams/join/tk9', { '/users/me': ME,
      '/team-invites/tk9': { team_id: 5, team_name: '某某工作室', inviter_nickname: '老板', role: 'member', spend_limit_cents: 30000,
        expires_at: '2026-10-22T00:00:00Z', already_member: false },
      'POST /team-invites/tk9/accept': { team_id: 5, user_id: 2, role: 'member', spend_limit_cents: 30000 } });
    const card = await screen.findByLabelText('团队邀请');
    await waitFor(() => expect(card.textContent).toContain('老板 邀请你加入「某某工作室」'));
    expect(card.textContent).toContain('¥300.00');
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.click(screen.getByText('加入团队'));
    await screen.findByText(/已加入/);
  });
});
