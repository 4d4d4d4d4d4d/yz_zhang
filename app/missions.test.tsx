// ORC-066 / AGT-084 AI 编排在 App 上的行为（131 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { MissionsScreen } from './missions';
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
const MISSION = {
  id: 7, owner_id: 2, goal: '周六搬家', detail: '', category: '跑腿', status: 'running', budget_cap_cents: 30000, committed_cents: 21000,
  spent_cents: 0, iteration: 1, max_iterations: 3, completion_pct: 0, quality_pct: 0, model_calls: 0, allow_agents: false,
  allow_tools: true, acceptance_criteria: [], last_error: '', created_at: '2026-10-14T00:00:00Z',
};
const STEP = {
  id: 3, iteration: 0, tool: 'publish_task', title: '周六搬家 - 打包', task_id: 11, status: 'dispatched', observation: '', is_remedy: false,
  agent_user_id: null, budget_cents: 21000, parent_step_id: null, attempt: 1, acceptance: [], review_verdict: '', review_score: 0, review_missing: [],
  tool_drafts: [{ invocation_id: 41, unit_id: 5, version: 1, label: '由经验单元生成，未经人工确认', text: '☐ 易碎品单独装箱', status: 'pending' }],
};

describe('AGT-094 App 上按自己的方法拆第一轮', () => {
  it('选了方法就带 method_id，再点一下取消', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /missions': [], '/notebook/methods': [{ id: 5, name: '我的搬家做法', description: '', steps: [{ title: '打包', note: '' }, { title: '搬运', note: '' }], source_note_ids: [], uses: 0, created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z' }], 'POST /missions': { ...MISSION, method_id: 5 },
      '/missions/7': { ...MISSION, method_id: 5, steps: [], timeline: [] } }, calls);
    render(<MissionsScreen client={client} />);
    fireEvent.changeText(await screen.findByLabelText('目标'), '周六搬家');
    fireEvent.press(await screen.findByText('按「我的搬家做法」拆（2 步）'));
    expect(screen.getByText('第一轮怎么拆：按我的方法「我的搬家做法」')).toBeTruthy();
    fireEvent.press(screen.getByText('建好，先不花钱'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/missions')?.body)
      .toEqual({ goal: '周六搬家', budget_cap_cents: 30000, allow_tools: true, method_id: 5 }));
  });
});

describe('ORC-066 App 上的 AI 编排', () => {
  it('新建（默认授权经验工具）→ 打开详情 → 采用草稿 → 推进一轮', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      'GET /missions': [], 'POST /missions': MISSION, '/missions/7': { ...MISSION, steps: [STEP], timeline: [] },
      'POST /missions/7/steps/3/drafts/41/adopt': { step_id: 3, invocation_id: 41, status: 'adopted' },
      'POST /missions/7/summary/save': { note_id: 9, created: false, title: '编排复盘：周六搬家（#7）', saved_at: '2026-10-14T01:00:00Z' },
      '/missions/7/summary': { mission_id: 7, goal: '周六搬家', status: 'running', rounds: 1, max_rounds: 3, spent_cents: 0, committed_cents: 21000, cap_cents: 30000,
        steps_total: 1, steps_done: 0, steps_failed: 0, remedies: 0, avg_review_score: null, drafts_total: 1, drafts_adopted: 0, duration_days: null,
        highlights: ['经验工具生成 1 份草稿，你采用了 0 份'], next: '还在进行：推进下一轮，或等已发布的任务有人接' },
      'POST /missions/7/tick': { action: 'waiting', status: 'running', total_steps: 1, done: 0, failed: 0, superseded: 0, completion_pct: 0, quality_pct: 0 },
    }, calls);
    render(<MissionsScreen client={client} />);
    fireEvent.changeText(await screen.findByLabelText('目标'), '周六搬家');
    fireEvent.press(screen.getByText('建好，先不花钱'));
    expect(await screen.findByText('预算：已付 ¥0.00，占用 ¥210.00，上限 ¥300.00')).toBeTruthy();
    expect(calls.find((c) => c.method === 'POST' && c.path === '/missions')?.body).toEqual({ goal: '周六搬家', budget_cap_cents: 30000, allow_tools: true });
    expect(screen.getByText('由经验单元生成，未经人工确认 · 待你确认')).toBeTruthy();
    expect(await screen.findByText('下一步：还在进行：推进下一轮，或等已发布的任务有人接')).toBeTruthy();
    expect(screen.getByText('• 经验工具生成 1 份草稿，你采用了 0 份')).toBeTruthy();
    fireEvent.press(screen.getByText('存进我的知识库'));
    expect(await screen.findByText('已更新知识库里的「编排复盘：周六搬家（#7）」')).toBeTruthy();
    fireEvent.press(screen.getByText('采用'));
    expect(await screen.findByText('已采用（只是标记，没有发给任何人）')).toBeTruthy();
    fireEvent.press(screen.getByText('推进一轮'));
    await waitFor(() => expect(calls.some((c) => c.path === '/missions/7/tick')).toBe(true));
  });

  it('工作台：本月助手成本与上限', async () => {
    const client = makeClient({
      '/workbench/overview': { counts: { overdue: 0, today: 0, doing: 0, blocked: 0, stale: 0, done_this_week: 0, open: 0 }, overdue: [], today: [], doing: [],
        blocked: [], stale: [], done_this_week: [], projects: [], platform: { to_choose: [], to_accept: [], executing: [] }, summary: '' },
      'GET /workbench/memories': { limit: 20, items: [] }, 'GET /workbench/routines': [],
      '/users/me/assistant-costs': { month: '2026-10', agent_tools_cents: 30, routines_cents: 0, total_cents: 30, cap_cents: 2000, remaining_cents: 1970, agent_calls: 1 },
    }, []);
    render(<WorkbenchScreen client={client} />);
    fireEvent.press(await screen.findByText('助手'));
    expect(await screen.findByText('本月助手成本 ¥0.30 / 上限 ¥20.00（经验工具 1 次）')).toBeTruthy();
  });
});
