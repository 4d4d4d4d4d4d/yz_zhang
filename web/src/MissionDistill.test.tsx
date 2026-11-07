// AGT-093（154 号 spec）沿用 ORC-066 / AGT-084 AI 编排（131 号 spec）：新建（默认授权经验工具）、推进、经验工具草稿采用 / 丢弃、收回授权；工作台显示本月助手成本。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};
const MISSION = {
  id: 7, owner_id: 2, goal: '周六搬家', detail: '', category: '跑腿', status: 'running', budget_cap_cents: 30000, committed_cents: 21000,
  spent_cents: 0, iteration: 1, max_iterations: 3, completion_pct: 0, quality_pct: 0, model_calls: 0, allow_agents: false,
  allow_tools: true, acceptance_criteria: [], last_error: '', created_at: '2026-10-14T00:00:00Z',
};
const STEP = {
  id: 3, iteration: 0, tool: 'publish_task', title: '周六搬家 - 打包', task_id: 11, status: 'dispatched', observation: '', is_remedy: false,
  agent_user_id: null, budget_cents: 21000, parent_step_id: null, attempt: 1, acceptance: [], review_verdict: '', review_score: 0, review_missing: [],
  tool_drafts: [{ invocation_id: 41, unit_id: 5, version: 1, label: '由经验单元「搬家·打包」（第 1 版）生成，未经人工确认', text: '验收报告草稿：☐ 易碎品单独装箱', status: 'pending' }],
};
type Call = { method: string; path: string; body?: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : (p === '/users/me' ? ME : [])) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

const SUMMARY = { mission_id: 7, goal: '周六搬家', status: 'succeeded', rounds: 1, max_rounds: 3, spent_cents: 21000, committed_cents: 0, cap_cents: 30000,
  steps_total: 2, steps_done: 1, steps_failed: 1, remedies: 0, avg_review_score: null, drafts_total: 0, drafts_adopted: 0, duration_days: 0,
  highlights: [], next: '存进个人知识库' };
const DRAFT = { name: '周六搬家的做法', steps: [{ title: '周六搬家 - 打包', note: '易碎品单独装箱' }], source_note_ids: [9],
  found: 'mission_steps', note_id: 9, note_title: '编排复盘：周六搬家（#7）', skipped_steps: 1 };

describe('AGT-093 复盘蒸馏成我的方法', () => {
  it('蒸馏只出草稿（列出做成了的步骤、说明没收进来的），确认后才保存为方法', async () => {
    const calls: Call[] = [];
    open('/missions?id=7', {
      'GET /missions': [MISSION], '/missions/7': { ...MISSION, status: 'succeeded', steps: [STEP], timeline: [] },
      '/missions/7/summary': SUMMARY,
      'POST /missions/7/summary/distill': DRAFT,
      'POST /notebook/methods': { id: 3, name: '周六搬家的做法', description: '', steps: DRAFT.steps, source_note_ids: [9], uses: 0,
        created_at: '2026-10-15T00:00:00Z', updated_at: '2026-10-15T00:00:00Z' },
    }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '蒸馏成我的方法' }));
    const box = await screen.findByLabelText('方法草稿');
    expect(box.textContent).toContain('周六搬家的做法');
    expect(box.textContent).toContain('1 步没做成，没收进来');
    expect(box.textContent).toContain('周六搬家 - 打包：易碎品单独装箱');
    expect(calls.some((c) => c.path === '/notebook/methods' && c.method === 'POST')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '保存为我的方法' }));
    await screen.findByText(/已保存为你的方法/);
    expect(calls.find((c) => c.method === 'POST' && c.path === '/notebook/methods')?.body)
      .toEqual({ name: '周六搬家的做法', steps: DRAFT.steps, source_note_ids: [9] });
  });

  it('还没有做成的步骤：如实说，不给保存按钮', async () => {
    const calls: Call[] = [];
    open('/missions?id=7', {
      'GET /missions': [MISSION], '/missions/7': { ...MISSION, steps: [STEP], timeline: [] }, '/missions/7/summary': SUMMARY,
      'POST /missions/7/summary/distill': { ...DRAFT, steps: [], found: 'none', skipped_steps: 0 },
    }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '蒸馏成我的方法' }));
    expect((await screen.findByLabelText('方法草稿')).textContent).toContain('还没有做成的步骤');
    expect(screen.queryByRole('button', { name: '保存为我的方法' })).toBeNull();
  });

  it('AGT-100 用了方法的编排：起草方法备注的修改建议，勾选后写回（只写勾了的）', async () => {
    const calls: Call[] = [];
    open('/missions?id=7', {
      'GET /missions': [MISSION], '/missions/7': { ...MISSION, method_id: 3, status: 'succeeded', steps: [STEP], timeline: [] },
      '/missions/7/summary': SUMMARY,
      '/missions/7/method-suggestions': { method_id: 3, method_name: '我的搬家做法', method_version: 1, note: '',
  suggestions: [{ title: '打包', current_note: '易碎品单独装箱', suggested_note: '易碎品单独装箱；上次这一步没做到：缺装箱照片', reason: '试了 2 次才做成', fixed_items: ['易碎品没有标记'], fixed_on_attempt: 2 },
    { title: '搬运', current_note: '', suggested_note: '上次这一步没做成：没人接单', reason: '试了 2 次仍没做成' }] },
      'POST /missions/7/method-suggestions/apply': { id: 3, name: '我的搬家做法', description: '', steps: [], source_note_ids: [], uses: 1,
        created_at: '', updated_at: '', version: 2 },
    }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '用这次的问题改进我的方法' }));
    const box = await screen.findByLabelText('方法改进建议');
    expect(box.textContent).toContain('给「我的搬家做法」（第 1 版）的建议');
    expect(box.textContent).toContain('易碎品单独装箱 → 易碎品单独装箱；上次这一步没做到：缺装箱照片');
    expect(box.textContent).toContain('（原来没有备注）');
    expect(box.textContent).toContain('（第 2 次补上了：易碎品没有标记）');
    expect(calls.some((c) => c.path === '/missions/7/method-suggestions/apply')).toBe(false);
    fireEvent.click(within(box).getAllByRole('checkbox')[1]);
    fireEvent.click(screen.getByRole('button', { name: '写回我的方法' }));
    await waitFor(() => expect(calls.find((c) => c.path === '/missions/7/method-suggestions/apply')?.body).toEqual({ titles: ['打包'] }));
    expect((await screen.findByRole('status')).textContent).toBe('已写回「我的搬家做法」，现在是第 2 版');
  });

  it('没用方法的编排不显示这个入口', async () => {
    open('/missions?id=7', { 'GET /missions': [MISSION], '/missions/7': { ...MISSION, method_id: null, status: 'succeeded', steps: [STEP], timeline: [] },
      '/missions/7/summary': SUMMARY }, []);
    await screen.findByRole('button', { name: '蒸馏成我的方法' });
    expect(screen.queryByRole('button', { name: '用这次的问题改进我的方法' })).toBeNull();
  });
});

