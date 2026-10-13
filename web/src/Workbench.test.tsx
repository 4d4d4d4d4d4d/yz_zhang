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

describe('IM-060 消息列表写出在和谁聊', () => {
  it('私聊显示对方昵称、任务会话显示任务标题，不再是「私聊 #2」', async () => {
    open('/messages', {
      '/users/me': ME,
      '/conversations': [
        { id: 2, kind: 'direct', task_id: null, participants: [2, 5], title: '陈设计', unread_count: 0, last_message: null },
        { id: 1, kind: 'task', task_id: 9, participants: [2, 3], title: '任务：三居室保洁', unread_count: 0, last_message: null },
      ],
    });
    expect(await screen.findByText(/陈设计/)).toBeTruthy();
    expect(screen.getByText(/任务：三居室保洁/)).toBeTruthy();
    expect(screen.queryByText(/私聊 #2/)).toBeNull();
  });
});

describe('TASK-090 发布页不替人选类目与城市', () => {
  it('没带参数时类目与城市都是「请选择」；没选就提交会说清楚，不发请求', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    open('/publish', { '/users/me': ME, '/categories': [{ name: '保洁', required_cert: '' }, { name: '设计', required_cert: '' }],
      '/cities': [{ id: 1, name: '上海' }, { id: 2, name: '杭州' }] }, calls);
    const category = await screen.findByDisplayValue('请选择类目');
    expect((category as HTMLSelectElement).value).toBe('');
    fireEvent.change(screen.getByLabelText(/^标题/), { target: { value: '咖啡店品牌升级' } });
    fireEvent.submit(category.closest('form')!);
    await waitFor(() => expect(document.querySelector('.error')?.textContent).toBe('请选择类目'));
    expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(false);
  });

  it('资料里填了开通城市的，默认用它；从工作台带着标题过来的照用', async () => {
    open('/publish?title=%E6%95%B4%E7%90%86%E5%8F%91%E7%A5%A8&category=%E8%AE%BE%E8%AE%A1', {
      '/users/me': { ...ME, city: '杭州' }, '/categories': [{ name: '保洁', required_cert: '' }, { name: '设计', required_cert: '' }],
      '/cities': [{ id: 1, name: '上海' }, { id: 2, name: '杭州' }] });
    expect(await screen.findByDisplayValue('整理发票')).toBeTruthy();
    expect(await screen.findByDisplayValue('杭州')).toBeTruthy();
    expect(screen.getByDisplayValue('设计')).toBeTruthy();
  });
});

describe('SPACE-029 个人空间显示履约记录', () => {
  it('完成单数、平均星级、常见标签与最近评价都在；没有记录时如实说', async () => {
    const space = { user_id: 5, nickname: '周师傅', headline: '保洁八年', introduction: '', theme: 'clay', kind: 'person',
      items: [], items_count: 0, accepting_orders: true,
      track_record: { tasks_completed: 3, rating_avg: 4.7, reviews_total: 2, top_tags: ['细致', '准时'],
        recent_reviews: [{ stars: 5, tags: ['细致'], comment: '厨房很干净', created_at: '2026-10-12T00:00:00Z' }] } };
    open('/people/5', { '/users/me': ME, '/spaces/5': space, '/users/5/follow-stats': { followers: 0, following: 0, viewer_following: false } });
    const section = await screen.findByLabelText('履约记录');
    expect(section.textContent).toContain('完成 3 单');
    expect(section.textContent).toContain('4.7');
    expect(section.textContent).toContain('#细致');
    expect(section.textContent).toContain('厨房很干净');
  });
});
