// SCN-122（356 号 spec）服务对象自己看进度：替别人发的单，发单人在详情里生成 / 作废链接；服务对象打开 /r/令牌 不用登录。
import { PlatformClient } from '@platform/core';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 9, phone: '138****0009', nickname: '女儿', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r9' };
type Call = { method: string; path: string; body?: unknown };
const TASK = (extra: Record<string, unknown>) => ({ id: 60, title: '装扶手', description: '', category: '维修', status: 'published', budget_cents: 20000,
  creator_id: 9, executor_id: null, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
  on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139', ...extra });
const NONE = { state: 'none', task_id: null, created_at: null, expires_at: null, view_count: 0, last_viewed_at: null };
const ACTIVE = { state: 'active', task_id: 60, created_at: '2026-11-03T00:00:00Z', expires_at: '2026-11-10T00:00:00Z', view_count: 2, last_viewed_at: '2026-11-03T02:00:00Z' };

function open(path: string, calls: Call[], routes: (method: string, p: string) => unknown, token: string | null = 'tok') {
  if (token) localStorage.setItem('token', token); else localStorage.removeItem('token');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = routes(method, p);
    if (hit instanceof Error) {
      return { ok: false, status: 404, text: async () => JSON.stringify({ detail: { code: hit.message, message: '链接过期' } }) };
    }
    const body = hit !== undefined ? hit : p === '/users/me' ? ME : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => token, fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-122 服务对象进度链接', () => {
  it('发单人生成链接：带上有效天数，完整地址只显示这一次；能作废', async () => {
    const calls: Call[] = [];
    let state: Record<string, unknown> = NONE;
    open('/tasks/60', calls, (m, p) => {
      if (p === '/tasks/60') return TASK({});
      if (p === '/tasks/60/recipient-link' && m === 'GET') return state;
      if (p === '/tasks/60/recipient-link' && m === 'POST') { state = ACTIVE; return { ...ACTIVE, view_count: 0, last_viewed_at: null, token: 'abcTOKEN', path: '/r/abcTOKEN', hint: '' }; }
      if (p === '/tasks/60/recipient-link' && m === 'DELETE') return { ...ACTIVE, state: 'revoked', revoked: 1 };
      return undefined;
    });
    const panel = await screen.findByLabelText('服务对象进度链接');
    expect(panel.textContent).toContain('还没有生成');
    expect(panel.textContent).toContain('看不到电话、地址、价钱');
    fireEvent.change(screen.getByLabelText('有效天数'), { target: { value: '3' } });
    fireEvent.click(screen.getByText('生成链接'));
    const link = await screen.findByLabelText('进度链接');
    expect(link.textContent).toMatch(/\/r\/abcTOKEN$/);
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/60/recipient-link')?.body).toEqual({ days: 3 });
    fireEvent.click(screen.getByText('作废链接'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/tasks/60/recipient-link')).toBe(true));
    await waitFor(() => expect(screen.queryByLabelText('进度链接')).toBeNull());
    expect(screen.getByLabelText('服务对象进度链接').textContent).toContain('已作废');
  });

  it('不是替别人发的单、不是发单人、单子已结束：都没有这个面板', async () => {
    for (const extra of [{ on_behalf: false }, { creator_id: 5 }, { status: 'completed' }]) {
      const calls: Call[] = [];
      open('/tasks/60', calls, (_m, p) => (p === '/tasks/60' ? TASK(extra) : p === '/tasks/60/recipient-link' ? ACTIVE : undefined));
      await screen.findByText('装扶手');
      expect(screen.queryByLabelText('服务对象进度链接')).toBeNull();
      expect(calls.some((c) => c.path === '/tasks/60/recipient-link')).toBe(false);
      cleanup();
    }
  });

  it('服务对象不登录打开 /r/令牌：看到谁来、几点、到没到，没有电话', async () => {
    const calls: Call[] = [];
    open('/r/abcTOKEN', calls, (_m, p) => (p === '/recipient-progress/abcTOKEN' ? {
      recipient_label: '我妈', title: '装扶手', phase: 'assigned', phase_text: '已经定好人了',
      helpers: [{ name: '李师傅', verified: true, work_date: null }], work_date: '2026-11-05', days: 1,
      shift_start: '09:00', shift_end: '11:00', deadline: null, visits_planned: 0, visits_reported: 0,
      last_arrival_at: null, departed_at: '2026-11-05T00:30:00Z', eta_at: '2026-11-05T01:00:00Z', expires_at: '2026-11-10T00:00:00Z' } : undefined), null);
    const page = await screen.findByLabelText('服务进度');
    expect(page.textContent).toContain('我妈，这一单已经定好人了');
    expect(page.textContent).toContain('李师傅（已实名）');
    expect(page.textContent).toContain('09:00~11:00');
    expect(page.textContent).toContain('已出发，预计');   // SCN-122c（364 号 spec）
    expect(page.textContent).not.toContain('139');
    expect(calls.every((c) => c.path !== '/tasks/60/recipient-link')).toBe(true);
  });

  it('链接过期：说清找家人重新发', async () => {
    open('/r/old', [], (_m, p) => (p === '/recipient-progress/old' ? new Error('recipient_link_expired') : undefined), null);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/过期/);
  });
});
