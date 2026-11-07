// NTF-064 全站公告：预览、定时、取消、撤回（151 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const SENT = { id: 5, title: '佣金下调', body: '', verified_only: false, status: 'sent', scheduled_at: null, created_by: 1,
  created_at: '2026-10-14T00:00:00Z', sent_at: '2026-10-14T00:00:00Z', delivered: 300, closed_by: null, closed_at: null, close_reason: '' };
const SCHED = { ...SENT, id: 6, title: '维护通知', status: 'scheduled', scheduled_at: '2026-10-16T12:00:00Z', sent_at: null, delivered: 0 };

type Call = { method: string; path: string; body: unknown };
function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body: unknown = path === '/users/me' ? ADMIN
      : method === 'GET' && path === '/admin/announcements' ? [SCHED, SENT]
      : path === '/admin/announcements/preview' ? { audience: 1234, verified_only: false, title: '提现规则调整', body: '', warnings: ['正文是空的：用户点开只看到标题'] }
      : method === 'POST' && path === '/admin/announcements' ? { delivered: 0, id: 7, status: 'scheduled', scheduled_at: '2026-10-20T02:00:00Z' }
      : path === '/admin/announcements/5/revoke' ? { ...SENT, status: 'revoked', close_reason: '写错了', notifications_updated: 300 }
      : path === '/admin/announcements/6/cancel' ? { ...SCHED, status: 'cancelled' }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('NTF-064 全站公告', () => {
  it('预览说清送给多少人与要留意的地方，且预览不发', async () => {
    const calls: Call[] = [];
    open(calls);
    const card = await screen.findByLabelText('全站公告');
    fireEvent.change(within(card).getByPlaceholderText('标题'), { target: { value: '提现规则调整' } });
    fireEvent.click(within(card).getByText('预览'));
    const p = await screen.findByTestId('ann-preview');
    expect(p.textContent).toContain('1234');
    expect(p.textContent).toContain('正文是空的');
    expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/announcements')).toBe(false);
  });

  it('定时发送：北京时间带 +08:00 交给服务端，回显何时发出', async () => {
    const calls: Call[] = [];
    open(calls);
    const card = await screen.findByLabelText('全站公告');
    fireEvent.change(within(card).getByPlaceholderText('标题'), { target: { value: '维护' } });
    fireEvent.change(within(card).getByLabelText('定时发送'), { target: { value: '2026-10-20T10:00' } });
    fireEvent.click(within(card).getByRole('button', { name: '发布' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/announcements')?.body)
      .toMatchObject({ title: '维护', scheduled_at: '2026-10-20T10:00:00+08:00' }));
    expect((await screen.findByTestId('ann-result')).textContent).toContain('已定时');
  });

  it('发过的公告：定时的可取消，已发的可撤回（理由必填，并说清推送收不回来）', async () => {
    const calls: Call[] = [];
    vi.spyOn(window, 'prompt').mockReturnValue('写错了');
    open(calls);
    const table = await screen.findByLabelText('发过的公告');
    expect(table.textContent).toContain('等待定时发出');
    fireEvent.click(within(table).getByText('撤回'));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/announcements/5/revoke')?.body).toEqual({ reason: '写错了' }));
    const msg = (await screen.findByTestId('ann-result')).textContent ?? '';
    expect(msg).toContain('300 条通知');
    expect(msg).toContain('推送收不回来');
    fireEvent.click(within(await screen.findByLabelText('发过的公告')).getByText('取消'));
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/announcements/6/cancel')).toBe(true));
  });
});
