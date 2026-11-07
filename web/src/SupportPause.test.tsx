// ESCA-065（240 号 spec）后台工单台「暂停接单」：选时长暂停，暂停中写明到几点并能提前恢复。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '客服甲', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['support'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
  first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
  last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急' };
const LABELS = { funds: '资金（提现、退款、到账）', account: '账号（登录、安全）', general: '一般' };
type Call = { method: string; url: string; body?: unknown };

function open(scope: unknown, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, url: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ADMIN : p === '/admin/tickets' ? [ROW]
      : p === '/admin/support/my-categories' ? scope
      : p === '/admin/support/my-pause' ? { paused_until: method === 'POST' ? '2026-10-22T10:00:00Z' : null }
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-065 暂停接单', () => {
  it('选时长暂停，写明到几点、手上的不动；暂停中能提前恢复', async () => {
    const calls: Call[] = [];
    open({ categories: ['funds'], declared: true, labels: LABELS, auto_assign: true }, calls);
    const box = await screen.findByLabelText('我负责的类别');
    fireEvent.change(within(box).getByLabelText('暂停多久'), { target: { value: '24' } });
    fireEvent.click(within(box).getByText('暂停接单'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/admin/support/my-pause')?.body).toEqual({ hours: 24 }));
    expect((await within(box).findByRole('status')).textContent).toContain('手上已接的工单不动');
    expect(box.textContent).toContain('暂停接单到');
    fireEvent.click(within(box).getByText('恢复接单'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.url === '/admin/support/my-pause')).toBe(true));
    await waitFor(() => expect(within(box).getByRole('status').textContent).toBe('已恢复接单'));
    expect(within(box).getByText('暂停接单')).toBeTruthy();
  });

  it('打开时已在暂停中：直接显示到几点和「恢复接单」', async () => {
    open({ categories: ['funds'], declared: true, labels: LABELS, auto_assign: true, paused_until: '2026-10-22T10:00:00Z' }, []);
    const box = await screen.findByLabelText('我负责的类别');
    expect(box.textContent).toContain('暂停接单到');
    expect(within(box).getByText('恢复接单')).toBeTruthy();
    expect(within(box).queryByLabelText('暂停多久')).toBeNull();
  });
});
