// ESCA-066（248 号 spec）工单台「客服状态」：只有主管看得到；点开才加载；暂停的人能替他恢复。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = (roles: string[]) => ({ id: 1, phone: '138****0001', nickname: '主管', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: roles, credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' });
const ROW = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
  first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
  last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急' };
const AGENTS = [
  { user_id: 2, nickname: '客服甲', categories: ['funds'], declared: true, auto_assign: true, paused_until: '2026-10-22T10:00:00Z', open_tickets: 0 },
  { user_id: 3, nickname: '客服乙', categories: ['funds', 'account', 'general'], declared: false, auto_assign: false, paused_until: null, open_tickets: 4 },
];
type Call = { method: string; path: string; body?: unknown };

function open(roles: string[], calls: Call[]) {
  localStorage.setItem('token', 'tok');
  let resumed = false;
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    if (method === 'DELETE' && p === '/admin/support/agents/2/pause') resumed = true;
    const body = p === '/users/me' ? ME(roles) : p === '/admin/tickets' ? [ROW]
      : p === '/admin/support/agents' ? (resumed ? [{ ...AGENTS[0], paused_until: null }, AGENTS[1]] : AGENTS)
      : p === '/admin/support/agents/2/pause' ? { user_id: 2, paused_until: null }
      : p === '/admin/support/agents/3/pause' ? { user_id: 3, paused_until: '2026-10-22T14:00:00Z' }
      : p === '/admin/admins' ? { admins: [] }
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-066 客服状态', () => {
  it('主管点开看到每位客服的状态；暂停的能替他恢复', async () => {
    const calls: Call[] = [];
    open(['super'], calls);
    const btn = await screen.findByText('看客服状态');
    expect(calls.some((c) => c.path === '/admin/support/agents')).toBe(false);
    fireEvent.click(btn);
    const box = await screen.findByLabelText('客服状态');
    expect(within(box).getByTestId('agent-2').textContent).toContain('暂停到');
    expect(within(box).getByTestId('agent-3').textContent).toContain('都管（没选）');
    expect(within(box).getByTestId('agent-3').textContent).toContain('在岗');
    expect(within(box).getByTestId('agent-3').textContent).toContain('4');
    expect(within(within(box).getByTestId('agent-3')).queryByText('替他恢复')).toBeNull();
    fireEvent.click(within(within(box).getByTestId('agent-2')).getByText('替他恢复'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/admin/support/agents/2/pause')).toBe(true));
    expect((await within(box).findByRole('status')).textContent).toBe('已恢复 客服甲 的接单，已通知他');
    await waitFor(() => expect(within(box).getByTestId('agent-2').textContent).toContain('在岗'));
  });

  it('普通客服看不到', async () => {
    open(['support'], []);
    await screen.findByLabelText('我负责的类别').catch(() => null);
    await screen.findByText('钱没到账');
    expect(screen.queryByText('看客服状态')).toBeNull();
  });

  it('ESCA-067 主管替在岗的客服安排暂停：问几小时、带上小时数', async () => {
    const calls: Call[] = [];
    open(['super'], calls);
    fireEvent.click(await screen.findByText('看客服状态'));
    const box = await screen.findByLabelText('客服状态');
    expect(within(within(box).getByTestId('agent-2')).queryByText('替他暂停')).toBeNull();
    vi.spyOn(window, 'prompt').mockReturnValueOnce('4');
    fireEvent.click(within(within(box).getByTestId('agent-3')).getByText('替他暂停'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/support/agents/3/pause')?.body).toEqual({ hours: 4 }));
    expect((await within(box).findByRole('status')).textContent).toBe('已为 客服乙 暂停接单 4 小时，已通知他');
  });
});

