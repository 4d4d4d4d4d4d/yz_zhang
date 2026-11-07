// XAPP-007 统一执行器驱动循环（161 号 spec）。
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { PlatformClient } from './client';
import type { XappCatalog, XappPlanRules } from './types';
import { driveXappRun, planXappLocally, planXappSteps } from './xapp';

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

// XAPP-015：本机出计划与服务端规则出计划是同一个算法。两边读同一份例子文件，任何一边改了算法另一边就红。
const CASES = JSON.parse(readFileSync(new URL('./xapp-plan-cases.json', import.meta.url), 'utf8')) as {
  rules: XappPlanRules; cases: Array<{ goal: string; apps: string[]; expect: Array<{ app: string; action: string; channel: string; red_line: boolean }> }>;
};
const RED = ['pay', 'transfer', 'sign', 'publish', 'send_message', 'change_security', 'delete'];

describe('XAPP-015 本机出计划（隐私沙箱）', () => {
  it('每个例子都与服务端规则出的计划一模一样', () => {
    expect(CASES.cases.length).toBeGreaterThanOrEqual(8);
    for (const c of CASES.cases) {
      const got = planXappSteps(c.goal, c.apps, CASES.rules, {}, new Set(RED))
        .map(({ app, action, channel, red_line }) => ({ app, action, channel, red_line }));
      expect(got, c.goal).toEqual(c.expect);
    }
  });

  it('App 名字里的字不当动作；红线步标出来；没授权的动作列出来；不联网', () => {
    const catalog: XappCatalog = { actions: [{ key: 'open', label: '打开' }, { key: 'read', label: '读取页面' }],
      red_line: RED.map((key) => ({ key, label: key === 'transfer' ? '转账' : key })), channels: [], executors: [], notice: '',
      plan_rules: CASES.rules };
    const p = planXappLocally('在支付宝给房东转账两千块', { id: 3, apps: ['com.eg.android.AlipayGphone'], actions: ['open'] }, catalog);
    expect(p.source).toBe('device_rules');
    expect(p.steps.map((s) => s.action)).toEqual(['open', 'transfer']);
    expect(p.steps[1]).toMatchObject({ red_line: true, action_label: '转账' });
    expect(p.ready).toBe(true);
    expect(p.notes.join('')).toContain('目标原文没有发出去');
    const q = planXappLocally('查看今天的订单', { id: 4, apps: ['com.sankuai.meituan'], actions: ['open'] }, catalog);
    expect(q.missing_actions).toEqual(['read']);
    expect(q.ready).toBe(false);
    expect(q.notes.join('')).toContain('读取页面');
  });
});
