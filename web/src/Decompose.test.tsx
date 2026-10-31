// AI-DEC-040~048 逐层拆解页（106 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 1, phone: '138****0000', nickname: '店主', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};
const TASK = {
  id: 9, creator_id: 1, executor_id: null, parent_id: null, depends_on: [], title: '开一家咖啡店',
  description: '', category: '活动策划', task_type: 'project', required_skills: [],
  budget_cents: 1000000, pricing: 'fixed', ip_assignment: 'assign', bonus_cents: 0,
  is_remote: true, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'draft', deadline: null, reject_count: 0, created_at: '2026-10-12T00:00:00Z',
};

function node(id: number, parent: number | null, title: string, over: Record<string, unknown> = {}) {
  return {
    id, parent, depth: parent === null ? 1 : 2, title, description: '', required_skills: [],
    budget_cents: 300000, depends_on: [], deliverable: `${title}成果`, acceptance: '发布方确认',
    single_owner: true, category: '', executor_hint: '', source: 'stub-model', fallback: false,
    leaf: true, missing: [], stop_reason: 'criteria_met', stop_note: '四条判据齐全，可以直接开工',
    expanded: false, executor_kind: 'needs_human', executor_basis: '无资质门槛的人工步骤（默认）',
    required_cert: '', task_id: null, ...over,
  };
}

const DEC = {
  id: 5, task_id: 9, items: [], status: 'proposed', source: 'anthropic:x', mode: 'tree',
  revision: 3, can_expand: true, fallback: false, model_calls: 1,
  nodes: [
    node(1, null, '开业筹备', { leaf: false, expanded: true, executor_kind: '', executor_basis: '', stop_reason: '' }),
    node(2, 1, '审租赁合同', { executor_kind: 'needs_expert', required_cert: '律师', category: '法律咨询',
      executor_basis: '类目「法律咨询」要求「律师」资质（平台类目资质表）' }),
    node(3, 1, '搞定营业执照', { executor_kind: 'unknown', executor_basis: '判断不了这一步谁能做' }),
    node(4, null, '装修', { leaf: false, missing: ['deliverable'], deliverable: '', stop_reason: 'max_depth',
      stop_note: '已到深度上限，没有继续拆。补齐交付物与验收标准，它就能作为一步发布' }),
  ],
  unresolved: [{ id: 3, title: '搞定营业执照', why: '还没说清谁来做' }, { id: 4, title: '装修', why: '还差：交付物' }],
};

type Call = { method: string; path: string; body: unknown };

function open(routes: Record<string, unknown>, calls: Call[] = [],
  errors: Record<string, { status: number; code: string; message: string }> = {}) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const key = `${method} ${path.split('?')[0]}`;
    const err = errors[key];
    if (err) return { ok: false, status: err.status, text: async () => JSON.stringify({ detail: { code: err.code, message: err.message } }) };
    const hit = routes[key] ?? routes[path.split('?')[0]];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  const client = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
  render(<MemoryRouter initialEntries={['/tasks/9/decompose']}><AppProvider client={client}><App /></AppProvider></MemoryRouter>);
  return calls;
}

const BASE = {
  '/users/me': ME, '/tasks/9': TASK, 'GET /tasks/9/decomposition': DEC,
  '/categories': [{ id: 1, name: '法律咨询', required_cert: '律师' }, { id: 2, name: '保洁', required_cert: '' }],
};

describe('AI-DEC-042/043 每一步说清谁来做、依据是什么', () => {
  it('树按层画出来；要资质的写出是什么资质与依据；判不了的明说', async () => {
    open(BASE);
    const lawyer = (await screen.findByText('审租赁合同')).closest('li')!;
    expect(within(lawyer).getByText('需要律师')).toBeTruthy();
    expect(within(lawyer).getByText(/类目资质表/)).toBeTruthy();
    const unknown = screen.getByText('搞定营业执照').closest('li')!;
    expect(within(unknown).getByText('待定：谁来做')).toBeTruthy();
    // 子步骤画在父步骤里面
    expect(screen.getByText('开业筹备').closest('li')!.contains(lawyer)).toBe(true);
  });

  it('AI-DEC-040 缺判据的步骤说出差什么；停下来的原因原样显示', async () => {
    open(BASE);
    const renov = (await screen.findByText('装修')).closest('li')!;
    expect(within(renov).getByText('还差：交付物')).toBeTruthy();
    expect(within(renov).getByText(/已到深度上限/)).toBeTruthy();
  });

  it('AI-DEC-048 模型不可用回落模板时，页面说出来', async () => {
    open({ ...BASE, 'GET /tasks/9/decomposition': { ...DEC, fallback: true } });
    expect((await screen.findByRole('alert')).textContent).toMatch(/AI 模型暂时不可用/);
  });
});

