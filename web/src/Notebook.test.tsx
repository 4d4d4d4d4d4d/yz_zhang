// KB-100 个人知识库（122 号 spec）：随手记、抽待办、问笔记、蒸馏方法、工作台引用。
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
const SUMMARY = { total: 2, inbox: 1, archived: 0, methods: 0, limit: 5000, tags: [{ tag: '财税', count: 1 }] };
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
type Call = { method: string; path: string; body?: unknown };

function open(path: string, routes: Record<string, unknown>, calls: Call[] = []) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: `${p}${String(url).includes('?') ? `?${String(url).split('?')[1]}` : ''}`, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

describe('KB-100 个人知识库', () => {
  it('导航里多了「知识库」，原有的导航项一个不少', async () => {
    open('/', { '/users/me': ME, '/spaces': { items: [], next_cursor: null } });
    const nav = await screen.findByRole('navigation', { name: '工作台导航' });
    for (const label of ['发现', '合作', '工作台', '知识库', '消息', '我的空间']) expect(nav.textContent).toContain(label);
  });

  it('随手记：正文与标签一起发出去，收件箱显示条数', async () => {
    const calls: Call[] = [];
    open('/notebook', { '/users/me': ME, '/notebook/summary': SUMMARY, 'GET /notebook/notes': [brief(1, '开票规则', { tags: ['财税'] })],
      'POST /notebook/notes': brief(3, '新想法') }, calls);
    expect(await screen.findByText('开票规则')).toBeTruthy();
    expect(screen.getByRole('tab', { name: '收件箱（1）' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('随手记'), { target: { value: '客户更在意交付时间' } });
    fireEvent.change(screen.getByLabelText('标签'), { target: { value: '客户 想法' } });
    fireEvent.click(screen.getByRole('button', { name: '记下' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/notebook/notes')).toBe(true));
    expect(calls.find((c) => c.method === 'POST' && c.path === '/notebook/notes')?.body).toMatchObject({ body: '客户更在意交付时间', tags: ['客户', '想法'] });
    expect(calls.some((c) => c.path.startsWith('/notebook/notes?') && c.path.includes('status=inbox'))).toBe(true);
  });

  it('抽出待办：先给草稿，去掉一项后才放进工作台', async () => {
    const calls: Call[] = [];
    open('/notebook?tab=all&note=4', {
      '/users/me': ME, '/notebook/summary': SUMMARY, 'GET /notebook/notes': [],
      'GET /notebook/notes/4': { ...brief(4, '周会纪要', { kind: 'minutes' }), body: '- [ ] 提交报价单\n待办：联系财务' },
      'POST /notebook/notes/4/extract-todos': { note_id: 4, items: [
        { title: '提交报价单', due_at: '2026-10-16T10:00:00Z', line: '- [ ] 提交报价单' },
        { title: '联系财务', due_at: null, line: '待办：联系财务' }] },
      'POST /notebook/notes/4/todos': [wbItem(9, '提交报价单')],
    }, calls);
    fireEvent.click(await screen.findByRole('button', { name: '抽出待办' }));
    expect(await screen.findByText(/提交报价单/)).toBeTruthy();
    expect(calls.some((c) => c.path === '/notebook/notes/4/todos')).toBe(false);     // 只是草稿
    fireEvent.click(screen.getByLabelText('保留：联系财务'));
    fireEvent.click(screen.getByRole('button', { name: '放进工作台' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/notebook/notes/4/todos')).toBe(true));
    const sent = calls.find((c) => c.path === '/notebook/notes/4/todos')?.body as { items: { title: string; due_at: string | null }[] };
    expect(sent.items).toEqual([{ title: '提交报价单', due_at: '2026-10-16T10:00:00Z' }]);
    expect((await screen.findByRole('status')).textContent).toContain('已放进工作台 1 项');
  });

  it('问问我的笔记：只摘录、带出处', async () => {
    open('/notebook?tab=ask', { '/users/me': ME, '/notebook/summary': SUMMARY,
      'POST /notebook/ask': { mode: 'extractive', answer: '…', citations: [{ n: 1, note_id: 1, title: '开票规则', snippet: '要税号和开户行' }] } });
    fireEvent.change(await screen.findByLabelText('问我的笔记'), { target: { value: '专票要什么' } });
    fireEvent.click(screen.getByRole('button', { name: '问' }));
    expect(await screen.findByRole('button', { name: '开票规则' })).toBeTruthy();
    expect(screen.getByText(/要税号和开户行/)).toBeTruthy();
  });

  it('勾选笔记蒸馏成方法：草稿可删步，确认后才保存', async () => {
    const calls: Call[] = [];
    open('/notebook?tab=all', { '/users/me': ME, '/notebook/summary': SUMMARY,
      'GET /notebook/notes': [brief(1, '报税流程'), brief(2, '报税补充')],
      'POST /notebook/methods/distill': { name: '报税流程', found: 'numbered', source_note_ids: [1, 2],
        steps: [{ title: '核对收入', note: '' }, { title: '整理发票', note: '' }, { title: '申报', note: '' }] },
      'POST /notebook/methods': { id: 1, name: '报税流程', description: '', steps: [], source_note_ids: [1, 2], uses: 0, created_at: '', updated_at: '' },
      'GET /notebook/methods': [] }, calls);
    fireEvent.click(await screen.findByLabelText('选中：报税流程'));
    fireEvent.click(screen.getByLabelText('选中：报税补充'));
    fireEvent.click(screen.getByRole('button', { name: '把选中的 2 条蒸馏成方法' }));
    expect(await screen.findByText('核对收入')).toBeTruthy();
    expect(calls.find((c) => c.path === '/notebook/methods/distill')?.body).toEqual({ note_ids: [1, 2] });
    fireEvent.click(screen.getByRole('button', { name: '去掉：整理发票' }));
    fireEvent.click(screen.getByRole('button', { name: '保存为我的方法' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/notebook/methods')).toBe(true));
    const sent = calls.find((c) => c.method === 'POST' && c.path === '/notebook/methods')?.body as { steps: { title: string }[] };
    expect(sent.steps.map((s) => s.title)).toEqual(['核对收入', '申报']);
  });

  it('我的方法：可以改名', async () => {
    const calls: Call[] = [];
    const m = { id: 7, name: '报税流程', description: '', steps: [{ title: '核对收入', note: '' }], source_note_ids: [], uses: 2, created_at: '', updated_at: '' };
    open('/notebook?tab=methods', { '/users/me': ME, '/notebook/summary': SUMMARY, 'GET /notebook/methods': [m], 'PATCH /notebook/methods/7': m }, calls);
    const input = await screen.findByLabelText('方法名：报税流程');
    expect(screen.getByText('用过 2 次')).toBeTruthy();
    fireEvent.change(input, { target: { value: '月度报税流程' } });
    fireEvent.blur(input);
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ name: '月度报税流程' }));
  });

  it('AGT-095 我的方法写明编排用得怎么样；做完的少就不给成功率', async () => {
    const base = { description: '', steps: [{ title: '打包', note: '' }], source_note_ids: [], uses: 3, created_at: '', updated_at: '' };
    const rows = [
      { ...base, id: 7, name: '搬家做法', missions_total: 4, missions_succeeded: 3, missions_failed: 1, missions_spent_cents: 36000, success_rate: 0.75 },
      { ...base, id: 8, name: '报税流程', missions_total: 1, missions_succeeded: 1, missions_failed: 0, missions_spent_cents: 5000, success_rate: null },
      { ...base, id: 9, name: '没用过的', missions_total: 0, missions_succeeded: 0, missions_failed: 0, missions_spent_cents: 0, success_rate: null },
    ];
    open('/notebook?tab=methods', { '/users/me': ME, '/notebook/summary': SUMMARY, 'GET /notebook/methods': rows });
    expect((await screen.findByTestId('method-stats-7')).textContent).toBe('编排用过 4 次：做成 3、没成 1，花了 ¥360.00；成功率 75%');
    expect(screen.getByTestId('method-stats-8').textContent).toContain('做完的还少，先不算成功率');
    expect(screen.queryByTestId('method-stats-9')).toBeNull();
  });

  it('AGT-097 改过步骤的方法按版本分开看效果；只用过一版的不分', async () => {
    const base = { description: '', steps: [{ title: '打包', note: '' }], source_note_ids: [], uses: 3, created_at: '', updated_at: '' };
    const ver = (version: number, total: number, ok: number, bad: number, rate: number | null) =>
      ({ version, missions_total: total, missions_succeeded: ok, missions_failed: bad, missions_spent_cents: 0, success_rate: rate });
    const rows = [
      { ...base, id: 7, name: '搬家做法', missions_total: 7, missions_succeeded: 4, missions_failed: 3, missions_spent_cents: 0, success_rate: 0.57,
        version: 2, versions: [ver(2, 4, 3, 1, 0.75), ver(1, 3, 1, 2, 0.33)] },
      { ...base, id: 8, name: '报税流程', missions_total: 3, missions_succeeded: 2, missions_failed: 1, missions_spent_cents: 0, success_rate: 0.67,
        version: 1, versions: [ver(1, 3, 2, 1, 0.67)] },
    ];
    open('/notebook?tab=methods', { '/users/me': ME, '/notebook/summary': SUMMARY, 'GET /notebook/methods': rows });
    const box = await screen.findByTestId('method-versions-7');
    expect(box.textContent).toContain('第 1 版成功率 33% → 第 2 版 75%：改了之后变好了');
    expect(box.textContent).toContain('第 2 版：用过 4 次，做成 3、没成 1');
    expect(box.textContent).toContain('第 1 版：用过 3 次，做成 1、没成 2');
    expect(screen.queryByTestId('method-versions-8')).toBeNull();
  });

  it('工作台任务里：相关笔记摆在眼前，能套用我的方法', async () => {
    const calls: Call[] = [];
    open('/workbench?tab=all&item=5', {
      '/users/me': ME, '/workbench/projects': [], 'GET /workbench/items': [],
      'GET /workbench/items/5': { ...wbItem(5, '十月报税'), children: [] }, '/workbench/items/5/logs': [],
      '/notebook/related': [{ note_id: 1, title: '报税材料清单', snippet: '银行流水、发票', score: 9 }],
      'GET /notebook/methods': [{ id: 7, name: '报税流程', description: '', steps: [{ title: '核对收入', note: '' }], source_note_ids: [], uses: 0, created_at: '', updated_at: '' }],
      'POST /notebook/methods/7/apply': { ...wbItem(5, '十月报税'), children: [] },
    }, calls);
    expect((await screen.findByRole('link', { name: '报税材料清单' })).getAttribute('href')).toBe('/notebook?tab=all&note=1');
    fireEvent.change(await screen.findByLabelText('套用我的方法'), { target: { value: '7' } });
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/notebook/methods/7/apply')).toBe(true));
    expect(calls.find((c) => c.path === '/notebook/methods/7/apply')?.body).toEqual({ item_id: 5 });
  });
});
