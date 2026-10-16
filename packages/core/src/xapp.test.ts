// XAPP-007 统一执行器驱动循环（161 号 spec）。
import { describe, expect, it } from 'vitest';
import { PlatformClient } from './client';
import { driveXappRun } from './xapp';

const step = (id: number, extra: Record<string, unknown> = {}) => ({ id, seq: id, app: 'com.autonavi.minimap', action: 'open', action_label: '打开',
  intent: '打开地图', channel: 'deeplink', vision_where: 'device', red_line: false, needs_confirm: false, confirmed: false,
  status: 'dispatched', attempts: 1, result: '', ...extra });

function fake(script: unknown[]) {
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  let i = 0;
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body = path.endsWith('/next') ? script[i++] : { run_status: 'running', step: step(1) };
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  return { client: new PlatformClient({ baseUrl: '', getToken: () => 't', fetchImpl }), calls };
}

describe('XAPP-007 driveXappRun', () => {
  it('执行 → 回报，一直走到需要人为止；红线步只调 handoff，不调 perform', async () => {
    const { client, calls } = fake([{ state: 'execute', step: step(1) }, { state: 'execute', step: step(2) },
      { state: 'handoff', step: step(3, { action: 'pay', action_label: '付款', red_line: true }) }]);
    const done: number[] = [];
    const handed: number[] = [];
    const last = await driveXappRun(client, 7, {
      perform: async (s) => { done.push(s.id); return { ok: true, summary: '好了' }; },
      handoff: async (s) => { handed.push(s.id); },
    });
    expect(done).toEqual([1, 2]);
    expect(handed).toEqual([3]);
    expect(last.state).toBe('handoff');
    expect(calls.filter((c) => c.path.endsWith('/result')).map((c) => c.body)).toEqual([{ ok: true, summary: '好了' }, { ok: true, summary: '好了' }]);
  });

  it('执行器抛错按失败回报；遇到叫停立刻返回', async () => {
    const { client, calls } = fake([{ state: 'execute', step: step(1) }, { state: 'stopped', reason: '本人叫停' }]);
    const last = await driveXappRun(client, 7, { perform: async () => { throw new Error('找不到按钮'); } });
    expect(calls.find((c) => c.path.endsWith('/result'))?.body).toEqual({ ok: false, summary: '找不到按钮' });
    expect(last).toEqual({ state: 'stopped', reason: '本人叫停' });
  });
});
