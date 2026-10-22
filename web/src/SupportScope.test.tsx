// ESCA-061（234 号 spec）后台工单台「我负责的类别」：勾选并保存；声明过才出现「只看我负责的类别」筛选。
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
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const p = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, url: full, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ADMIN : p === '/admin/tickets' ? [ROW]
      : p === '/admin/support/my-categories' ? (method === 'PUT' ? { categories: ['funds'], declared: true, labels: LABELS } : scope)
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-061 我负责的类别', () => {
  it('没声明时写明视为都管、没有筛选；勾选保存后出现「只看我负责的类别」，勾上带参数', async () => {
    const calls: Call[] = [];
    open({ categories: ['funds', 'account', 'general'], declared: false, labels: LABELS }, calls);
    const box = await screen.findByLabelText('我负责的类别');
    expect(box.textContent).toContain('（还没选，视为都管）');
    expect(screen.queryByText('只看我负责的类别')).toBeNull();
    fireEvent.click(within(box).getByLabelText(/账号/));
    fireEvent.click(within(box).getByLabelText(/一般/));
    fireEvent.click(within(box).getByText('保存'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ categories: ['funds'] }));
    expect(await within(box).findByRole('status')).toBeTruthy();
    fireEvent.click(await screen.findByLabelText(/只看我负责的类别/));
    await waitFor(() => expect(calls.some((c) => c.url.startsWith('/admin/tickets?') && c.url.includes('my_categories=true'))).toBe(true));
  });

  it('老服务端没有这个接口：不显示这一块', async () => {
    open([], []);
    await screen.findByText('钱没到账');
    expect(screen.queryByLabelText('我负责的类别')).toBeNull();
  });
});
