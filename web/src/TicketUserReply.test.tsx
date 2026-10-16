// ESCA-056 提单人追加回复（166 号 spec）：我的工单里补充、已结的会重新打开；后台看到提单人补了什么、在等谁。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 9, phone: '138****0009', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, admin_roles: [], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r9' };
const T = { id: 3, subject: '提现没到账', body: '三天了', status: 'resolved', reply: '已处理', created_at: '2026-10-13T00:00:00Z',
  claimed: true, escalation_level: 0, escalation_label: '', waited_hours: 2, sla_hours: 24, overdue_hours: 0,
  first_responded: true, first_response_hours: 4, first_response_overdue: false,
  replies: [{ body: '已处理', is_staff: true, created_at: '2026-10-13T01:00:00Z' }] };
type Call = { method: string; path: string; body?: unknown };

function open(path: string, me: unknown, routes: Record<string, unknown>, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    const body = p === '/users/me' ? me : key ? routes[key] : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-056 提单人追加回复', () => {
  it('已结的工单补充后重新打开，往来里有「我」说的这句', async () => {
    const calls: Call[] = [];
    const after = { ...T, status: 'open', reopened: true,
      replies: [...T.replies, { body: '还是没到账', is_staff: false, created_at: '2026-10-14T00:00:00Z' }] };
    open('/support', ME, { 'GET /support/tickets': [T], 'POST /support/tickets/3/replies': after }, calls);
    fireEvent.change(await screen.findByLabelText('补充工单 3'), { target: { value: '还是没到账' } });
    fireEvent.click(screen.getByRole('button', { name: '补充' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/support/tickets/3/replies')?.body).toEqual({ body: '还是没到账' }));
    expect(await screen.findByText('已补充，工单 #3 重新打开')).toBeTruthy();
    expect(screen.getByTestId('ticket-replies-3').textContent).toContain('我（');
  });

  it('后台工单台：看到提单人补了什么，标出「等你回」', async () => {
    const calls: Call[] = [];
    const ADMIN = { ...ME, id: 1, is_admin: true, admin_roles: ['support'] };
    const ROW = { id: 7, user_id: 9, subject: '提现没到账', body: '急', created_at: '2026-10-13T00:00:00Z', assignee_id: 1,
      assignee_nickname: '客服', escalation_level: 0, escalation_label: '', waited_hours: 5, sla_hours: 24, overdue_hours: 0,
      first_responded: true, first_response_hours: 4, first_response_overdue: false, replies_count: 1,
      last_user_reply: '补充：银行卡尾号 1234', last_user_reply_at: '2026-10-14T00:00:00Z', awaiting_staff: true };
    open('/admin', ADMIN, { '/admin/tickets': [ROW] }, calls);
    expect((await screen.findByTestId('ticket-user-reply-7')).textContent).toContain('银行卡尾号 1234');
    expect(screen.getByText(/提单人补充了，等你回/)).toBeTruthy();
  });
});
