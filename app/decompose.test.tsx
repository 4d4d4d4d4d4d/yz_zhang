// APP-077 App 上的逐层拆解（107 号 spec）。
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { PublishScreen, TaskDetailScreen } from './App';
import { CockpitBlock, DecomposeScreen } from './decompose';

type Call = { method: string; path: string; body: unknown };

function makeClient(routes: Record<string, unknown>, calls: Call[] = [],
  errors: Record<string, { status: number; code: string; message: string }> = {}): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const key = `${method} ${path.split('?')[0]}`;
    const err = errors[key];
    if (err) return { ok: false, status: err.status, text: async () => JSON.stringify({ detail: { code: err.code, message: err.message } }) };
    const hit = routes[key] ?? routes[path.split('?')[0]];
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const TASK: Task = {
  id: 9, creator_id: 1, executor_id: null, parent_id: null, depends_on: [], title: '开一家咖啡店',
  description: '', category: '活动策划', task_type: 'project', required_skills: [],
  budget_cents: 1000000, pricing: 'fixed', ip_assignment: 'assign', bonus_cents: 0,
  is_remote: true, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'draft', deadline: null, reject_count: 0, created_at: '2026-10-12T00:00:00Z',
} as unknown as Task;

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
  ],
  unresolved: [{ id: 3, title: '搞定营业执照', why: '还没说清谁来做' }],
};
const BASE = {
  'GET /tasks/9/decomposition': DEC,
  '/categories': [{ id: 1, name: '法律咨询', required_cert: '律师' }, { id: 2, name: '保洁', required_cert: '' }],
};