describe('AI-DEC-044 每一种判定都有去处', () => {
  it('「交给人做」是一个带 revision 的修改请求', async () => {
    const calls = open({ ...BASE, 'PATCH /decompositions/5/nodes/3': { ...DEC, revision: 4 } });
    const li = (await screen.findByText('搞定营业执照')).closest('li')!;
    fireEvent.click(within(li).getByRole('button', { name: '交给人做' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    const patch = calls.find((c) => c.method === 'PATCH')!;
    expect(patch.path).toBe('/decompositions/5/nodes/3');
    expect(patch.body).toEqual({ revision: 3, executor_hint: 'human' });
  });

  it('「需要持证专家」从要资质的类目里选', async () => {
    const calls = open({ ...BASE, 'PATCH /decompositions/5/nodes/3': DEC });
    fireEvent.change(await screen.findByLabelText('「搞定营业执照」需要的资质类目'), { target: { value: '法律咨询' } });
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body)
      .toEqual({ revision: 3, category: '法律咨询' }));
    // 不要资质的类目不在选项里
    expect(screen.queryByRole('option', { name: /保洁/ })).toBeNull();
  });

  it('还有没说清的步骤时不能确认；全部说清后能确认', async () => {
    open(BASE);
    const confirm = await screen.findByRole('button', { name: '确认并发布可开工的步骤' });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/还有 2 步没说清/)).toBeTruthy();
  });

  it('全部说清后确认，回到任务页', async () => {
    const ready = { ...DEC, unresolved: [], nodes: DEC.nodes.slice(0, 2) };
    const calls = open({ ...BASE, 'GET /tasks/9/decomposition': ready,
      'POST /decompositions/5/confirm': { decomposition: { ...ready, status: 'confirmed' }, children: [] } });
    fireEvent.click(await screen.findByRole('button', { name: '确认并发布可开工的步骤' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/decompositions/5/confirm')).toBe(true));
  });
});

describe('AI-DEC-041 一层一层拆', () => {
  it('「继续拆下一层」只带 revision；「拆这一步」带上那一步', async () => {
    const calls = open({ ...BASE, 'POST /decompositions/5/expand': { ...DEC, revision: 4, report: { expanded: [], stopped: [], blocked: [] } } });
    fireEvent.click(await screen.findByRole('button', { name: '继续拆下一层' }));
    await waitFor(() => expect(calls.filter((c) => c.path === '/decompositions/5/expand')).toHaveLength(1));
    expect(calls.find((c) => c.path === '/decompositions/5/expand')!.body).toEqual({ revision: 3 });

    const renov = screen.getByText('装修').closest('li')!;
    fireEvent.click(within(renov).getByRole('button', { name: '拆这一步' }));
    await waitFor(() => expect(calls.filter((c) => c.path === '/decompositions/5/expand')).toHaveLength(2));
    expect(calls.filter((c) => c.path === '/decompositions/5/expand')[1].body).toEqual({ revision: 4, node_ids: [4] });
  });

  it('别的窗口改过：显示服务端的话并重新读最新的那份', async () => {
    const calls = open(BASE, [], {
      'PATCH /decompositions/5/nodes/3': { status: 409, code: 'decomposition_changed', message: '这份拆解刚被另一个窗口改过，请刷新后再改' },
    });
    const li = (await screen.findByText('搞定营业执照')).closest('li')!;
    fireEvent.click(within(li).getByRole('button', { name: '交给人做' }));
    await waitFor(() => expect(screen.getByText(/另一个窗口改过/)).toBeTruthy());
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET' && c.path === '/tasks/9/decomposition').length).toBeGreaterThanOrEqual(2));
  });

  it('还没拆过的草稿项目：进页面就开始拆', async () => {
    const calls = open({ ...BASE, '/tasks/9/tree': { parent_id: 9, parent_status: 'draft', progress_pct: 0, all_children_completed: false, children: [] },
      'POST /tasks/9/decompositions': DEC }, [], {
      'GET /tasks/9/decomposition': { status: 404, code: 'no_decomposition_in_progress', message: '这个任务没有进行中的拆解' },
    });
    await screen.findByText('审租赁合同');
    expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/9/decompositions')).toBe(true);
  });
});
