// API-052 App 上的 API Key 用量与每日配额（152 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { KeyUsageBlock } from './apiKeyUsage';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const USAGE = { key_id: 4, daily_quota: 0, effective_daily_quota: 20000, today: '2026-10-15', today_used: 1500, today_remaining: 18500,
  resets_at: '2026-10-15T16:00:00Z', time_zone: '北京时间 UTC+8',
  days: [{ day: '2026-10-15', count: 1500, rejected: 12 }, { day: '2026-10-14', count: 800, rejected: 0 }] };

describe('API-052 App 上的 Key 用量', () => {
  it('显示今天已用与剩余、最近几天进来与挡回；保存更低配额', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /developer/api-keys/4/usage': USAGE,
      'PUT /developer/api-keys/4/quota': { id: 4, daily_quota: 5000, effective_daily_quota: 5000 } }, calls);
    render(<KeyUsageBlock client={client} keyId={4} />);
    expect(await screen.findByText(/已用 1500 \/ 20000 次（平台默认配额），还剩 18500 次/)).toBeTruthy();
    expect(screen.getByText(/10-15 1500（挡回 12） · 10-14 800/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('Key 4 每日配额'), '5000');
    fireEvent.press(screen.getByText('保存配额'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ daily_quota: 5000 }));
  });

  it('载荷不对时不显示，也不拖垮页面', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /developer/api-keys/4/usage': [] }, calls);
    const r = render(<KeyUsageBlock client={client} keyId={4} />);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(r.toJSON()).toBeNull();
  });

  it('API-054 写明账号下所有 Key 当天合计（158 号 spec）', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /developer/api-keys/4/usage': { ...USAGE, account_today_used: 41000, account_daily_quota: 50000, account_today_remaining: 9000 } }, calls);
    render(<KeyUsageBlock client={client} keyId={4} />);
    expect(await screen.findByText('账号下所有 Key 今天合计 41000 / 50000 次')).toBeTruthy();
  });

  it('API-056 平台单独调过账号配额的写明（235 号 spec）', async () => {
    const client = makeClient({ 'GET /developer/api-keys/4/usage': { ...USAGE, account_today_used: 1, account_daily_quota: 200000, account_today_remaining: 199999,
      account_quota_custom: true, account_quota_expires_at: null } }, []);
    render(<KeyUsageBlock client={client} keyId={4} />);
    expect(await screen.findByText('平台为你单独调过账号配额')).toBeTruthy();
  });
});
