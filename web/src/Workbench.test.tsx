// PWB 个人工作台（116 号 spec）：我的任务、进度与助手。
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

const item = (id: number, title: string, extra: Record<string, unknown> = {}) => ({
  id, project_id: null, parent_id: null, title, notes: '', status: 'todo', status_name: '待办', priority: 1,
  category: '', due_at: null, remind_at: null, progress: 0, progress_source: 'manual', children_total: 0,
  children_done: 0, tags: [], linked_task: null, revision: 0, created_at: '2026-10-13T00:00:00Z',
  updated_at: '2026-10-13T00:00:00Z', completed_at: null, ...extra,
});

const OVERVIEW = {
  counts: { overdue: 1, today: 0, doing: 0, blocked: 0, stale: 0, done_this_week: 0, open: 1 },
  overdue: [item(7, '交房租', { due_at: '2026-10-12T00:00:00Z' })], today: [], doing: [], blocked: [], stale: [], done_this_week: [],
  projects: [{ id: 1, name: '家里的事', color: 'clay', total: 2, done: 1, progress: 50 }],
  platform: { to_choose: [{ task_id: 9, title: '三居室保洁', applicants: 2 }], to_accept: [], executing: [] },
  summary: '今天到期 0 项；已逾期 1 项：「交房租」；进行中 0 项；卡住 0 项。平台上：1 单有人报名等你选人。',
};

function open(path: string, routes: Record<string, unknown>, calls: Array<{ method: string; path: string; body?: unknown }> = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('PWB 个人工作台', () => {
  it('导航里有「工作台」，原有的导航项一个不少', async () => {
    open('/', { '/users/me': ME, '/spaces': { items: [], next_cursor: null } });
    const nav = await screen.findByRole('navigation', { name: '工作台导航' });
    for (const label of ['发现', '合作', '工作台', '消息', '我的空间']) {
      expect(nav.textContent).toContain(label);
    }
  });

  it('「今天」显示助手概览、逾期任务和平台上等我处理的单', async () => {
    open('/workbench', { '/users/me': ME, '/workbench/overview': OVERVIEW, '/workbench/projects': [] });
    expect((await screen.findByTestId('wb-summary')).textContent).toContain('已逾期 1 项');
    expect(screen.getByText('已逾期（1）')).toBeTruthy();
    expect(screen.getByRole('link', { name: '三居室保洁' }).getAttribute('href')).toBe('/tasks/9');
    expect(screen.getByText(/2 人报名，等你选人/)).toBeTruthy();
    expect(screen.getByText(/家里的事 · 1\/2/)).toBeTruthy();
  });

  it('快速添加一条带项目的任务', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    open('/workbench?tab=all', {
      '/users/me': ME, '/workbench/projects': [{ id: 3, name: '报税', color: 'clay', archived: false, sort: 0, created_at: '' }],
      'GET /workbench/items': [], 'POST /workbench/items': item(1, '整理发票'),
    }, calls);
    await screen.findByRole('option', { name: '报税' });
    fireEvent.change(screen.getByLabelText('新任务'), { target: { value: '整理发票' } });
    fireEvent.change(screen.getByLabelText('所属项目'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: '添加' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/items')).toBe(true));
    const post = calls.find((c) => c.method === 'POST' && c.path === '/workbench/items');
    expect(post?.body).toMatchObject({ title: '整理发票', project_id: 3, due_at: null });
  });

  it('让助手拆一下：先给草稿，去掉一项后确认，才写入清单', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    open('/workbench?tab=all&item=5', {
      '/users/me': ME, '/workbench/projects': [], 'GET /workbench/items': [item(5, '搬家')],
      'GET /workbench/items/5': { ...item(5, '搬家'), children: [] }, '/workbench/items/5/logs': [],
      'POST /workbench/items/5/breakdown': { source: 'generic', steps: [
        { title: '列物品清单', note: '' }, { title: '找搬家公司', note: '' }, { title: '退押金', note: '' }] },
      'POST /workbench/items/5/children': { ...item(5, '搬家'), children: [] },
    }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '让助手拆一下' }));
    expect(await screen.findByText('列物品清单')).toBeTruthy();
    expect(calls.some((c) => c.path === '/workbench/items/5/children')).toBe(false);   // 只是草稿
    fireEvent.click(screen.getByRole('button', { name: '去掉：退押金' }));
    fireEvent.click(screen.getByRole('button', { name: '确认加入清单' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/items/5/children')).toBe(true));
    const sent = calls.find((c) => c.path === '/workbench/items/5/children')?.body as { steps: { title: string }[] };
    expect(sent.steps.map((s) => s.title)).toEqual(['列物品清单', '找搬家公司']);
  });

  it('按清单算的进度不给手填滑块', async () => {
    open('/workbench?tab=all&item=5', {
      '/users/me': ME, '/workbench/projects': [], 'GET /workbench/items': [],
      'GET /workbench/items/5': { ...item(5, '搬家', { progress: 50, progress_source: 'children', children_total: 2, children_done: 1 }),
        children: [item(6, '列清单', { parent_id: 5, status: 'done', status_name: '完成' }), item(8, '找车', { parent_id: 5 })] },
      '/workbench/items/5/logs': [],
    });
    expect(await screen.findByText('进度 50%（按清单）')).toBeTruthy();
    expect(screen.queryByLabelText('手填进度')).toBeNull();
    expect((screen.getByLabelText('完成：列清单') as HTMLInputElement).checked).toBe(true);
  });

  it('助手页：记住一件事、添加每周回顾、立即运行看到输出', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    const routine = { id: 4, name: '周五回顾', kind: 'review', freq: 'weekly', time_of_day: '18:00', weekday: 4, monthday: 1,
      run_at: null, note: '', item_id: null, enabled: true, next_run_at: '2026-10-17T10:00:00Z', last_run_at: null, last_status: '', failures: 0 };
    open('/workbench?tab=assistant', {
      '/users/me': ME, '/workbench/projects': [],
      'GET /workbench/memories': { limit: 20, items: [] }, 'POST /workbench/memories': { id: 1, content: '周末不安排工作', created_at: '' },
      'GET /workbench/routines': [routine], 'POST /workbench/routines': routine,
      'POST /workbench/routines/4/run': { status: 'ok', output: '本周完成 3 项', routine },
    }, calls);
    fireEvent.change(await screen.findByLabelText('让助手记住'), { target: { value: '周末不安排工作' } });
    fireEvent.click(screen.getByRole('button', { name: '记住' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/memories')).toBe(true));
    fireEvent.change(screen.getByLabelText('做什么'), { target: { value: 'review' } });
    fireEvent.change(screen.getByLabelText('多久一次'), { target: { value: 'weekly' } });
    fireEvent.change(screen.getByLabelText('周几'), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: '添加例行任务' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/routines')).toBe(true));
    expect(calls.find((c) => c.method === 'POST' && c.path === '/workbench/routines')?.body).toMatchObject({ kind: 'review', freq: 'weekly', weekday: 4 });
    fireEvent.click(screen.getByRole('button', { name: '现在运行一次' }));
    expect((await screen.findByTestId('wb-run-output')).textContent).toContain('本周完成 3 项');
  });
});
