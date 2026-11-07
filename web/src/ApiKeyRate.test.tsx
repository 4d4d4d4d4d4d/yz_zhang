// API-050 API Key 的每分钟上限在网页开发者设置里（145 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const KEY = (own: number, eff: number) => ({ id: 4, name: '集成', scopes: ['tasks:read'], key_prefix: 'pk_ab', active: true,
  last_used_at: null, created_at: '2026-10-01T00:00:00Z', rate_per_minute: own, effective_rate_per_minute: eff });

describe('API-050 Key 每分钟上限', () => {
  it('显示生效上限与来源，保存更低的上限', async () => {
    localStorage.setItem('token', 'tok');
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    let saved = false;
    const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      if (method === 'PUT') saved = true;
      const body = path === '/users/me' ? ME : path === '/developer/api-keys' ? [saved ? KEY(30, 30) : KEY(0, 120)]
        : path === '/developer/scopes' ? { scopes: [], events: [], notice: '' }
        : path === '/developer/api-keys/4/rate-limit' ? { id: 4, rate_per_minute: 30, effective_rate_per_minute: 30 } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/developer']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    const line = await screen.findByTestId('key-rate-4');
    expect(line.textContent).toContain('每分钟最多 120 次（平台默认）');
    fireEvent.change(screen.getByLabelText('Key 4 每分钟上限'), { target: { value: '30' } });
    fireEvent.click(screen.getByText('保存'));
    await waitFor(() => expect(screen.getByTestId('key-rate-4').textContent).toContain('每分钟最多 30 次（你设的）'));
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ rate_per_minute: 30 });
  });
});
