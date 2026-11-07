// FIN-073 弱网下再点一次「提现」是重试，不是第二笔提现（104 号 spec）。
//
// 服务端从 V1 起支持幂等键，而网页从来没发过它——超时后用户再点一次，
// 服务端看到的是两笔毫不相干的提现。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 1, phone: '138****0000', nickname: '提现的人', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};
const ROUTES: Record<string, unknown> = {
  '/users/me': ME,
  '/wallet': { available_cents: 50000, escrow_cents: 0, frozen_cents: 0 },
  '/wallet/ledger': [],
  '/wallet/payout-account': { bound: true, kind: 'bank', account_no: '6222****0000', holder_name: '张三' },
  '/finance/my-tax': { items: [], yearly: [], disclaimer: '预扣预缴不等于完税' },
  '/wallet/invoices': [],
  '/wallet/withdraw': { status: 'done', available_cents: 40000, frozen_cents: 0 },
  '/wallet/topup': { order_no: 'o1', status: 'succeeded', available_cents: 60000 },
};

/** `failFirst` 次打到 path 时网络断（fetch 抛异常，请求可能已经到了服务端）。 */
function open(failing: Record<string, number> = {}) {
  localStorage.setItem('token', 'tok');
  const keys: Record<string, string[]> = {};
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; headers?: Record<string, string> }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    if (init?.method === 'POST') (keys[path] ??= []).push(init.headers?.['Idempotency-Key'] ?? '');
    if (failing[path]) {
      failing[path] -= 1;
      throw new TypeError('Failed to fetch');
    }
    const hit = Object.keys(ROUTES).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? ROUTES[hit] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={['/wallet']}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return keys;
}

describe('FIN-073 资金操作带幂等键', () => {
  it('网络断了再点一次提现：同一个键（服务端回放，不是第二笔）', async () => {
    const keys = open({ '/wallet/withdraw': 1 });
    fireEvent.click(await screen.findByRole('button', { name: '提现' }));
    await waitFor(() => expect(keys['/wallet/withdraw']).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: '提现' }));
    await waitFor(() => expect(keys['/wallet/withdraw']).toHaveLength(2));
    const [a, b] = keys['/wallet/withdraw'];
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(b).toBe(a);
  });

  it('成功之后再点：是新的一笔，换新键', async () => {
    const keys = open();
    fireEvent.click(await screen.findByRole('button', { name: '充值（模拟）' }));
    await waitFor(() => expect(keys['/wallet/topup']).toHaveLength(1));
    await waitFor(() => expect(screen.getByRole('button', { name: '充值（模拟）' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '充值（模拟）' }));
    await waitFor(() => expect(keys['/wallet/topup']).toHaveLength(2));
    const [a, b] = keys['/wallet/topup'];
    expect(a).toBeTruthy();
    expect(b).not.toBe(a);
  });

  it('网络断了之后改了金额：是另一件事，换新键', async () => {
    const keys = open({ '/wallet/withdraw': 1 });
    fireEvent.click(await screen.findByRole('button', { name: '提现' }));
    await waitFor(() => expect(keys['/wallet/withdraw']).toHaveLength(1));
    fireEvent.change(screen.getByDisplayValue('100'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: '提现' }));
    await waitFor(() => expect(keys['/wallet/withdraw']).toHaveLength(2));
    expect(keys['/wallet/withdraw'][1]).not.toBe(keys['/wallet/withdraw'][0]);
  });
});