describe('APP-077 App 上的逐层拆解', () => {
  it('每一步写出谁来做与依据；子步骤画在父步骤里', async () => {
    render(<DecomposeScreen client={makeClient(BASE)} task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    const lawyer = await screen.findByTestId('node-2');
    expect(within(lawyer).getByText('需要律师')).toBeTruthy();
    expect(within(lawyer).getByText(/类目资质表/)).toBeTruthy();
    expect(within(screen.getByTestId('node-1')).getByTestId('node-2')).toBeTruthy();
    expect(within(screen.getByTestId('node-3')).getByText('待定：谁来做')).toBeTruthy();
  });

  it('「交给人做」与「需要律师」都是真的修改请求；不要资质的类目不在选项里', async () => {
    const calls: Call[] = [];
    render(<DecomposeScreen client={makeClient({ ...BASE, 'PATCH /decompositions/5/nodes/3': DEC }, calls)}
                            task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    const unknown = await screen.findByTestId('node-3');
    fireEvent.press(within(unknown).getByText('交给人做'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(1));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ revision: 3, executor_hint: 'human' });
    fireEvent.press(within(unknown).getByText('需要律师（法律咨询）'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'PATCH')[1].body).toEqual({ revision: 3, category: '法律咨询' });
    expect(within(unknown).queryByText(/保洁/)).toBeNull();
  });

  it('还有没说清的步骤时确认按钮不可用', async () => {
    const calls: Call[] = [];
    render(<DecomposeScreen client={makeClient(BASE, calls)} task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    fireEvent.press(await screen.findByText('确认并发布可开工的步骤'));
    expect(calls.some((c) => c.path.endsWith('/confirm'))).toBe(false);
    expect(screen.getByText(/还有 1 步没说清/)).toBeTruthy();
  });

  it('全部说清后确认，回到任务', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    const ready = { ...DEC, unresolved: [], nodes: DEC.nodes.slice(0, 2) };
    render(<DecomposeScreen client={makeClient({ ...BASE, 'GET /tasks/9/decomposition': ready,
      'POST /decompositions/5/confirm': { decomposition: ready, children: [] } }, calls)}
                            task={TASK} onBack={() => {}} onConfirmed={done} />);
    fireEvent.press(await screen.findByText('确认并发布可开工的步骤'));
    await waitFor(() => expect(done).toHaveBeenCalled());
  });

  it('「继续拆下一层」只带 revision；「拆这一步」带上那一步', async () => {
    const calls: Call[] = [];
    render(<DecomposeScreen client={makeClient({ ...BASE, 'POST /decompositions/5/expand': { ...DEC, revision: 4 } }, calls)}
                            task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    fireEvent.press(await screen.findByText('继续拆下一层'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/decompositions/5/expand')).toHaveLength(1));
    expect(calls.find((c) => c.path === '/decompositions/5/expand')!.body).toEqual({ revision: 3 });
    fireEvent.press(within(screen.getByTestId('node-2')).getByText('拆这一步'));
    await waitFor(() => expect(calls.filter((c) => c.path === '/decompositions/5/expand')).toHaveLength(2));
    expect(calls.filter((c) => c.path === '/decompositions/5/expand')[1].body).toEqual({ revision: 4, node_ids: [2] });
  });

  it('模型不可用回落模板时明说', async () => {
    render(<DecomposeScreen client={makeClient({ ...BASE, 'GET /tasks/9/decomposition': { ...DEC, fallback: true } })}
                            task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    expect(await screen.findByText(/AI 模型暂时不可用/)).toBeTruthy();
  });

  it('还没拆过的草稿项目：进来就开始拆', async () => {
    const calls: Call[] = [];
    render(<DecomposeScreen client={makeClient({ ...BASE, '/tasks/9/tree': { parent_id: 9, parent_status: 'draft', progress_pct: 0, all_children_completed: false, children: [] },
      'POST /tasks/9/decompositions': DEC }, calls, {
      'GET /tasks/9/decomposition': { status: 404, code: 'no_decomposition_in_progress', message: '这个任务没有进行中的拆解' },
    })} task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    await screen.findByTestId('node-2');
    expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/9/decompositions')).toBe(true);
  });
});

describe('APP-077 入口', () => {
  const ME = { id: 1, nickname: '店主' } as never;

  it('发布方在草稿项目的详情页看得到「继续拆解」，别人看不到', async () => {
    const { unmount } = render(<TaskDetailScreen client={makeClient(BASE)} me={ME} task={TASK}
                                                 onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
    fireEvent.press(await screen.findByText(/继续拆解/));
    expect(await screen.findByTestId('node-2')).toBeTruthy();
    unmount();
    render(<TaskDetailScreen client={makeClient(BASE)} me={{ id: 2, nickname: '路人' } as never} task={TASK}
                             onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
    expect(screen.queryByText(/继续拆解/)).toBeNull();
  });

  it('子任务进度的响应不像预期时不画，也不把详情页带崩', async () => {
    render(<TaskDetailScreen client={makeClient({ ...BASE, '/tasks/9/tree': { unexpected: true } })} me={ME} task={TASK}
                             onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
    expect(await screen.findByText(/继续拆解/)).toBeTruthy();
    expect(screen.queryByText(/子任务进度/)).toBeNull();
  });

  it('确认后的项目在详情页显示子任务进度，点进去打开那一步', async () => {
    const open = jest.fn();
    const child = { ...TASK, id: 11, parent_id: 9, task_type: 'service', status: 'published', title: '开一家咖啡店 - 选址' };
    render(<TaskDetailScreen client={makeClient({ ...BASE, '/tasks/9/tree': { parent_id: 9, parent_status: 'draft', progress_pct: 0,
      all_children_completed: false, children: [{ id: 11, title: '开一家咖啡店 - 选址', status: 'published', budget_cents: 300000, depends_on: [], executor_id: null }] },
      '/tasks/11': child })} me={ME} task={TASK} onBack={() => {}} onChanged={async () => {}} onOpenTask={open} />);
    fireEvent.press(await screen.findByText(/子任务进度/).then(() => screen.getByText(/开一家咖啡店 - 选址/)));
    await waitFor(() => expect(open).toHaveBeenCalledWith(expect.objectContaining({ id: 11 })));
  });

  it('合作入口发布项目：建草稿（不发布）并把新任务交回去打开', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK }, calls)} allowProject onDone={done} />);
    fireEvent.press(screen.getByText(/要拆开做的项目/));
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '开一家咖啡店');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('创建并开始拆解'));
    await waitFor(() => expect(done).toHaveBeenCalledWith(expect.objectContaining({ id: 9 })));
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect(body.task_type).toBe('project');
    expect(body.publish_now).toBe(false);
  });

  it('SCN-107 几个人 × 连续几天：写明会拆成几个名额，请求带 people_needed / days / start_date', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK }, calls)} onDone={done} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '快闪店帮手');
    fireEvent.changeText(screen.getByLabelText('需要几个人'), '5');
    fireEvent.changeText(screen.getByLabelText('连续几天'), '3');
    fireEvent.changeText(screen.getByLabelText('从哪天开始'), '2030-01-05');
    expect(screen.getByText(/会拆成 15 个名额（5 人 × 3 天）/)).toBeTruthy();
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect(body).toMatchObject({ people_needed: 5, days: 3, start_date: '2030-01-05' });
  });

  it('从「不懂就问」来的发布页没有项目选项（那是一单具体的活）', () => {
    render(<PublishScreen client={makeClient({})} onDone={() => {}} category="法律咨询" />);
    expect(screen.queryByText(/要拆开做的项目/)).toBeNull();
  });
});


