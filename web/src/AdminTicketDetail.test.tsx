// ESCA-058（221 号 spec）后台工单台「看完整往来」：接手的人看得到提单人原话与之前每一句往来、谁说的。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '客服甲', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['support'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = { id: 7, user_id: 9, subject: '提现没到账', body: '三天了', created_at: '2026-10-13T00:00:00Z', assignee_id: 1,
  assignee_nickname: '客服甲', escalation_level: 0, escalation_label: '', waited_hours: 5, sla_hours: 24, overdue_hours: 0,
  first_responded: true, first_response_hours: 4, first_response_overdue: false, replies_count: 1,
  last_user_reply: '尾号 1234', last_user_reply_at: '2026-10-14T00:00:00Z', awaiting_staff: true,
  category: 'funds', priority: 'urgent', priority_label: '加急' };
const DETAIL = { ...ROW, user_nickname: '小林', status: 'open', reply: '', resolved_at: null,
  thread: [
    { body: '在查了，请稍等', is_staff: true, author: '客服乙', created_at: '2026-10-13T02:00:00Z' },
    { body: '尾号 1234', is_staff: false, author: '提单人', created_at: '2026-10-14T00:00:00Z' },
  ] };
type Call = { method: string; path: string };

function open(routes: Record<string, unknown>, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path: p });
    const body = p === '/users/me' ? ADMIN : p in routes ? routes[p] : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-058 后台看完整往来', () => {
  it('点开看到提单人、原话与每一句往来（客服写出是谁）', async () => {
    const calls: Call[] = [];
    open({ '/admin/tickets': [ROW], '/admin/tickets/7': DETAIL }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '看完整往来' }));
    const box = await screen.findByTestId('ticket-thread-7');
    expect(calls.some((c) => c.path === '/admin/tickets/7')).toBe(true);
    expect(box.textContent).toContain('提单人：小林');
    expect(box.textContent).toContain('三天了');
    expect(box.textContent).toContain('客服 客服乙');
    expect(box.textContent).toContain('在查了，请稍等');
    expect(box.textContent).toContain('提单人（');
    // 再点一下收起
    fireEvent.click(screen.getByRole('button', { name: '收起往来' }));
    await waitFor(() => expect(screen.queryByTestId('ticket-thread-7')).toBeNull());
  });

  it('还没有往来的写明，不留一块空白', async () => {
    open({ '/admin/tickets': [ROW], '/admin/tickets/7': { ...DETAIL, thread: [] } }, []);
    fireEvent.click(await screen.findByRole('button', { name: '看完整往来' }));
    expect((await screen.findByTestId('ticket-thread-7')).textContent).toContain('还没有往来。');
  });
});
