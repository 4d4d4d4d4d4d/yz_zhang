// REL-100 助手的可靠性在 App 上的行为（130 号 spec）：新建带运行合同、状态写清、健康度；助手的完整角色契约。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { PacksScreen } from './packs';
import { WorkbenchScreen } from './workbench';

type Call = { method: string; path: string; body?: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    const hit = Object.keys(routes).find((k) => k === `${method} ${path}`) ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const OVERVIEW = {
  counts: { overdue: 0, today: 0, doing: 0, blocked: 0, stale: 0, done_this_week: 0, open: 0 },
  overdue: [], today: [], doing: [], blocked: [], stale: [], done_this_week: [], projects: [],
  platform: { to_choose: [], to_accept: [], executing: [] }, summary: '',
};
const ROUTINE = {
  id: 4, name: '早报', kind: 'digest', freq: 'daily', time_of_day: '08:30', weekday: 0, monthday: 1, run_at: null, note: '',
  item_id: null, enabled: true, next_run_at: '2026-10-15T00:30:00Z', last_run_at: null, last_status: 'degraded', failures: 1,
  timeout_ms: 10000, max_retries: 2, degrade: true, retry_count: 0, pending_slot_at: null,
};

describe('REL-100 App 上的可靠性', () => {
  it('例行任务：写清重试与降级、上次降级送达、健康度；新建默认带运行合同', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/workbench/overview': OVERVIEW, 'GET /workbench/memories': { limit: 20, items: [] }, 'GET /workbench/routines': [ROUTINE],
      'POST /workbench/routines': ROUTINE,
      '/workbench/routines/4/health': { routine_id: 4, runs: 4, success_rate: 0.75, delivered: 4, degraded: 1, retries: 2, skipped: 0, failed: 0,
        p50_ms: 8, p95_ms: 20, error_kinds: [], cost_cents: 0, contract: { timeout_ms: 10000, max_retries: 2, degrade: true } },
    }, calls);
    render(<WorkbenchScreen client={client} />);
    fireEvent.press(await screen.findByText('助手'));
    expect(await screen.findByText(/上次降级送达/)).toBeTruthy();
    expect(screen.getByText('失败重试 2 次，用尽后降级交付')).toBeTruthy();
    fireEvent.press(screen.getByText('健康度'));
    expect((await screen.findByLabelText('健康度：早报')).props.children.join('')).toContain('成功率 75% · 降级 1 · 重试 2');
    fireEvent.press(screen.getByText('每天早上的概览'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/workbench/routines')?.body)
      .toMatchObject({ max_retries: 2, degrade: true, timeout_ms: 10000 }));
  });

  it('助手专家：看完整的角色契约', async () => {
    const card = {
      key: 'collab-basics', version: 1, title: '平台协作入门', segment: 'general', summary: '', pains: [], enabled: false, enabled_version: null,
      upgrade_available: false, active_users: 0, published_at: '',
      assets: { assistants: [{ key: 'collab-advisor', name: '协作顾问', persona: '熟悉平台规则', inputs: [], outputs: [], forbidden: [], tools: [],
        human_gates: ['付款、收款、转账、托管'] }], methods: [], knowledge: [], routines: [], task_templates: [] },
    };
    const client = makeClient({
      '/packs': [card],
      '/packs/collab-basics/assistants/collab-advisor/contract': { key: 'collab-advisor', name: '协作顾问', persona: '', inputs: ['你的问题'],
        outputs: ['带出处的摘录'], forbidden: ['替你付款、收款或确认验收'], tools: [{ key: 'pack.knowledge', name: '本包的知识条目' }],
        human_gates: [{ key: 'money', name: '付款、收款、转账、托管' }], fallback_category: '' },
    }, []);
    render(<PacksScreen client={client} />);
    fireEvent.press(await screen.findByText('平台协作入门'));
    fireEvent.press(await screen.findByText('看完整的角色契约'));
    expect(await screen.findByText('不会做：替你付款、收款或确认验收')).toBeTruthy();
    expect(screen.getByText('只用这些工具：本包的知识条目')).toBeTruthy();
  });
});
