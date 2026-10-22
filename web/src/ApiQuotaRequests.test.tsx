// API-057（241 号 spec）开发者页申请提额、撤回；后台看到申请并批准（可改量）或驳回（要理由）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const OPS = { ...ME, nickname: '运营', is_admin: true, admin_roles: ['ops'], certifications: [], credit_level: '普通', referral_code: 'r1' };
const KEY = { id: 4, name: '集成', scopes: ['tasks:read'], key_prefix: 'pk_ab', active: true, last_used_at: null,
  created_at: '2026-10-01T00:00:00Z', rate_per_minute: 0, effective_rate_per_minute: 120 };
const REQ = { id: 3, daily_quota: 5000, days: 30, purpose: '接入店铺 ERP 同步订单', status: 'pending', created_at: '2026-10-22T00:00:00Z',
  decided_at: null, decision_note: '', granted_quota: null, granted_days: null };
type Call = { method: string; path: string; body: unknown };

function open(at: string, me: unknown, routes: Record<string, unknown>, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const key = `${method} ${path}`;
    const body = path === '/users/me' ? me : key in routes ? routes[key] : path in routes ? routes[path]
      : path === '/developer/scopes' ? { scopes: [], events: [], notice: '' } : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[at]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

afterEach(() => vi.restoreAllMocks());

describe('API-057 提额申请', () => {
  it('开发者页：填量、天数、用途提交；待批时不再显示表单，可以撤回', async () => {
    const calls: Call[] = [];
    let mine: unknown[] = [];
    const routes: Record<string, unknown> = { '/developer/api-keys': [KEY] };
    Object.defineProperty(routes, 'GET /developer/quota-requests', { get: () => mine, enumerable: true });
    routes['POST /developer/quota-requests'] = REQ;
    routes['DELETE /developer/quota-requests/3'] = { ...REQ, status: 'withdrawn' };
    open('/developer', ME, routes, calls);
    const box = await screen.findByLabelText('申请提高配额');
    fireEvent.change(within(box).getByLabelText('想要的每日配额'), { target: { value: '5000' } });
    fireEvent.change(within(box).getByLabelText('想要多少天'), { target: { value: '30' } });
    fireEvent.change(within(box).getByLabelText('用途'), { target: { value: '接入店铺 ERP 同步订单' } });
    mine = [REQ];
    fireEvent.click(within(box).getByText('提交申请'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/developer/quota-requests')?.body)
      .toEqual({ daily_quota: 5000, purpose: '接入店铺 ERP 同步订单', days: 30 }));
    expect((await within(box).findByTestId('quota-request-3')).textContent).toContain('#3 申请每天 5000 次、30 天（接入店铺 ERP 同步订单） · 待批');
    expect(within(box).queryByText('提交申请')).toBeNull();
    mine = [{ ...REQ, status: 'withdrawn' }];
    fireEvent.click(within(box).getByText('撤回'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/developer/quota-requests/3')).toBe(true));
    expect(await within(box).findByText('提交申请')).toBeTruthy();
  });

  it('后台：列出待批申请与现在的配额、最近用量；批准可改量，驳回要理由', async () => {
    const calls: Call[] = [];
    const row = { ...REQ, user_id: 9, nickname: '某接入方', current_quota: 50000, peak_7d: 48000 };
    open('/admin', OPS, {
      'GET /admin/api-quota-requests': [row],
      'POST /admin/api-quota-requests/3/approve': { ...REQ, status: 'approved', granted_quota: 3000, granted_days: 30 },
      'POST /admin/api-quota-requests/3/reject': { ...REQ, status: 'rejected' },
    }, calls);
    const li = await screen.findByTestId('quota-req-3');
    expect(li.textContent).toContain('某接入方：#3 申请每天 5000 次、30 天');
    expect(li.textContent).toContain('现在每天 50000 次，最近 7 天最多一天用了 48000 次');
    const prompt = vi.spyOn(window, 'prompt').mockReturnValueOnce('3000').mockReturnValueOnce('先给 3000');
    fireEvent.click(within(li).getByText('批准'));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/api-quota-requests/3/approve')?.body)
      .toEqual({ note: '先给 3000', daily_quota: 3000 }));
    prompt.mockReset();
    prompt.mockReturnValueOnce('不');
    fireEvent.click(within(await screen.findByTestId('quota-req-3')).getByText('驳回'));
    expect(calls.some((c) => c.path === '/admin/api-quota-requests/3/reject')).toBe(false);
    prompt.mockReturnValueOnce('用途写得不清楚');
    fireEvent.click(within(await screen.findByTestId('quota-req-3')).getByText('驳回'));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/api-quota-requests/3/reject')?.body).toEqual({ note: '用途写得不清楚' }));
  });
});
