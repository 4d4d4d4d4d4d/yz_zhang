// PWB 个人工作台在 App 上的行为（116 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { WorkbenchScreen } from './workbench';

const item = (id: number, title: string, extra: Record<string, unknown> = {}) => ({
  id, project_id: null, parent_id: null, title, notes: '', status: 'todo', status_name: '待办', priority: 1,
  category: '', due_at: null, remind_at: null, progress: 0, progress_source: 'manual', children_total: 0,
  children_done: 0, tags: [], linked_task: null, revision: 0, created_at: '2026-10-13T00:00:00Z',
  updated_at: '2026-10-13T00:00:00Z', completed_at: null, ...extra,
});

function makeClient(routes: Record<string, unknown>, calls: Array<{ method: string; path: string; body?: unknown }>) {
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
  counts: { overdue: 0, today: 1, doing: 0, blocked: 0, stale: 0, done_this_week: 0, open: 1 },
  overdue: [], today: [item(5, '搬家')], doing: [], blocked: [], stale: [], done_this_week: [], projects: [],
  platform: { to_choose: [], to_accept: [{ task_id: 9, title: '三居室保洁' }], executing: [] },
  summary: '今天到期 1 项：「搬家」；已逾期 0 项；进行中 0 项；卡住 0 项。平台上：1 单等你验收。',
};

describe('PWB App 上的个人工作台', () => {
  it('今天：概览、平台上等我验收的单；点开任务让助手拆一下并确认', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    const client = makeClient({
      '/workbench/overview': OVERVIEW,
      'GET /workbench/items/5': { ...item(5, '搬家'), children: [] }, '/workbench/items/5/logs': [],
      'POST /workbench/items/5/breakdown': { source: 'generic', steps: [{ title: '列物品清单', note: '' }, { title: '退押金', note: '' }] },
      'POST /workbench/items/5/children': { ...item(5, '搬家'), children: [] },
    }, calls);
    render(<WorkbenchScreen client={client} />);
    expect(await screen.findByText(/平台上：1 单等你验收/)).toBeTruthy();
    expect(screen.getByText('平台：「三居室保洁」等你验收')).toBeTruthy();
    fireEvent.press(screen.getByText('搬家'));
    fireEvent.press(await screen.findByText('让助手拆一下'));
    expect(await screen.findByText('列物品清单')).toBeTruthy();
    expect(calls.some((c) => c.path === '/workbench/items/5/children')).toBe(false);
    fireEvent.press(screen.getAllByText('去掉')[1]);
    fireEvent.press(screen.getByText('确认加入清单'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/items/5/children')).toBe(true));
    const sent = calls.find((c) => c.path === '/workbench/items/5/children')?.body as { steps: { title: string }[] };
    expect(sent.steps.map((x) => x.title)).toEqual(['列物品清单']);
  });

  it('勾掉清单项、记一笔进展', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    const client = makeClient({
      '/workbench/overview': { ...OVERVIEW, platform: { to_choose: [], to_accept: [], executing: [] } },
      'GET /workbench/items/5': { ...item(5, '搬家', { progress: 0, progress_source: 'children', children_total: 1 }),
        children: [item(6, '找车', { parent_id: 5 })] },
      '/workbench/items/5/logs': [], 'PATCH /workbench/items/6': item(6, '找车', { status: 'done' }),
      'POST /workbench/items/5/logs': { id: 1, kind: 'note', body: '车定好了', created_at: '' },
    }, calls);
    render(<WorkbenchScreen client={client} />);
    fireEvent.press(await screen.findByText('搬家'));
    expect(await screen.findByText(/进度 0%（按清单）/)).toBeTruthy();
    expect(screen.queryByText('进度 50%')).toBeNull();     // 按清单算的不给手填
    fireEvent.press(screen.getByText('☐ 找车'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.path === '/workbench/items/6')?.body).toEqual({ status: 'done' }));
    fireEvent.changeText(screen.getByPlaceholderText('今天做到哪了？'), '车定好了');
    fireEvent.press(screen.getByText('记一笔'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/workbench/items/5/logs')).toBe(true));
  });

  it('助手：记住一件事、一键加每天早上的概览', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    const client = makeClient({
      '/workbench/overview': OVERVIEW, 'GET /workbench/memories': { limit: 20, items: [] }, 'GET /workbench/routines': [],
    }, calls);
    render(<WorkbenchScreen client={client} />);
    fireEvent.press(await screen.findByText('助手'));
    fireEvent.changeText(await screen.findByPlaceholderText('让助手记住一件事'), '周末不安排工作');
    fireEvent.press(screen.getByText('记住'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/workbench/memories')?.body).toEqual({ content: '周末不安排工作' }));
    fireEvent.press(screen.getByText('每天早上的概览'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/workbench/routines')?.body)
      .toMatchObject({ kind: 'digest', freq: 'daily', time_of_day: '08:30' }));
  });
});
