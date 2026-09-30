// PAY-030 收款账户绑定：提现的前置条件，此前**全仓没有任何界面能满足它**。
//
// 网页上一直有「提现」按钮，而 `bindPayoutAccount` 在 web 和 app 里
// 一次都没被调用过——于是每一次点击都返回
// `400 {"code":"no_payout_account","message":"请先绑定收款账户"}`，
// 用户读到这句提示，然后在整个产品里找不到任何一处可以绑定。**钱能进，不能出。**
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

/** 按整条路径精确匹配（V84 的教训：`includes` 会让 `/wallet` 吃掉
 *  `/wallet/ledger` 和 `/wallet/payout-account`，页面拿对象去 .map() 直接白屏）。 */
function makeClient(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string; body: unknown }> = [],
): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const WALLET = { available_cents: 50000, escrow_cents: 0, frozen_cents: 0 };
const TAX = { items: [], yearly: [], disclaimer: '预扣预缴不等于完税' };

describe('钱包：钱能进，也要能出', () => {
  it('PAY-030 未绑定时说清楚提现会被拒，并且就地能绑', async () => {
    localStorage.setItem('token', 'tok');
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({
      '/users/me': ME,
      '/wallet': WALLET,
      '/wallet/ledger': [],
      '/finance/my-tax': TAX,
      '/wallet/payout-account': { bound: false },
    }, calls);
    render(
      <MemoryRouter initialEntries={['/wallet']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/未绑定收款账户/)).toBeTruthy());

    fireEvent.change(screen.getByPlaceholderText('银行卡号 / 支付宝账号'), { target: { value: '6222020000000000' } });
    fireEvent.change(screen.getByPlaceholderText('开户姓名'), { target: { value: '提现的人' } });
    fireEvent.click(screen.getByText('绑定'));

    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.path === '/wallet/payout-account')).toBe(true));
    const bind = calls.find((c) => c.path === '/wallet/payout-account' && c.method === 'PUT')!;
    expect(bind.body).toMatchObject({ kind: 'bank', account_no: '6222020000000000', holder_name: '提现的人' });
  });

  it('PAY-030 已绑定显示的是服务端返回的脱敏卡号，不自己拼回去', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/wallet': WALLET,
      '/wallet/ledger': [],
      '/finance/my-tax': TAX,
      '/wallet/payout-account': { bound: true, kind: 'bank', account_no: '6222****0000', holder_name: '提现的人' },
    });
    render(
      <MemoryRouter initialEntries={['/wallet']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/6222\*\*\*\*0000/)).toBeTruthy());
  });

  it('AML-030 大额进人审时，原样显示服务端的中性话术', async () => {
    localStorage.setItem('token', 'tok');
    const neutral = '您的提现申请已提交，我们会尽快处理';
    const client = makeClient({
      '/users/me': ME,
      '/wallet': WALLET,
      '/wallet/ledger': [],
      '/finance/my-tax': TAX,
      '/wallet/payout-account': { bound: true, kind: 'bank', account_no: '6222****0000', holder_name: '提现的人' },
      // tipping-off：服务端**刻意**不说触发了哪条规则，界面更不能自己编一句
      '/wallet/withdraw': { status: 'pending_review', request_id: 3, message: neutral, available_cents: 40000, frozen_cents: 10000 },
    });
    render(
      <MemoryRouter initialEntries={['/wallet']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('提现')).toBeTruthy());
    fireEvent.click(screen.getByText('提现'));
    await waitFor(() => expect(screen.getByText(neutral)).toBeTruthy());
  });
});
