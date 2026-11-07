// API-050 API Key 的每分钟上限在 App 开发者设置里（145 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SubScreenHost } from './TeamCoopDev';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const KEY = { id: 4, name: '集成', scopes: ['tasks:read'], key_prefix: 'pk_ab', active: true, last_used_at: null,
  created_at: '2026-10-01T00:00:00Z', rate_per_minute: 0, effective_rate_per_minute: 120 };

describe('API-050 App 上的 Key 每分钟上限', () => {
  it('显示生效上限与来源，保存更低的上限', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/developer/api-keys': [KEY], '/developer/webhooks': [],
      'PUT /developer/api-keys/4/rate-limit': { id: 4, rate_per_minute: 30, effective_rate_per_minute: 30 } }, calls);
    render(<SubScreenHost client={client} screen="developer" onBack={() => undefined} onPublish={() => undefined} />);
    expect(await screen.findByText('每分钟最多 120 次（平台默认），超了会收到 429 并告诉你几秒后重试')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('Key 4 每分钟上限'), '30');
    fireEvent.press(screen.getByText('保存上限'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')).toEqual({ method: 'PUT', path: '/developer/api-keys/4/rate-limit', body: { rate_per_minute: 30 } }));
  });

  it('轮换：显示新 Key 与「只显示这一次」', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/developer/api-keys': [KEY], '/developer/webhooks': [],
      'POST /developer/api-keys/4/rotate': { id: 9, key: 'pk_new123', revoked_id: 4, warning: '旧密钥已立即失效；新密钥同样只显示这一次。' } }, calls);
    render(<SubScreenHost client={client} screen="developer" onBack={() => undefined} onPublish={() => undefined} />);
    fireEvent.press(await screen.findByText('轮换（旧 Key 立刻失效）'));
    expect(await screen.findByText(/pk_new123/)).toBeTruthy();
    expect(screen.getByText(/新密钥同样只显示这一次/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/developer/api-keys/4/rotate')).toBe(true);
  });
});