describe('SPACE-024 App 上的合作驾驶舱（移动简化版）', () => {
  it('进度、四个钱数、预警与关键路径', async () => {
    const node = (id: number, title: string) => ({ id, parent_id: 20, title, status: 'published', status_name: '招募中',
      budget_cents: 200000, is_container: false, depends_on: [], blocked_by: [], executor_id: null, executor_nickname: null,
      deadline: null, overdue: false, on_critical_path: true, in_dispute: false });
    const client = makeClient({ '/tasks/20/cockpit': {
      task_id: 20, title: '公司官网', status: 'draft', progress_pct: 25, steps_total: 4, steps_done: 1,
      budget: { planned_cents: 800000, allocated_cents: 800000, committed_cents: 200000, paid_cents: 200000, remaining_cents: 400000 },
      critical_path: [21, 22], alerts: [{ task_id: 22, kind: 'dispute', text: '「页面开发」在纠纷中，相关款项已冻结' }],
      nodes: [node(21, '需求梳理'), node(22, '页面开发')] } });
    render(<CockpitBlock client={client} taskId={20} />);
    expect(await screen.findByText('合作驾驶舱 · 1/4 步完成')).toBeTruthy();
    expect(screen.getByText('计划 ¥8000.00 · 已托管 ¥2000.00 · 已付 ¥2000.00 · 还剩 ¥4000.00')).toBeTruthy();
    expect(screen.getByText('• 「页面开发」在纠纷中，相关款项已冻结')).toBeTruthy();
    expect(screen.getByText('关键路径：需求梳理 → 页面开发')).toBeTruthy();
  });
});

describe('AI-DEC-021b App 驾驶舱的排期冲突（368 号 spec）', () => {
  it('排期冲突与晚于整件事的预警用警示样式，等你验收的不用', async () => {
    const node = (id: number, title: string) => ({ id, parent_id: 20, title, status: 'published', status_name: '招募中',
      budget_cents: 200000, is_container: false, depends_on: [], blocked_by: [], executor_id: null, executor_nickname: null,
      deadline: null, overdue: false, on_critical_path: false, in_dispute: false, schedule_conflicts: [] });
    const client = makeClient({ '/tasks/20/cockpit': {
      task_id: 20, title: '公司官网', status: 'draft', progress_pct: 0, steps_total: 2, steps_done: 0,
      budget: { planned_cents: 400000, allocated_cents: 400000, committed_cents: 0, paid_cents: 0, remaining_cents: 400000 },
      critical_path: [], alerts: [
        { task_id: 22, kind: 'schedule_conflict', text: '「页面开发」的截止不晚于它要等的「需求梳理」' },
        { task_id: 21, kind: 'past_parent_deadline', text: '「需求梳理」的截止晚于整件事的截止' },
        { task_id: 22, kind: 'to_accept', text: '「页面开发」已交付，等你验收' }],
      nodes: [node(21, '需求梳理'), { ...node(22, '页面开发'), schedule_conflicts: [21] }] } });
    render(<CockpitBlock client={client} taskId={20} />);
    const warn = (await screen.findByText('• 「页面开发」的截止不晚于它要等的「需求梳理」')).props.style;
    expect(warn.fontWeight).toBe('600');
    expect(screen.getByText('• 「需求梳理」的截止晚于整件事的截止').props.style.fontWeight).toBe('600');
    expect(screen.getByText('• 「页面开发」已交付，等你验收').props.style.fontWeight).toBeUndefined();
  });
});

