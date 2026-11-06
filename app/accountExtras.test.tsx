// APP-074（418 号 spec）网页早就有、App 一直没有的三件事：登录设备、通知已读、券。
import { readFileSync } from 'fs';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { CouponsBlock, DeviceSessionsBlock, NoticesList } from './accountExtras';
import { WalletScreen } from './App';

type Call = { method: string; path: string; body: unknown };
type Route = { status?: number; body: unknown };

function makeClient(routes: Record<string, Route>, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const full = decodeURIComponent(String(url).replace(/^.*\/api\/v1/, ''));
    const method = init?.method ?? 'GET';
    calls.push({ method, path: full, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[`${method} ${full}`] ?? routes[`${method} ${full.split('?')[0]}`] ?? routes[full.split('?')[0]];
    const status = hit?.status ?? 200;
    return { ok: status < 400, status, text: async () => JSON.stringify(hit ? hit.body : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('ACC-005 App 上的登录设备', () => {
  it('列出在登的设备，点「下线」吊销那一台并重新拉', async () => {
    const calls: Call[] = [];
    render(<DeviceSessionsBlock client={makeClient({
      '/auth/sessions': { body: [{ id: 3, device: 'iPhone 15', created_at: '2026-11-01T08:00:00Z' }, { id: 4, device: '', created_at: '2026-11-02T08:00:00Z' }] },
      'POST /auth/sessions/3/revoke': { body: { ok: true } },
    }, calls)} />);
    expect(await screen.findByText('登录设备（2）')).toBeTruthy();
    expect(screen.getByText(/未知设备/)).toBeTruthy();
    fireEvent.press(screen.getAllByText('下线')[0]);
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/auth/sessions/3/revoke')).toBe(true));
    await waitFor(() => expect(calls.filter((c) => c.path === '/auth/sessions').length).toBe(2));
  });

  it('响应畸形或没有设备：整块不画', async () => {
    const calls: Call[] = [];
    render(<DeviceSessionsBlock client={makeClient({ '/auth/sessions': { body: { oops: 1 } } }, calls)} />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByText(/登录设备/)).toBeNull();
  });
});

describe('GRW App 上的券', () => {
  const OFFER = { id: 7, title: '新人立减', kind: 'requester_discount', amount_cents: 2000, percent_bps: 0, max_discount_cents: 0,
    min_order_cents: 10000, category: '', newcomer_only: true, total_quota: 100, issued_count: 1, per_user_limit: 1, valid_days: 30, active: true };
  const MINE = { id: 11, status: 'unused', title: '九折券', kind: 'requester_discount', min_order_cents: 0, amount_cents: 0, percent_bps: 900,
    max_discount_cents: 3000, category: '', expires_at: '2026-12-31T00:00:00Z', discount_cents: 0, contract_id: null };

  it('可领的与我的都显示；领取打到 /coupons/7/claim 并重新拉', async () => {
    const calls: Call[] = [];
    render(<CouponsBlock client={makeClient({
      '/coupons': { body: { coupons: [OFFER] } }, '/me/coupons': { body: { coupons: [MINE] } },
      'POST /coupons/7/claim': { body: { id: 12, coupon_id: 7, status: 'unused', expires_at: '2026-12-31T00:00:00Z' } },
    }, calls)} />);
    expect(await screen.findByText('减 ¥20.00 · 满 ¥100.00 可用 · 仅新用户')).toBeTruthy();
    expect(screen.getByText(/9.0% 折，最高减 ¥30.00 · 有效期至/)).toBeTruthy();
    expect(screen.getByText('可用')).toBeTruthy();
    fireEvent.press(screen.getByText('领取'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/coupons/7/claim')).toBe(true));
    await waitFor(() => expect(calls.filter((c) => c.path === '/coupons').length).toBe(2));
  });

  it('领不了时说清为什么', async () => {
    render(<CouponsBlock client={makeClient({
      '/coupons': { body: { coupons: [OFFER] } }, '/me/coupons': { body: { coupons: [] } },
      'POST /coupons/7/claim': { status: 409, body: { detail: { code: 'coupon_x', message: '这张券已经领完了' } } },
    })} />);
    fireEvent.press(await screen.findByText('领取'));
    expect(await screen.findByText(/已经领完了/)).toBeTruthy();
  });

  it('钱包页里有券这一块', async () => {
    render(<WalletScreen client={makeClient({
      '/wallet': { body: { available_cents: 0, frozen_cents: 0, total_income_cents: 0 } },
      '/coupons': { body: { coupons: [OFFER] } }, '/me/coupons': { body: { coupons: [] } },
    })} />);
    expect(await screen.findByText('新人立减')).toBeTruthy();
  });
});

describe('NTF App 上的通知已读', () => {
  const NOTES = [
    { id: 5, category: 'task', title: '验收快到期了', body: '还剩 1 天', is_read: false, created_at: '2026-11-05T00:00:00Z' },
    { id: 6, category: 'system', title: '欢迎', body: '你好', is_read: true, created_at: '2026-11-01T00:00:00Z' },
  ];

  it('未读的有标记；点一条记成「从通知中心点开」的已读；点已读的不再发', async () => {
    const calls: Call[] = [];
    const onChanged = jest.fn();
    render(<NoticesList onChanged={onChanged} client={makeClient({
      '/notifications': { body: NOTES }, 'POST /notifications/5/read': { body: { ok: true } },
    }, calls)} />);
    expect(await screen.findByText('● 验收快到期了')).toBeTruthy();
    expect(screen.getByText('欢迎')).toBeTruthy();
    fireEvent.press(screen.getByTestId('notice-6'));
    fireEvent.press(screen.getByTestId('notice-5'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/notifications/5/read?via=center']);
  });

  it('全部标为已读', async () => {
    const calls: Call[] = [];
    render(<NoticesList client={makeClient({ '/notifications': { body: NOTES }, 'POST /notifications/read-all': { body: { marked: 1 } } }, calls)} />);
    fireEvent.press(await screen.findByText('全部标为已读（未读 1）'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/notifications/read-all')).toBe(true));
  });

  it('顶栏「通知」带未读数，关掉通知页时重新数；「我的」里有登录设备', () => {
    // App 根组件自己 new client（读 BASE_URL），登录后的顶栏在单测里渲染不出来，这里按源码钉住接线
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    expect(src).toContain("{unread ? `通知 ${unread}` : '通知'}");
    expect(src).toContain('setUnread(unreadBadge(r?.unread))');
    expect(src).toContain('useEffect(() => { if (!overlay) refreshUnread(); }, [overlay, refreshUnread]);');
    expect(src).toContain("<NoticesScreen client={client} onChanged={refreshUnread} />");
    expect(src).toContain('<DeviceSessionsBlock client={client} />');
  });
});
