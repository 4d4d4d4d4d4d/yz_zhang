// API-057（241 号 spec）App 开发者页申请提额：点开才加载，提交、撤回。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { QuotaRequestsBlock } from './apiKeyUsage';

type Call = { method: string; path: string; body: unknown };
const REQ = { id: 3, daily_quota: 5000, days: null, purpose: '接入店铺 ERP 同步订单', status: 'pending', created_at: '2026-10-22T00:00:00Z',
  decided_at: null, decision_note: '', granted_quota: null, granted_days: null };

describe('API-057 App 提额申请', () => {
  it('点开才加载；提交不填天数就不带 days；待批时可以撤回', async () => {
    const calls: Call[] = [];
    let mine: unknown[] = [];
    const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      const body = method === 'GET' ? mine : method === 'POST' ? REQ : { ...REQ, status: 'withdrawn' };
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    render(<QuotaRequestsBlock client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} />);
    expect(calls).toEqual([]);
    fireEvent.press(screen.getByText('申请提高账号配额'));
    fireEvent.changeText(await screen.findByLabelText('想要的每日配额'), '5000');
    fireEvent.changeText(screen.getByLabelText('用途'), '接入店铺 ERP 同步订单');
    mine = [REQ];
    fireEvent.press(screen.getByText('提交申请'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ daily_quota: 5000, purpose: '接入店铺 ERP 同步订单' }));
    expect(await screen.findByText('#3 申请每天 5000 次、长期（接入店铺 ERP 同步订单） · 待批')).toBeTruthy();
    expect(screen.queryByText('提交申请')).toBeNull();
    mine = [{ ...REQ, status: 'withdrawn' }];
    fireEvent.press(screen.getByText('撤回'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/developer/quota-requests/3')).toBe(true));
    expect(await screen.findByText('提交申请')).toBeTruthy();
  });
});