describe('AI-DEC-021c App 驾驶舱的时间线（384 号 spec）', () => {
  const node = (id: number, title: string, extra: Record<string, unknown> = {}) => ({ id, parent_id: 20, title, status: 'published',
    status_name: '招募中', budget_cents: 200000, is_container: false, depends_on: [], blocked_by: [], executor_id: null,
    executor_nickname: null, deadline: null, overdue: false, on_critical_path: false, in_dispute: false, schedule_conflicts: [], ...extra });
  const base = { task_id: 20, title: '公司官网', status: 'draft', progress_pct: 0, steps_total: 2, steps_done: 0,
    budget: { planned_cents: 400000, allocated_cents: 400000, committed_cents: 0, paid_cents: 0, remaining_cents: 400000 },
    critical_path: [], alerts: [{ task_id: 20, kind: 'projected_late', text: '整件事会晚于截止' }] };

  it('预计完成日、每一步一条（赶不上截止的用警示样式），预警标警示', async () => {
    const client = makeClient({ '/tasks/20/cockpit': { ...base,
      nodes: [node(21, '需求梳理', { status: 'in_progress', est_days: 2 }), node(22, '页面开发', { status: 'in_progress', est_days: 8 })],
      timeline: { projected_finish: '2026-11-20T12:00:00Z', unknown_steps: [], rows: [
        { task_id: 21, start: '2026-11-10T12:00:00Z', end: '2026-11-12T12:00:00Z', basis: 'estimate', late: false },
        { task_id: 22, start: '2026-11-12T12:00:00Z', end: '2026-11-20T12:00:00Z', basis: 'estimate', late: true }] } } });
    render(<CockpitBlock client={client} taskId={20} />);
    expect(await screen.findByText(/^按各步工期排下来，预计 .*20.* 做完$/)).toBeTruthy();
    expect(screen.getByTestId('bar-fill-22').props.style.left).toBe('20%');
    expect(screen.getByTestId('bar-fill-22').props.style.width).toBe('80%');
    expect(screen.getByText(/页面开发 · 到 .* · 按工期估计（赶不上这一步的截止）/).props.style.fontWeight).toBe('600');
    expect(screen.getByText(/需求梳理 · 到 .* · 按工期估计$/).props.style.fontWeight).toBeUndefined();
    expect(screen.getByText('• 整件事会晚于截止').props.style.fontWeight).toBe('600');
    // 都开工了：没有可填工期的步骤
    expect(screen.queryByLabelText('需求梳理 工期（天）')).toBeNull();
  });

  it('排不出来时说清几步没填；没开工的步骤就地填工期，存完重新取驾驶舱', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/tasks/20/cockpit': { ...base, alerts: [],
      nodes: [node(21, '需求梳理'), node(22, '页面开发', { status: 'in_progress', est_days: 5 })],
      timeline: { projected_finish: null, unknown_steps: [21], rows: [
        { task_id: 21, start: null, end: null, basis: 'unknown', late: false },
        { task_id: 22, start: '2026-11-10T12:00:00Z', end: '2026-11-15T12:00:00Z', basis: 'estimate', late: false }] } } }, calls);
    render(<CockpitBlock client={client} taskId={20} />);
    expect(await screen.findByText('有 1 步没填工期也没填截止，排不出整件事的完成日：给每一步填上要几天')).toBeTruthy();
    expect(screen.queryByLabelText('页面开发 工期（天）')).toBeNull();
    fireEvent.changeText(screen.getByLabelText('需求梳理 工期（天）'), '400');
    expect(screen.getByText('1~365 天')).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('需求梳理 工期（天）'), '3');
    const before = calls.filter((c) => c.path === '/tasks/20/cockpit').length;
    fireEvent.press(screen.getByText('存'));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.path === '/tasks/21')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ est_days: 3 });
    await waitFor(() => expect(calls.filter((c) => c.path === '/tasks/20/cockpit').length).toBe(before + 1));
  });

  it('老服务端没有时间线、步骤都开工了：不画这一块', async () => {
    const client = makeClient({ '/tasks/20/cockpit': { ...base, alerts: [],
      nodes: [node(21, '需求梳理', { status: 'in_progress' })] } });
    render(<CockpitBlock client={client} taskId={20} />);
    await screen.findByText('合作驾驶舱 · 0/2 步完成');
    expect(screen.queryByLabelText('时间线')).toBeNull();
  });
});

describe('AI-DEC-021c App 拆解时给一步填工期（384 号 spec）', () => {
  it('填了工期随这一步保存，超范围不让存，不填不带字段', async () => {
    const calls: Call[] = [];
    render(<DecomposeScreen client={makeClient({ ...BASE, 'GET /tasks/9/decomposition': { ...DEC,
      nodes: DEC.nodes.map((n) => n.id === 2 ? { ...n, est_days: 4 } : n) }, 'PATCH /decompositions/5/nodes/3': DEC }, calls)}
      task={TASK} onBack={() => {}} onConfirmed={() => {}} />);
    expect(within(await screen.findByTestId('node-2')).getByText(/工期 4 天/)).toBeTruthy();
    const box = screen.getByTestId('node-3');
    fireEvent.press(within(box).getByText('编辑'));
    fireEvent.changeText(within(box).getByPlaceholderText('要几天（工期估计，选填）'), '0');
    expect(within(box).getByText('工期填 1~365 天')).toBeTruthy();
    fireEvent.changeText(within(box).getByPlaceholderText('要几天（工期估计，选填）'), '6');
    fireEvent.press(within(box).getByText('保存这一步'));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toMatchObject({ revision: 3, est_days: 6 });
    fireEvent.press(within(screen.getByTestId('node-2')).getByText('编辑'));
    fireEvent.press(within(screen.getByTestId('node-2')).getByText('保存这一步'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'PATCH')[1].body).toMatchObject({ est_days: 4 });
  });
});
