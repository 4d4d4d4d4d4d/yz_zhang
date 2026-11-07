// ESCA-060（229 号 spec）自选加急的滥用提示：选了加急类别才显示；提交后写明照旧按加急处理；后台写提单人的记录。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 9, phone: '138****0009', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, admin_roles: [], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r9' };
const MSG = '你最近 90 天选了加急的 3 张工单里，有 2 张被客服改回了一般。加急只留给资金没到账、账号登录或安全这类事：选错会让真正着急的人排在后面。';

function open(path: string, me: unknown, routes: Record<string, unknown>) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    const body = p === '/users/me' ? me : key ? routes[key] : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-060 自选加急的滥用提示', () => {
  it('选一般不显示，选资金类才显示；提交后写明照旧按加急处理', async () => {
    open('/support', ME, { '/support/tickets/urgent-hint': { days: 90, self_urgent: 3, downgraded: 2, message: MSG },
      'GET /support/tickets': [], 'POST /support/tickets': { id: 4, status: 'open', reply: '', priority: 'urgent', priority_note: MSG } });
    await screen.findByLabelText('工单类别');
    expect(screen.queryByTestId('urgent-hint')).toBeNull();
    fireEvent.change(screen.getByLabelText('工单类别'), { target: { value: 'funds' } });
    expect((await screen.findByTestId('urgent-hint')).textContent).toBe(MSG);
    fireEvent.change(screen.getByPlaceholderText('问题一句话概括'), { target: { value: '提现没到账' } });
    fireEvent.click(screen.getByRole('button', { name: '提交工单' }));
    expect((await screen.findByTestId('ticket-created-note')).textContent).toBe(`已提交（按加急处理）。${MSG}`);
  });

  it('后台队列写提单人近 90 天自选加急被改回的记录；没被改回过的不写', async () => {
    const ADMIN = { ...ME, id: 1, is_admin: true, admin_roles: ['support'] };
    const ROW = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
      assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
      first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
      last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急',
      requester_urgent_90d: 4, requester_downgraded_90d: 3 };
    open('/admin', ADMIN, { '/admin/tickets': [ROW, { ...ROW, id: 8, requester_downgraded_90d: 0 }] });
    expect((await screen.findByTestId('ticket-urgent-record-7')).textContent).toBe('提单人近 90 天自选加急 4 张，被改回一般 3 张');
    expect(screen.queryByTestId('ticket-urgent-record-8')).toBeNull();
  });
});
