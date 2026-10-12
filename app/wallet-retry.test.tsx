// FIN-073 弱网下再按一次「提现」是重试，不是第二笔提现（104 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { WalletScreen } from './App';

const ROUTES: Record<string, unknown> = {
  '/wallet': { available_cents: 50000, escrow_cents: 0, frozen_cents: 0 },
  '/wallet/ledger': [],
  '/wallet/payout-account': { bound: true, kind: 'bank', account_no: '6222****0000', holder_name: '张三' },
  '/wallet/withdraw': { status: 'done', available_cents: 40000, frozen_cents: 0 },
  '/wallet/topup': { order_no: 'o1', status: 'succeeded', available_cents: 60000 },
};

function makeClient(keys: Record<string, string[]>, failing: Record<string, number> = {}) {
  const fetchImpl = (async (url: string, init?: { method?: string; headers?: Record<string, string> }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    if (init?.method === 'POST') (keys[path] ??= []).push(init.headers?.['Idempotency-Key'] ?? '');
    if (failing[path]) {
      failing[path] -= 1;
      throw new TypeError('Network request failed');
    }
    const hit = Object.keys(ROUTES).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? ROUTES[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('FIN-073 App 资金操作带幂等键', () => {
  it('网络断了再按一次提现：同一个键', async () => {
    const keys: Record<string, string[]> = {};
    render(<WalletScreen client={makeClient(keys, { '/wallet/withdraw': 1 })} />);
    fireEvent.press(await screen.findByText('提现 ¥100.00'));
    await waitFor(() => expect(keys['/wallet/withdraw']).toHaveLength(1));
    fireEvent.press(screen.getByText('提现 ¥100.00'));
    await waitFor(() => expect(keys['/wallet/withdraw']).toHaveLength(2));
    expect(keys['/wallet/withdraw'][0]).toMatch(/^[0-9a-f]{32}$/);
    expect(keys['/wallet/withdraw'][1]).toBe(keys['/wallet/withdraw'][0]);
  });

  it('成功之后再按：换新键', async () => {
    const keys: Record<string, string[]> = {};
    render(<WalletScreen client={makeClient(keys)} />);
    fireEvent.press(await screen.findByText('充值 ¥100.00（模拟）'));
    await waitFor(() => expect(keys['/wallet/topup']).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText('提现已受理')).toBeNull());
    fireEvent.press(screen.getByText('充值 ¥100.00（模拟）'));
    await waitFor(() => expect(keys['/wallet/topup']).toHaveLength(2));
    expect(keys['/wallet/topup'][1]).not.toBe(keys['/wallet/topup'][0]);
  });
});
