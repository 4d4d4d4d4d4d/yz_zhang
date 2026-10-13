// KB-100 个人知识库在 App 上的行为（122 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { NotebookScreen } from './notebook';
import { WorkbenchScreen } from './workbench';

type Call = { method: string; path: string; body?: unknown };
const brief = (id: number, title: string, extra: Record<string, unknown> = {}) => ({
  id, kind: 'note', title, url: '', status: 'inbox', tags: [], pinned: false, project_id: null, revision: 0,
  excerpt: '', created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z', ...extra,
});
const wbItem = (id: number, title: string) => ({
  id, project_id: null, parent_id: null, title, notes: '', status: 'todo', status_name: '待办', priority: 1,
  category: '', due_at: null, remind_at: null, progress: 0, progress_source: 'manual', children_total: 0,
  children_done: 0, tags: [], linked_task: null, revision: 0, created_at: '2026-10-13T00:00:00Z',
  updated_at: '2026-10-13T00:00:00Z', completed_at: null,
});
const SUMMARY = { total: 1, inbox: 1, archived: 0, methods: 0, limit: 5000, tags: [] };

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

describe('KB-100 App 上的个人知识库', () => {
  it('随手记一句；点开纪要抽出待办，去掉一项后放进工作台', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/notebook/summary': SUMMARY, 'GET /notebook/notes': [brief(4, '周会纪要', { kind: 'minutes' })],
      'POST /notebook/notes': brief(5, '新想法'),
      'GET /notebook/notes/4': { ...brief(4, '周会纪要', { kind: 'minutes' }), body: '- [ ] 提交报价单\n待办：联系财务' },
      'POST /notebook/notes/4/extract-todos': { note_id: 4, items: [
        { title: '提交报价单', due_at: null, line: '' }, { title: '联系财务', due_at: null, line: '' }] },
      'POST /notebook/notes/4/todos': [wbItem(9, '提交报价单')],
    }, calls);
    render(<NotebookScreen client={client} />);
    expect(await screen.findByText('收件箱（1）')).toBeTruthy();
    fireEvent.changeText(screen.getByPlaceholderText('一句话、一段纪要，或者粘贴一个链接'), '客户更在意交付时间');
    fireEvent.press(screen.getByText('记下'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/notebook/notes')?.body).toEqual({ body: '客户更在意交付时间' }));
    fireEvent.press(await screen.findByText('周会纪要'));
    fireEvent.press(await screen.findByText('抽出待办'));
    fireEvent.press(await screen.findByText('☑ 联系财务'));
    expect(calls.some((c) => c.path === '/notebook/notes/4/todos')).toBe(false);
    fireEvent.press(screen.getByText('放进工作台'));
    await waitFor(() => expect(calls.find((c) => c.path === '/notebook/notes/4/todos')?.body).toEqual({ items: [{ title: '提交报价单', due_at: null }] }));
    expect(await screen.findByText('已放进工作台 1 项')).toBeTruthy();
  });

  it('选中两条笔记蒸馏成方法：草稿可删步，确认后才保存', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/notebook/summary': SUMMARY, 'GET /notebook/notes': [brief(1, '报税流程'), brief(2, '报税补充')],
      'POST /notebook/methods/distill': { name: '报税流程', found: 'numbered', source_note_ids: [1, 2],
        steps: [{ title: '核对收入', note: '' }, { title: '整理发票', note: '' }] },
      'POST /notebook/methods': { id: 1, name: '报税流程', description: '', steps: [], source_note_ids: [1, 2], uses: 0, created_at: '', updated_at: '' },
    }, calls);
    render(<NotebookScreen client={client} />);
    await screen.findByText('报税流程');
    fireEvent.press(screen.getAllByText('☐ 选中')[0]);
    fireEvent.press(screen.getAllByText('☐ 选中')[0]);
    fireEvent.press(screen.getByText('把选中的 2 条蒸馏成方法'));
    expect(await screen.findByText('2. 整理发票')).toBeTruthy();
    expect(calls.find((c) => c.path === '/notebook/methods/distill')?.body).toEqual({ note_ids: [1, 2] });
    fireEvent.press(screen.getAllByText('去掉')[1]);
    fireEvent.press(screen.getByText('保存为我的方法'));
    await waitFor(() => expect((calls.find((c) => c.method === 'POST' && c.path === '/notebook/methods')?.body as { steps: unknown[] }).steps).toEqual([{ title: '核对收入', note: '' }]));
  });

  it('笔记可以删除（知识库满了的补救）', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/notebook/summary': SUMMARY, 'GET /notebook/notes': [brief(4, '旧笔记')],
      'GET /notebook/notes/4': { ...brief(4, '旧笔记'), body: '不要了' }, 'DELETE /notebook/notes/4': { deleted: true } }, calls);
    render(<NotebookScreen client={client} />);
    fireEvent.press(await screen.findByText('旧笔记'));
    fireEvent.press(await screen.findByText('删除'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/notebook/notes/4')).toBe(true));
    expect(await screen.findByText('收件箱（1）')).toBeTruthy();     // 删完回到列表
  });

  it('问笔记：带出处', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/notebook/summary': SUMMARY,
      'POST /notebook/ask': { mode: 'extractive', answer: '', citations: [{ n: 1, note_id: 1, title: '开票规则', snippet: '要税号和开户行' }] } }, calls);
    render(<NotebookScreen client={client} />);
    fireEvent.press(await screen.findByText('问笔记'));
    fireEvent.changeText(screen.getByPlaceholderText('比如：给企业开专票要什么？'), '专票要什么');
    fireEvent.press(screen.getByText('问'));
    expect(await screen.findByText('[1] 开票规则')).toBeTruthy();
    expect(calls.find((c) => c.path === '/notebook/ask')?.body).toEqual({ q: '专票要什么' });
  });

  it('工作台任务里：相关笔记与套用我的方法', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      '/workbench/overview': { counts: { overdue: 0, today: 1, doing: 0, blocked: 0, stale: 0, done_this_week: 0, open: 1 },
        overdue: [], today: [wbItem(5, '十月报税')], doing: [], blocked: [], stale: [], done_this_week: [], projects: [],
        platform: { to_choose: [], to_accept: [], executing: [] }, summary: '' },
      'GET /workbench/items/5': { ...wbItem(5, '十月报税'), children: [] }, '/workbench/items/5/logs': [],
      '/notebook/related': [{ note_id: 1, title: '报税材料清单', snippet: '银行流水、发票', score: 9 }],
      'GET /notebook/methods': [{ id: 7, name: '报税流程', description: '', steps: [{ title: '核对收入', note: '' }], source_note_ids: [], uses: 0, created_at: '', updated_at: '' }],
      'POST /notebook/methods/7/apply': { ...wbItem(5, '十月报税'), children: [] },
    }, calls);
    render(<WorkbenchScreen client={client} />);
    fireEvent.press(await screen.findByText('十月报税'));
    expect(await screen.findByText('· 报税材料清单：银行流水、发票')).toBeTruthy();
    fireEvent.press(await screen.findByText('套用我的方法：报税流程（1 步）'));
    await waitFor(() => expect(calls.find((c) => c.path === '/notebook/methods/7/apply')?.body).toEqual({ item_id: 5 }));
  });
});
