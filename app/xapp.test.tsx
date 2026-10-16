// XAPP 跨 App 助手在 App 上（161 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { XappScreen } from './xapp';

type Call = { method: string; path: string; body: unknown };
const STEP = (id: number, extra: Record<string, unknown> = {}) => ({ id, seq: id, app: 'com.tencent.mm', action: 'open', action_label: '打开',
  intent: `第 ${id} 步`, channel: 'deeplink', vision_where: 'device', red_line: false, needs_confirm: false, confirmed: false,
  status: 'pending', attempts: 0, result: '', ...extra });
const RUN = { id: 9, grant_id: 1, goal: '告诉客户预计到达时间', executor: 'mock', confirm_mode: 'red_only', status: 'running',
  stop_reason: '', created_at: '2026-10-15T00:00:00Z', finished_at: null };

function makeClient(routes: Record<string, unknown>, calls: Call[], seq: unknown[] = []) {
  let i = 0;
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body = path.endsWith('/next') ? seq[i++] : routes[`${method} ${path}`] ?? routes[path] ?? [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const BASE = {
  '/xapp/catalog': { actions: [], red_line: [], channels: [], executors: [], notice: '付款、签署只能由你亲手完成；屏幕内容默认只在本机处理。' },
  'GET /xapp/grants': [{ id: 1, device_label: '这台手机', apps: ['com.tencent.mm'], actions: ['open'], allow_cloud_vision: false,
    expires_at: '2026-10-22T00:00:00Z', revoked_at: null, active: true, created_at: '2026-10-15T00:00:00Z' }],
  'GET /xapp/runs': [RUN],
  'GET /xapp/runs/9': { ...RUN, steps: [STEP(1), STEP(2, { action: 'send_message', action_label: '对外发消息', red_line: true, needs_confirm: true })] },
};

describe('XAPP App 上的跨 App 助手', () => {
  it('说明红线、可以授权、红线步写明要亲手完成并能确认、可以叫停', async () => {
    const calls: Call[] = [];
    const client = makeClient({ ...BASE, 'POST /xapp/grants': BASE['GET /xapp/grants'][0],
      'POST /xapp/runs/9/steps/2/confirm': { run_status: 'done', step: STEP(2) }, 'POST /xapp/runs/9/stop': { ...RUN, status: 'stopped' } }, calls);
    render(<XappScreen client={client} />);
    expect(await screen.findByText(/屏幕内容默认只在本机处理/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('目标 App'), 'com.autonavi.minimap, com.tencent.mm');
    fireEvent.press(screen.getByText('授权'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/xapp/grants')?.body)
      .toMatchObject({ apps: ['com.autonavi.minimap', 'com.tencent.mm'], days: 7 }));
    fireEvent.press(await screen.findByText('看步骤'));
    expect(await screen.findByText('这一步要你亲手完成，智能体只会把你带到那个页面')).toBeTruthy();
    fireEvent.press(screen.getByText('我已亲手完成这一步'));
    await waitFor(() => expect(calls.some((c) => c.path === '/xapp/runs/9/steps/2/confirm')).toBe(true));
    fireEvent.press(screen.getByText('一键叫停'));
    await waitFor(() => expect(calls.find((c) => c.path === '/xapp/runs/9/stop')?.body).toEqual({ reason: '本人叫停' }));
  });

  it('发起一次示例执行：计划只用授权里的 App，发消息那步按红线交给你', async () => {
    const calls: Call[] = [];
    const client = makeClient({ ...BASE, 'POST /xapp/runs': RUN }, calls);
    render(<XappScreen client={client} />);
    fireEvent.press(await screen.findByText('发起一次示例执行（模拟执行器）'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/xapp/runs')?.body).toMatchObject({
      grant_id: 1, executor: 'mock', confirm_mode: 'red_only',
      steps: [{ app: 'com.tencent.mm', action: 'open' }, { app: 'com.tencent.mm', action: 'send_message' }] }));
    expect(await screen.findByText('已发起，看下面的步骤')).toBeTruthy();
    expect(calls.some((c) => c.method === 'GET' && c.path === '/xapp/runs/9')).toBe(true);
  });

  it('模拟执行器试跑：只走协议，停在需要你的那一步', async () => {
    const calls: Call[] = [];
    const client = makeClient({ ...BASE, 'POST /xapp/runs/9/steps/1/result': { run_status: 'running', step: STEP(1) } }, calls,
      [{ state: 'execute', step: STEP(1) }, { state: 'awaiting_confirm', step: STEP(2) }]);
    render(<XappScreen client={client} />);
    fireEvent.press(await screen.findByText('看步骤'));
    fireEvent.press(await screen.findByText('用模拟执行器试跑（不会真的操作其他 App）'));
    expect(await screen.findByText('停在这里：等你确认或亲手完成')).toBeTruthy();
    expect(calls.find((c) => c.path === '/xapp/runs/9/steps/1/result')?.body).toEqual({ ok: true, summary: '模拟完成：第 1 步' });
  });
});
