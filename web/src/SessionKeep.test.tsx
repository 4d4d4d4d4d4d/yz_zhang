// REG-002（222 号 spec）只有服务端明确不认这个登录才清掉 token：断网、跳页取消的请求不清（以前一跳页就被登出）。
import { PlatformClient } from '@platform/core';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

function open(me: () => Promise<{ ok: boolean; status: number; text: () => Promise<string> }>) {
  localStorage.setItem('token', 'tok');
  const calls: string[] = [];
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push(p);
    if (p === '/users/me') return me();
    return { ok: true, status: 200, text: async () => '[]' };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => localStorage.getItem('token'), fetchImpl })}><App /></AppProvider>
  </MemoryRouter>);
  return calls;
}

describe('REG-002 登录态只在服务端不认时清', () => {
  it('请求被取消 / 断网：token 留着', async () => {
    const calls = open(async () => { throw new TypeError('Failed to fetch'); });
    await waitFor(() => expect(calls).toContain('/users/me'));
    await new Promise((r) => setTimeout(r, 20));
    expect(localStorage.getItem('token')).toBe('tok');
  });

  it('服务端说登录态无效：清掉', async () => {
    open(async () => ({ ok: false, status: 403, text: async () => JSON.stringify({ detail: { code: 'unauthenticated', message: '登录态无效' } }) }));
    await waitFor(() => expect(localStorage.getItem('token')).toBeNull());
  });
});
