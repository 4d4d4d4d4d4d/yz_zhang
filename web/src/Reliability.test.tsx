// REL-100 助手的可靠性（130 号 spec）：例行任务的运行合同、运行记录的状态、健康度；助手专家的完整角色契约。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const ROUTINE = {
  id: 4, name: '早报', kind: 'digest', freq: 'daily', time_of_day: '08:30', weekday: 0, monthday: 1, run_at: null, note: '',
  item_id: null, enabled: true, next_run_at: '2026-10-15T00:30:00Z', last_run_at: '2026-10-14T00:31:00Z', last_status: 'degraded',
  failures: 1, timeout_ms: 10000, max_retries: 2, degrade: true, retry_count: 0, pending_slot_at: null,
};
const RUN = (id: number, status: string, attempt: number, output: string) => ({
  id, status, output, started_at: '2026-10-14T00:31:00Z', slot_at: '2026-10-14T00:30:00Z', attempt, duration_ms: 12,
  cost_cents: 0, error_kind: status === 'ok' ? '' : 'RuntimeError', degraded: status === 'degraded',
});
type Call = { method: string; path: string; body?: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('REL-100 例行任务的运行合同', () => {
  it('新建默认带运行合同；列表写清重试与降级；运行记录写清状态与第几次尝试；健康度', async () => {
    const calls: Call[] = [];
    open('/workbench?tab=assistant', {
      '/users/me': ME, '/workbench/projects': [], 'GET /workbench/memories': { limit: 20, items: [] },
      'GET /workbench/routines': [ROUTINE], 'POST /workbench/routines': ROUTINE,
      '/workbench/routines/4/runs': [RUN(2, 'degraded', 3, '这次的内容没能完整生成'), RUN(1, 'retrying', 1, '运行失败（RuntimeError），1 分钟后重试')],
      '/workbench/routines/4/health': { routine_id: 4, runs: 3, success_rate: 0.5, delivered: 2, degraded: 1, retries: 1, skipped: 0, failed: 0,
        p50_ms: 12, p95_ms: 30, error_kinds: [{ kind: 'RuntimeError', count: 2 }], cost_cents: 0, contract: { timeout_ms: 10000, max_retries: 2, degrade: true } },
    }, calls);
    const row = await screen.findByText('早报');
    const li = row.closest('li')!;
    expect(li.textContent).toContain('上次降级送达');
    expect(li.textContent).toContain('失败重试 2 次，用尽后降级交付');
    fireEvent.click(screen.getByRole('button', { name: '运行记录' }));
    await waitFor(() => expect(li.textContent).toContain('降级送达（第 3 次尝试）'));
    expect(li.textContent).toContain('失败，等待重试');
    fireEvent.click(screen.getByRole('button', { name: '健康度' }));
    expect((await screen.findByLabelText('健康度：早报')).textContent).toContain('最近 3 次：成功率 50% · 降级 1 · 重试 1');
    expect(screen.getByLabelText('健康度：早报').textContent).toContain('RuntimeError 2 次');
    fireEvent.change(screen.getByLabelText('失败后重试'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: '添加例行任务' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/routines')).toBe(true));
    expect(calls.find((c) => c.method === 'POST' && c.path === '/workbench/routines')?.body).toMatchObject({ max_retries: 1, degrade: true, timeout_ms: 10000 });
  });
});

describe('REL-107 助手专家的角色契约', () => {
  it('问之前能看完整的角色契约：要什么、给什么、只用哪些工具、答不了怎么办', async () => {
    const card = {
      key: 'collab-basics', version: 1, title: '平台协作入门', segment: 'general', summary: '一页讲清托管、验收、纠纷',
      pains: ['不知道钱什么时候付'], enabled: false, enabled_version: null, upgrade_available: false, active_users: 3,
      published_at: '2026-10-13T00:00:00Z',
      assets: {
        assistants: [{ key: 'collab-advisor', name: '协作顾问', persona: '熟悉平台规则', inputs: ['问题'], outputs: ['说明'],
          forbidden: ['替你付款'], tools: ['pack.knowledge'], human_gates: ['付款、收款、转账、托管'] }],
        methods: [], knowledge: [], routines: [], task_templates: [],
      },
    };
    open('/packs?pack=collab-basics', {
      '/users/me': ME, '/packs': [card], '/packs/collab-basics': card,
      '/packs/collab-basics/assistants/collab-advisor/contract': {
        key: 'collab-advisor', name: '协作顾问', persona: '帮你理解平台规则', inputs: ['你的问题'], outputs: ['带出处的摘录'],
        forbidden: ['替你付款、收款或确认验收'], tools: [{ key: 'pack.knowledge', name: '本包的知识条目（带出处与有效期）' }],
        human_gates: [{ key: 'money', name: '付款、收款、转账、托管' }], fallback_category: '咨询',
      },
    }, []);
    fireEvent.click(await screen.findByRole('button', { name: '看完整的角色契约' }));
    const c = await screen.findByLabelText('角色契约：协作顾问');
    expect(c.textContent).toContain('需要你给：你的问题');
    expect(c.textContent).toContain('它给你：带出处的摘录');
    expect(c.textContent).toContain('只用这些工具：本包的知识条目（带出处与有效期）');
    expect(c.textContent).toContain('建议发一单「咨询」');
  });
});
