// NTF-066 / NTF-067 公告定向与阅读率（159 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const SENT = { id: 5, title: '上海见面会', body: '', verified_only: false, city: '上海', audience: 'publishers', status: 'sent', scheduled_at: null,
  created_by: 1, created_at: '2026-10-14T00:00:00Z', sent_at: '2026-10-14T00:00:00Z', delivered: 200, closed_by: null, closed_at: null,
  close_reason: '', read: 50, read_rate: 0.25 };

type Call = { method: string; path: string; body: unknown };
function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body: unknown = path === '/users/me' ? ADMIN
      : method === 'GET' && path === '/admin/announcements' ? [SENT]
      : path === '/admin/announcements/preview' ? { audience: 37, verified_only: false, city: '上海', audience_kind: 'publishers', title: '上海见面会', body: '', warnings: [] }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('NTF-066 / NTF-067 公告定向与阅读率', () => {
  it('城市与人群带进预览请求，预览说清发给谁；历史里显示阅读率', async () => {
    const calls: Call[] = [];
    open(calls);
    const card = await screen.findByLabelText('全站公告');
    fireEvent.change(within(card).getByPlaceholderText('标题'), { target: { value: '上海见面会' } });
    fireEvent.change(within(card).getByLabelText('只发给城市'), { target: { value: '上海' } });
    fireEvent.change(within(card).getByLabelText('发给哪类人'), { target: { value: 'publishers' } });
    fireEvent.click(within(card).getByText('预览'));
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/announcements/preview')?.body)
      .toMatchObject({ city: '上海', audience: 'publishers' }));
    const p = await screen.findByTestId('ann-preview');
    expect(p.textContent).toContain('37');
    expect(p.textContent).toContain('上海 · 近 180 天发过单的人');
    const table = await screen.findByLabelText('发过的公告');
    expect(table.textContent).toContain('50 人（25%）');
    expect(table.textContent).toContain('（上海）（近 180 天发过单的人）');
  });
});
