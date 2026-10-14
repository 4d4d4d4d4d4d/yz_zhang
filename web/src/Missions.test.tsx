// ORC-066 / AGT-084 AI 编排（131 号 spec）：新建（默认授权经验工具）、推进、经验工具草稿采用 / 丢弃、收回授权；工作台显示本月助手成本。
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

describe('ORC-066 AI 编排', () => {
  it('新建：带预算上限与验收要点，默认授权经验工具；建好先不花钱', async () => {
    const calls: Call[] = [];
    open('/missions', { 'GET /missions': [], 'POST /missions': MISSION, '/missions/7': { ...MISSION, steps: [], timeline: [] } }, calls);
    fireEvent.change(await screen.findByLabelText('目标'), { target: { value: '周六搬家' } });
    fireEvent.change(screen.getByLabelText('预算上限'), { target: { value: '300' } });
    fireEvent.change(screen.getByLabelText('验收要点'), { target: { value: '物品无损\n现场清洁' } });
    fireEvent.click(screen.getByRole('button', { name: '建好，先不花钱' }));
    await screen.findByText('已建好：点「推进一轮」开始规划和分发');
    expect(calls.find((c) => c.method === 'POST' && c.path === '/missions')?.body).toEqual({
      goal: '周六搬家', detail: '', category: '跑腿', budget_cap_cents: 30000, max_iterations: 3,
      acceptance_criteria: ['物品无损', '现场清洁'], allow_agents: false, allow_tools: true,
    });
  });

  it('详情：预算与步骤看得见；经验工具草稿采用只是标记；推进一轮；收回授权', async () => {
    const calls: Call[] = [];
    open('/missions?id=7', {
      'GET /missions': [MISSION], '/missions/7': { ...MISSION, steps: [STEP], timeline: [{ iteration: 1, action: 'tool_draft', summary: '用经验工具生成了草稿，等你确认', at: '2026-10-14T00:01:00Z' }] },
      'POST /missions/7/steps/3/drafts/41/adopt': { step_id: 3, invocation_id: 41, status: 'adopted' },
      'POST /missions/7/summary/save': { note_id: 9, created: true, title: '编排复盘：周六搬家（#7）', saved_at: '2026-10-14T01:00:00Z' },
      '/missions/7/summary': { mission_id: 7, goal: '周六搬家', status: 'running', rounds: 1, max_rounds: 3, spent_cents: 0, committed_cents: 21000, cap_cents: 30000,
        steps_total: 1, steps_done: 0, steps_failed: 0, remedies: 0, avg_review_score: null, drafts_total: 1, drafts_adopted: 0, duration_days: null,
        highlights: ['经验工具生成 1 份草稿，你采用了 0 份'], next: '还在进行：推进下一轮，或等已发布的任务有人接' },
      'POST /missions/7/tick': { action: 'waiting', status: 'running', total_steps: 1, done: 0, failed: 0, superseded: 0, completion_pct: 0, quality_pct: 0 },
      'PUT /missions/7/tools': { ...MISSION, allow_tools: false },
    }, calls);
    const d = await screen.findByLabelText('编排详情');
    await waitFor(() => expect(d.textContent).toContain('占用 ¥210.00，上限 ¥300.00'));
    expect(screen.getByLabelText('经验工具草稿').textContent).toContain('未经人工确认');
    const sum = await screen.findByLabelText('复盘');
    expect(sum.textContent).toContain('1/3 轮 · 完成 0/1 步 · 整改 0 次');
    expect(sum.textContent).toContain('下一步：还在进行');
    fireEvent.click(screen.getByRole('button', { name: '存进我的知识库' }));
    await screen.findByText('已存进你的知识库：「编排复盘：周六搬家（#7）」');
    expect(screen.getByLabelText('经验工具草稿').textContent).toContain('待你确认');
    fireEvent.click(screen.getByRole('button', { name: '采用' }));
    await screen.findByText('已采用（只是标记，没有发给任何人）');
    expect(calls.some((c) => c.method === 'POST' && c.path === '/missions/7/steps/3/drafts/41/adopt')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '推进一轮' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/missions/7/tick')).toBe(true));
    fireEvent.click(screen.getByLabelText('允许用经验工具生成草稿'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ allow_tools: false }));
  });

  it('工作台显示本月助手成本与上限，并指向 AI 编排', async () => {
    open('/workbench?tab=assistant', {
      '/workbench/projects': [], 'GET /workbench/memories': { limit: 20, items: [] }, 'GET /workbench/routines': [],
      '/users/me/assistant-costs': { month: '2026-10', agent_tools_cents: 30, routines_cents: 0, total_cents: 30, cap_cents: 2000, remaining_cents: 1970, agent_calls: 1 },
    }, []);
    const c = await screen.findByLabelText('本月助手成本');
    expect(c.textContent).toContain('本月助手成本 ¥0.30 / 上限 ¥20.00（经验工具 1 次）');
    expect(c.querySelector('a')?.getAttribute('href')).toBe('/missions');
  });
});
