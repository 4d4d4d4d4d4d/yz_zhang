// AGT-093 App 上复盘蒸馏成我的方法（154 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { MissionsScreen } from './missions';

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

const DRAFT = { name: '周六搬家的做法', steps: [{ title: '周六搬家 - 打包', note: '易碎品单独装箱' }], source_note_ids: [9],
  found: 'mission_steps', note_id: 9, note_title: '编排复盘：周六搬家（#7）', skipped_steps: 1 };

describe('AGT-093 App 上复盘蒸馏成我的方法', () => {
  it('蒸馏只出草稿，确认后才保存为方法', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      'GET /missions': [MISSION], '/missions/7': { ...MISSION, steps: [STEP], timeline: [] },
      '/missions/7/summary': { mission_id: 7, goal: '周六搬家', status: 'succeeded', rounds: 1, max_rounds: 3, spent_cents: 21000, committed_cents: 0, cap_cents: 30000,
        steps_total: 2, steps_done: 1, steps_failed: 1, remedies: 0, avg_review_score: null, drafts_total: 0, drafts_adopted: 0, duration_days: 0,
        highlights: [], next: '存进个人知识库' },
      'POST /missions/7/summary/distill': DRAFT,
      'POST /notebook/methods': { id: 3, name: '周六搬家的做法', description: '', steps: DRAFT.steps, source_note_ids: [9], uses: 0,
        created_at: '2026-10-15T00:00:00Z', updated_at: '2026-10-15T00:00:00Z' },
    }, calls);
    render(<MissionsScreen client={client} />);
    fireEvent.press(await screen.findByText('周六搬家'));
    fireEvent.press(await screen.findByText('蒸馏成我的方法'));
    expect(await screen.findByText('周六搬家的做法（1 步；1 步没做成，没收进来）')).toBeTruthy();
    expect(screen.getByText('1. 周六搬家 - 打包：易碎品单独装箱')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/notebook/methods')).toBe(false);
    fireEvent.press(screen.getByText('保存为我的方法'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/notebook/methods')?.body)
      .toEqual({ name: '周六搬家的做法', steps: DRAFT.steps, source_note_ids: [9] }));
  });
});

describe('AGT-100 App 用这次的问题改进方法', () => {
  it('点开看建议、取消一项、写回只带勾了的', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      'GET /missions': [MISSION], '/missions/7': { ...MISSION, method_id: 3, steps: [STEP], timeline: [] },
      '/missions/7/summary': { mission_id: 7, goal: '周六搬家', status: 'succeeded', rounds: 1, max_rounds: 3, spent_cents: 21000, committed_cents: 0, cap_cents: 30000,
        steps_total: 2, steps_done: 1, steps_failed: 1, remedies: 1, avg_review_score: null, drafts_total: 0, drafts_adopted: 0, duration_days: 0,
        highlights: [], next: '存进个人知识库' },
      '/missions/7/method-suggestions': { method_id: 3, method_name: '我的搬家做法', method_version: 1, note: '',
  suggestions: [{ title: '打包', current_note: '易碎品单独装箱', suggested_note: '易碎品单独装箱；上次这一步没做到：缺装箱照片', reason: '试了 2 次才做成' },
    { title: '搬运', current_note: '', suggested_note: '上次这一步没做成：没人接单', reason: '试了 2 次仍没做成' }] },
      'POST /missions/7/method-suggestions/apply': { id: 3, name: '我的搬家做法', description: '', steps: [], source_note_ids: [], uses: 1,
        created_at: '', updated_at: '', version: 2 },
    }, calls);
    render(<MissionsScreen client={client} />);
    fireEvent.press(await screen.findByText('周六搬家'));
    fireEvent.press(await screen.findByText('用这次的问题改进我的方法'));
    expect(await screen.findByText('易碎品单独装箱 → 易碎品单独装箱；上次这一步没做到：缺装箱照片')).toBeTruthy();
    fireEvent.press(screen.getByText('☑ 搬运（试了 2 次仍没做成）'));
    fireEvent.press(screen.getByText('写回我的方法'));
    await waitFor(() => expect(calls.find((c) => c.path === '/missions/7/method-suggestions/apply')?.body).toEqual({ titles: ['打包'] }));
    expect(await screen.findByText('已写回「我的搬家做法」，现在是第 2 版')).toBeTruthy();
  });
});
