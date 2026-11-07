// KB-062b（327 号 spec）后台「城市与类目」：每个类目显示经验时效（没设写默认 365 天），可以按类目调，填错当场说清。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '运营', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [],
  credit_level: '普通', referral_code: 'r2' };
const CATS = [{ id: 1, name: '装修', required_cert: '', experience_fresh_days: 90 }, { id: 3, name: '跑腿', required_cert: '' }];
type Call = { method: string; path: string; query: string };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const [p, q = ''] = String(url).replace(/^.*\/api\/v1/, '').split('?');
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, query: decodeURIComponent(q) });
    const body = p === '/users/me' ? ME : p === '/categories' ? CATS : p === '/cities' ? [{ id: 1, name: '上海' }]
      : p === '/admin/admins' ? { admins: [] } : p === '/admin/aml/activities' ? { items: [], note: '' }
      : method === 'PATCH' ? { id: 3, name: '跑腿', active: true, required_cert: '', experience_fresh_days: 180 } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('KB-062b 经验时效按类目', () => {
  it('显示每个类目的经验时效；改跑腿为 180 天', async () => {
    const calls: Call[] = [];
    open(calls);
    const reno = (await screen.findByText('装修')).closest('tr')!;
    expect(reno.textContent).toContain('经验时效 90 天');
    const errand = screen.getByText('跑腿').closest('tr')!;
    expect(errand.textContent).toContain('经验时效 365 天（默认）');
    const ask = vi.spyOn(window, 'prompt').mockReturnValue(' 180 ');
    try {
      fireEvent.click(within(errand).getByText('经验时效'));
      await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.path === '/admin/categories/3')?.query)
        .toBe('experience_fresh_days=180'));
    } finally { ask.mockRestore(); }
  });

  it('填的不是整数：当场说清，不发请求', async () => {
    const calls: Call[] = [];
    open(calls);
    const errand = (await screen.findByText('跑腿')).closest('tr')!;
    const ask = vi.spyOn(window, 'prompt').mockReturnValue('半年');
    try {
      fireEvent.click(within(errand).getByText('经验时效'));
      expect(await screen.findByText(/经验时效填一个整数天数/)).toBeTruthy();
      expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
    } finally { ask.mockRestore(); }
  });
});
