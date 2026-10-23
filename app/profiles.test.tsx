// PROF-100 任务画像与能力画像在 App 上的行为（126 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Me, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';
import { CapabilityScreen, DraftHints, TaskProfileBlock } from './profiles';

type Call = { method: string; path: string; body?: unknown };
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

describe('PROF-100 App 上的画像', () => {
  it('发布时提示缺什么与预算位置', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'POST /profiles/task-draft': { category: '跑腿', mode: 'remote', declared_skills: [], inferred_skills: [], size: 'small',
      price: { sample_size: 3, p50_cents: 5000, min_cents: 3000, max_cents: 8000, position: 'below_median' }, risks: [],
      completeness: 0.5, checks: [{ key: 'deadline', ok: false, hint: '给一个截止时间' }] } }, calls);
    render(<DraftHints client={client} draft={{ title: '帮忙取快递', category: '跑腿', budget_cents: 3500, is_remote: true }} delayMs={0} />);
    expect(await screen.findByText('说明完整度 50%')).toBeTruthy();
    expect(screen.getByText('预算低于同类成交中位（中位 ¥50.00）')).toBeTruthy();
    expect(screen.getByText('· 给一个截止时间')).toBeTruthy();
    await waitFor(() => expect(calls.find((c) => c.path === '/profiles/task-draft')?.body).toMatchObject({ title: '帮忙取快递', budget_cents: 3500 }));
  });

  it('KB-094 样本被一位发布方占了大半：括号里写去重后的中位（271 号 spec）', async () => {
    const client = makeClient({ 'POST /profiles/task-draft': { category: '跑腿', mode: 'remote', declared_skills: [], inferred_skills: [], size: 'small',
      price: { sample_size: 9, p50_cents: 5000, min_cents: 5000, max_cents: 22000, position: 'below_median', concentrated: true, reference_cents: 18000 },
      risks: [], completeness: 0.5, checks: [] } }, []);
    render(<DraftHints client={client} draft={{ title: '排队', category: '跑腿', budget_cents: 10000, is_remote: true }} delayMs={0} />);
    expect(await screen.findByText('预算低于同类成交中位（按发布方去重后的中位 ¥180.00）')).toBeTruthy();
  });

  it('SCN-106 创作类的单：列出九项里还没写的（140 号 spec）', async () => {
    const client = makeClient({ 'POST /profiles/task-draft': { category: '设计', mode: 'remote', declared_skills: [], inferred_skills: [], size: 'unknown',
      price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' }, risks: [],
      completeness: 0.5, checks: [], brief: { missing: 1, items: [{ name: '用途', ok: true, ask: '用在哪儿？' }, { name: '版权授权', ok: false, ask: '版权怎么约定？' }] } } }, []);
    render(<DraftHints client={client} draft={{ title: '海报', category: '设计' }} delayMs={0} />);
    expect(await screen.findByText('创作类需求一般写清九项，已写 1/2。还可以补：')).toBeTruthy();
    expect(screen.getByText('· 版权授权：版权怎么约定？')).toBeTruthy();
    expect(screen.queryByText(/用在哪儿/)).toBeNull();
  });

  it('取不到画像时不显示，不挡发布', async () => {
    const client = makeClient({}, []);
    render(<DraftHints client={client} draft={{ title: 'x' }} delayMs={0} />);
    await waitFor(() => expect(screen.queryByText(/说明完整度/)).toBeNull());
  });

  it('任务详情：这单的画像写出风险与技能', async () => {
    const client = makeClient({ '/tasks/7/profile': { task_id: 7, category: '跑腿', mode: 'onsite', declared_skills: [], inferred_skills: ['驾驶'],
      size: 'medium', price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' },
      risks: [{ kind: 'advance', text: '需要垫付：金额与凭证提前说清' }], completeness: 0.7, checks: [] } }, []);
    render(<TaskProfileBlock client={client} taskId={7} />);
    expect(await screen.findByText('⚠ 需要垫付：金额与凭证提前说清')).toBeTruthy();
    expect(screen.getByText(/线下 · 技能：驾驶 · 说明完整度 70%/)).toBeTruthy();
  });

  it('我的能力画像：自述与佐证分开', async () => {
    const client = makeClient({ '/users/me/capability': { user_id: 2, tasks_completed: 2, categories: [{ category: '保洁', completed: 2, rating_avg: 5 }],
      skills: [{ skill: '收纳', evidenced: false }], certifications: [], on_time_rate: null, rework_rate: null, reply_hours_median: null,
      has_weekly_slots: false, limited_capacity: false, note: '', disputes: 0 } }, []);
    render(<CapabilityScreen client={client} />);
    expect(await screen.findByText('· 保洁：完成 2 单，平均 5 星')).toBeTruthy();
    expect(screen.getByText('技能：收纳（自述）')).toBeTruthy();
    expect(screen.getByText(/准时交付 样本不足/)).toBeTruthy();
  });
});

