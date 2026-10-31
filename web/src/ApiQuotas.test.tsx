// API-056（235 号 spec）后台「开放 API 配额」：调整带理由与天数、列表写明到期、改回默认要理由。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const OPS = { id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['ops'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = { user_id: 9, nickname: '某接入方', daily_quota: 200000, default_quota: 50000, reason: '签了企业接入合同',
  set_at: '2026-10-22T00:00:00Z', expires_at: '2026-11-21T00:00:00Z', active: true, today_used: 1234 };
type Call = { method: string; url: string; body?: unknown };

function open(rows: unknown[], calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const p = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, url: full, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? OPS : p === '/admin/api-accounts/quotas' ? rows
      : p === '/admin/api-accounts/9/quota' ? (method === 'DELETE' ? { user_id: 9, daily_quota: 50000, custom: false } : ROW) : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('API-056 开放 API 配额', () => {
  it('调整：带理由与天数；列表写明到期与今天用量', async () => {
    const calls: Call[] = [];
    open([ROW], calls);
    const box = await screen.findByLabelText('开放 API 配额');
    const li = await within(box).findByTestId('api-quota-9');
    expect(li.textContent).toContain('某接入方：每天 200000 次（默认 50000）· 今天用了 1234 · 到 ');
    fireEvent.change(within(box).getByLabelText('用户编号'), { target: { value: '9' } });
    fireEvent.change(within(box).getByLabelText('每日配额'), { target: { value: '200000' } });
    fireEvent.change(within(box).getByLabelText('有效天数'), { target: { value: '30' } });
    fireEvent.change(within(box).getByLabelText('调整理由'), { target: { value: '签了企业接入合同' } });
    fireEvent.click(within(box).getByText('调整'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ daily_quota: 200000, reason: '签了企业接入合同', days: 30 }));
    expect((await within(box).findByRole('status')).textContent).toBe('已调整 #9 的账号配额');
  });

  it('改回默认要写理由；没写够不发', async () => {
    const calls: Call[] = [];
    const prompt = vi.spyOn(window, 'prompt').mockReturnValueOnce('短').mockReturnValueOnce('合同到期');
    open([ROW], calls);
    const box = await screen.findByLabelText('开放 API 配额');
    fireEvent.click(await within(box).findByText('改回默认'));
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
    fireEvent.click(within(box).getByText('改回默认'));
    await waitFor(() => expect(calls.find((c) => c.method === 'DELETE')?.url).toBe('/admin/api-accounts/9/quota?reason=%E5%90%88%E5%90%8C%E5%88%B0%E6%9C%9F'));
    prompt.mockRestore();
  });

  it('非运营看不到这一块', async () => {
    localStorage.setItem('token', 'tok');
    const SUP = { ...OPS, admin_roles: ['support'] };
    const fetchImpl = vi.fn(async (url: string) => ({ ok: true, status: 200, headers: { get: () => null },
      text: async () => JSON.stringify(String(url).includes('/users/me') ? SUP : []) })) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    await screen.findByLabelText('用户管理');
    expect(screen.queryByLabelText('开放 API 配额')).toBeNull();
  });
});
