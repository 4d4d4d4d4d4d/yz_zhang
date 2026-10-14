// TEAM-065 团队成员管理（136 号 spec）：只有所有者能加人、改角色与额度、移出。
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
  my_spend_limit_cents: 0, invoice_block: '', monthly_budget_cents: 0, month_spent_cents: 0, my_month_spent_cents: 0,
  members: [{ user_id: 2, role: 'owner', spend_limit_cents: 0, nickname: '我' }, { user_id: 5, role: 'member', spend_limit_cents: 50000, nickname: '小林' }],
});
type Call = { method: string; path: string; body?: unknown };

function open(role: string, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const routes: Record<string, unknown> = {
    '/users/me': ME, '/teams/mine': [{ ...TEAM(role), my_role: role, my_spend_limit_cents: 0 }], '/teams/9': TEAM(role), '/teams/9/spends': [],
    'POST /teams/9/members': { team_id: 9, user_id: 7, role: 'member', spend_limit_cents: 30000 },
    'DELETE /teams/9/members/5': { removed: 5 },
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

describe('TEAM-065 团队成员', () => {
  it('所有者：看到成员昵称与额度，加人、移出（先确认）', async () => {
    const calls = open('owner');
    fireEvent.click(await screen.findByText('打开'));
    const box = await screen.findByLabelText('团队成员');
    expect(box.textContent).toContain('小林');
    expect(box.textContent).toContain('¥500.00');
    fireEvent.change(screen.getByLabelText('成员用户编号'), { target: { value: '7' } });
    fireEvent.change(screen.getByLabelText('月度额度'), { target: { value: '300' } });
    fireEvent.click(screen.getByRole('button', { name: '加入团队' }));
    await screen.findByText('已加入');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '移出' }));
    await screen.findByText('已移出');
    await waitFor(() => expect(calls.filter((c) => c.method !== 'GET').map((c) => [c.method, c.path, c.body])).toEqual([
      ['POST', '/teams/9/members', { user_id: 7, role: 'member', spend_limit_cents: 30000 }],
      ['DELETE', '/teams/9/members/5', undefined],
    ]));
  });

  it('不是所有者：只能看', async () => {
    open('member');
    fireEvent.click(await screen.findByText('打开'));
    await screen.findByText('只有团队所有者能管理成员。');
    expect(screen.queryByRole('button', { name: '加入团队' })).toBeNull();
  });
});
