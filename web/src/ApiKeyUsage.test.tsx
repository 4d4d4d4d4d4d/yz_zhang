// API-052 API Key 用量与每日配额在网页开发者设置里（152 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const KEY = { id: 4, name: '集成', scopes: ['tasks:read'], key_prefix: 'pk_ab', active: true, last_used_at: null,
  created_at: '2026-10-01T00:00:00Z', rate_per_minute: 0, effective_rate_per_minute: 120, daily_quota: 0, effective_daily_quota: 20000 };
const USAGE = (quota: number, own: number) => ({ key_id: 4, daily_quota: own, effective_daily_quota: quota, today: '2026-10-15',
  today_used: 1500, today_remaining: quota - 1500, resets_at: '2026-10-15T16:00:00Z', time_zone: '北京时间 UTC+8',
  days: [{ day: '2026-10-15', count: 1500, rejected: 12 }, { day: '2026-10-14', count: 800, rejected: 0 }] });

describe('API-052 Key 用量与每日配额', () => {
  it('显示今天已用 / 配额 / 剩余 / 恢复时间与每天进来和挡回的数；保存更低配额', async () => {
    localStorage.setItem('token', 'tok');
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    let saved = false;
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      if (method === 'PUT') saved = true;
      const body = path === '/users/me' ? ME : path === '/developer/api-keys' ? [KEY]
        : path === '/developer/scopes' ? { scopes: [], events: [], notice: '' }
        : path === '/developer/api-keys/4/usage' ? (saved ? USAGE(5000, 5000) : USAGE(20000, 0))
        : path === '/developer/api-keys/4/quota' ? { id: 4, daily_quota: 5000, effective_daily_quota: 5000 } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/developer']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    const box = await screen.findByTestId('key-usage-4');
    expect(box.textContent).toContain('已用 1500 / 20000 次（平台默认配额）');
    expect(box.textContent).toContain('还剩 18500 次');
    const table = within(box).getByLabelText('Key 4 最近用量');
    expect(table.textContent).toContain('2026-10-15');
    expect(table.textContent).toContain('12');
    fireEvent.change(screen.getByLabelText('Key 4 每日配额'), { target: { value: '5000' } });
    fireEvent.click(screen.getByText('保存配额'));
    await waitFor(() => expect(screen.getByTestId('key-usage-4').textContent).toContain('已用 1500 / 5000 次（你设的配额）'));
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ daily_quota: 5000 });
  });

  it('API-054 写明账号下所有 Key 当天合计（158 号 spec）', async () => {
    localStorage.setItem('token', 'tok');
    const fetchImpl = vi.fn(async (url: string) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const body = path === '/users/me' ? ME : path === '/developer/api-keys' ? [KEY]
        : path === '/developer/scopes' ? { scopes: [], events: [], notice: '' }
        : path === '/developer/api-keys/4/usage' ? { ...USAGE(20000, 0), account_today_used: 41000, account_daily_quota: 50000, account_today_remaining: 9000 } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/developer']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    expect((await screen.findByTestId('key-usage-4')).textContent).toContain('账号下所有 Key 合计 41000 / 50000 次');
  });
});
