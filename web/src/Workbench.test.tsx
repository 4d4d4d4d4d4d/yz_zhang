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

describe('SPACE-023 资料页设置可用时段与少量接单', () => {
  it('勾周六、改结束时间、勾少量接单，保存时发出时段（原有的服务设置不受影响）', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    open('/profile', { '/users/me': { ...ME, weekly_slots: [], limited_capacity: false }, 'PATCH /users/me': ME,
      '/users/me/certifications': { active: [], applications: [] }, '/finance/my-tax': { mode: 'labor', yearly: [], items: [], disclaimer: '' },
      '/legal/agreements': { current_version: 'v1', documents: [], sensitive_scopes: [], rights: {} },
      '/wallet/payout-account': { kind: '', account_no: '', holder_name: '', bound: false } }, calls);
    const sat = await screen.findByLabelText('周六有空');
    fireEvent.click(sat);
    fireEvent.change(screen.getByLabelText('周六结束'), { target: { value: '12:00' } });
    fireEvent.click(screen.getByLabelText(/这阵子少量接单/));
    fireEvent.click(screen.getByRole('button', { name: '保存可用时间' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.path === '/users/me')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      weekly_slots: [{ d: 5, from: '09:00', to: '12:00' }], limited_capacity: true });
    expect(screen.getByText('服务设置与隐私')).toBeTruthy();
  });
});

describe('IM-009 消息里的报价卡', () => {
  it('发布方报的价：对方看到卡片并能按这个价报名；执行方报的价：发布方看到去选 TA', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    const q = (id: number, sender: number, fromCreator: boolean) => ({ id, sender_id: sender, kind: 'quote', risk_flagged: false, recalled: false,
      created_at: '2026-10-13T00:00:00Z', content: JSON.stringify({ task_id: 9, price_cents: 21000, note: '周六上午', title: '三居室保洁', from_creator: fromCreator }) });
    open('/messages?conversation=2', {
      '/users/me': ME,
      '/conversations': [{ id: 2, kind: 'direct', task_id: null, participants: [2, 5], title: '陈设计', unread_count: 0, last_message: null }],
      '/conversations/2/messages': [q(1, 5, true), q(2, 5, false)],
      'POST /tasks/9/applications': { id: 1, status: 'pending' },
    }, calls);
    const cards = await screen.findAllByTestId('quote-card');
    expect(cards[0].textContent).toContain('¥210.00');
    expect(cards[0].textContent).toContain('《三居室保洁》');
    expect(cards[1].textContent).toContain('去任务页的报名列表里选 TA');
    fireEvent.click(screen.getByRole('button', { name: '按这个价报名' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/9/applications')?.body)
      .toEqual({ message: '周六上午', bid_cents: 21000 }));
  });

  it('在私聊里从我发布的招募中任务里选一单发报价', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    open('/messages?conversation=2', {
      '/users/me': ME,
      '/conversations': [{ id: 2, kind: 'direct', task_id: null, participants: [2, 5], title: '陈设计', unread_count: 0, last_message: null }],
      '/conversations/2/messages': [], '/tasks/mine': [{ id: 9, title: '三居室保洁' }],
      'POST /conversations/2/quote-cards': { id: 3, kind: 'quote' },
    }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '发报价' }));
    fireEvent.change(await screen.findByLabelText('报哪一单'), { target: { value: '9' } });
    fireEvent.change(screen.getByLabelText('报价（元）'), { target: { value: '210' } });
    fireEvent.click(screen.getByRole('button', { name: '发出报价卡' }));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/conversations/2/quote-cards')?.body)
      .toEqual({ task_id: 9, price_cents: 21000, note: '' }));
  });
});

describe('SPACE-024 合作驾驶舱', () => {
  const PARENT = { id: 20, title: '公司官网', description: '', category: '软件开发', status: 'draft', budget_cents: 800000,
    creator_id: 2, executor_id: null, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null,
    task_type: 'project', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none' };
  const node = (id: number, title: string, extra: Record<string, unknown> = {}) => ({ id, parent_id: 20, title, status: 'published',
    status_name: '招募中', budget_cents: 200000, is_container: false, depends_on: [], blocked_by: [], executor_id: null,
    executor_nickname: null, deadline: null, overdue: false, on_critical_path: false, in_dispute: false, ...extra });
  const COCKPIT = { task_id: 20, title: '公司官网', status: 'draft', progress_pct: 0, steps_total: 2, steps_done: 0,
    budget: { planned_cents: 800000, allocated_cents: 400000, committed_cents: 200000, paid_cents: 0, remaining_cents: 600000 },
    critical_path: [21, 22],
    alerts: [{ task_id: 21, kind: 'overdue', text: '「需求梳理」已过截止时间（进行中）：催办、改期或发起纠纷' }],
    nodes: [node(21, '需求梳理', { status: 'in_progress', status_name: '进行中', executor_id: 5, executor_nickname: '陈设计', overdue: true,
      deadline: '2026-10-12T00:00:00Z', on_critical_path: true }),
      node(22, '页面开发', { depends_on: [21], blocked_by: [21], on_critical_path: true })] };

  it('发布方看到钱、预警、关键路径和每一步卡在哪', async () => {
    open('/tasks/20', { '/users/me': ME, '/tasks/20': PARENT, '/tasks/20/cockpit': COCKPIT,
      '/tasks/20/tree': { parent_id: 20, parent_status: 'draft', progress_pct: 0, children: [{ id: 21, title: '需求梳理', status: 'in_progress', budget_cents: 200000, depends_on: [], executor_id: 5 }], all_children_completed: false } });
    const panel = await screen.findByLabelText('合作驾驶舱');
    expect(panel.textContent).toContain('已托管 ¥2000.00');
    expect(panel.textContent).toContain('还剩 ¥6000.00');
    expect(panel.textContent).toContain('已过截止时间');
    expect(panel.textContent).toContain('需求梳理 → 页面开发');
    const row = screen.getByText('★ 页面开发').closest('tr')!;
    expect(row.textContent).toContain('需求梳理');            // 卡在「需求梳理」
    expect(screen.getByText('陈设计')).toBeTruthy();
  });

  it('不是发布方：不请求驾驶舱', async () => {
    const calls: Array<{ method: string; path: string }> = [];
    open('/tasks/20', { '/users/me': { ...ME, id: 9 }, '/tasks/20': PARENT,
      '/tasks/20/tree': { parent_id: 20, parent_status: 'draft', progress_pct: 0, children: [{ id: 21, title: '需求梳理', status: 'in_progress', budget_cents: 200000, depends_on: [], executor_id: 5 }], all_children_completed: false } }, calls);
    await screen.findByText(/子任务进度/);
    expect(calls.some((c) => c.path === '/tasks/20/cockpit')).toBe(false);
  });
});