describe('SCN-110 App 任务详情上的需求九项', () => {
  const profile = (brief: unknown) => ({ '/tasks/7/profile': { task_id: 7, category: '设计', mode: 'remote', declared_skills: [], inferred_skills: [],
    size: 'medium', price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' }, risks: [], completeness: 0.6,
    checks: [], brief } });
  const BRIEF = { missing: 1, items: [{ name: '用途', ok: true, ask: '用在哪儿？' }, { name: '版权授权', ok: false, ask: '版权怎么约定？' }] };

  it('接单的人看到报名前该问的话，发单人看到还可以补', async () => {
    const { unmount } = render(<TaskProfileBlock client={makeClient(profile(BRIEF), [])} taskId={7} />);
    expect(await screen.findByText('说明里没写的 1 项，报名前可以先问问发单人：')).toBeTruthy();
    expect(screen.getByText('· 版权授权：版权怎么约定？')).toBeTruthy();
    unmount();
    render(<TaskProfileBlock client={makeClient(profile(BRIEF), [])} taskId={7} isCreator />);
    expect(await screen.findByText('创作类需求一般写清九项，已写 1/2。还可以补：')).toBeTruthy();
  });
});

describe('SCN-135 App 带着这些问题报名', () => {
  const BRIEF = { missing: 1, items: [{ name: '用途', ok: true, ask: '用在哪儿？' }, { name: '版权授权', ok: false, ask: '版权怎么约定？' }] };
  const profile = { '/tasks/7/profile': { task_id: 7, category: '设计', mode: 'remote', declared_skills: [], inferred_skills: [], size: 'medium',
    price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' }, risks: [], completeness: 0.5, checks: [], brief: BRIEF } };
  it('能报名时有按钮，按下把问题交给报名', async () => {
    const onApply = jest.fn();
    render(<TaskProfileBlock client={makeClient(profile, [])} taskId={7} onApplyWithQuestions={onApply} />);
    fireEvent.press(await screen.findByText('带着这些问题报名'));
    expect(onApply).toHaveBeenCalledWith('我可以做。报名前想先确认几件事：\n1. 版权授权：版权怎么约定？');
  });
  it('发单人自己、或不能报名时没有按钮', async () => {
    const { unmount } = render(<TaskProfileBlock client={makeClient(profile, [])} taskId={7} isCreator onApplyWithQuestions={jest.fn()} />);
    await screen.findByText('创作类需求一般写清九项，已写 1/2。还可以补：');
    expect(screen.queryByText('带着这些问题报名')).toBeNull();
    unmount();
    render(<TaskProfileBlock client={makeClient(profile, [])} taskId={7} />);
    await screen.findByText('说明里没写的 1 项，报名前可以先问问发单人：');
    expect(screen.queryByText('带着这些问题报名')).toBeNull();
  });
});

describe('SCN-135 App 任务详情里接上报名', () => {
  it('在招的单、不是发单人：按下就带着问题报名', async () => {
    const calls: Call[] = [];
    const BRIEF = { missing: 1, items: [{ name: '版权授权', ok: false, ask: '版权怎么约定？' }] };
    const client = makeClient({ '/tasks/7/profile': { task_id: 7, category: '设计', mode: 'remote', declared_skills: [], inferred_skills: [],
      size: 'medium', price: { sample_size: 0, p50_cents: null, min_cents: null, max_cents: null, position: 'unknown' }, risks: [],
      completeness: 0.5, checks: [], brief: BRIEF }, 'POST /tasks/7/applications': { id: 5, status: 'pending' } }, calls);
    const task = { id: 7, creator_id: 1, executor_id: null, parent_id: null, depends_on: [], title: '海报', description: '', category: '设计',
      task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign', bonus_cents: 0,
      is_remote: true, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '', status: 'published', deadline: null,
      reject_count: 0, created_at: '2026-10-16T00:00:00Z' } as Task;
    render(<TaskDetailScreen client={client} me={{ id: 2, nickname: '我' } as unknown as Me} task={task} onBack={() => {}} onChanged={async () => {}} />);
    fireEvent.press(await screen.findByText('带着这些问题报名'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/7/applications')?.body)
      .toEqual({ message: '我可以做。报名前想先确认几件事：\n1. 版权授权：版权怎么约定？' }));
  });
});
