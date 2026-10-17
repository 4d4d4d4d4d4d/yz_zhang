// SCN-118 App 上一次报多天（177 号 spec）：多天母任务的子任务进度里，不是发单人的人勾几天一次报完。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';
import { TaskTreeBlock } from './decompose';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[`${method} ${path}`] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const TASK = { id: 30, title: '快闪店帮手', parent_id: null, task_type: 'service', days: 3, people_needed: 2, creator_id: 9 } as unknown as Task;
const TREE = { parent_id: 30, parent_status: 'published', progress_pct: 0, all_children_completed: false,
  children: [{ id: 31, title: '名额 31', status: 'published', budget_cents: 1666, depends_on: [], executor_id: null, work_date: '2030-01-05' }],
  by_day: [{ date: '2030-01-05', slots: 2, filled: 2, open: 0, done: 0, closed: 0 },
    { date: '2030-01-06', slots: 2, filled: 0, open: 2, done: 0, closed: 0 }] };

describe('SCN-118 App 一次报多天', () => {
  it('只列还缺人的那几天，勾了一次报完并说清结果', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /tasks/30/tree': TREE,
      'POST /tasks/30/apply-days': { applied: [{ date: '2030-01-06', task_id: 33, application_id: 1 }], skipped: [] } }, calls);
    render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} meId={2} />);
    await screen.findByLabelText('一次报多天');
    expect(screen.queryByLabelText('报 2030-01-05')).toBeNull();
    fireEvent.press(screen.getByLabelText('报 2030-01-06'));
    fireEvent.press(screen.getByText('报这几天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/30/apply-days')?.body).toEqual(
      { dates: ['2030-01-06'], message: '' }));
    expect(await screen.findByText('已报：01-06')).toBeTruthy();
  });

  it('发单人自己、或没登录时没有这一块', async () => {
    const client = makeClient({ 'GET /tasks/30/tree': TREE,
      'GET /tasks/30/applicants': [{ applicant_id: 5, nickname: '小王', days: [{ date: '2030-01-06', task_id: 33, application_id: 1 }] }] });
    const { unmount } = render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} meId={9} />);
    await screen.findByLabelText('按天看名额');
    expect(screen.queryByLabelText('一次报多天')).toBeNull();
    unmount();
    render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} />);
    await screen.findByLabelText('按天看名额');
    expect(screen.queryByLabelText('一次报多天')).toBeNull();
    expect(screen.queryByLabelText('按人选')).toBeNull();   // 没登录也看不到别人报了什么
  });

  it('名额页能回到整单', async () => {
    const slot = { id: 31, creator_id: 9, executor_id: null, parent_id: 30, depends_on: [], title: '快闪店帮手 · 第1天', description: '',
      category: '跑腿', task_type: 'service', required_skills: [], budget_cents: 1666, pricing: 'fixed', ip_assignment: 'assign',
      bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '', status: 'published',
      deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z', work_date: '2030-01-05' } as Task;
    const opened = jest.fn();
    const client = makeClient({ 'GET /tasks/30': { ...TASK, id: 30 } });
    render(<TaskDetailScreen client={client} me={{ id: 2, nickname: '帮手' } as never} task={slot}
                             onBack={() => {}} onChanged={async () => {}} onOpenTask={opened} />);
    fireEvent.press(await screen.findByText('这单一共好几天：回到整单，一次报多天 →'));
    await waitFor(() => expect(opened).toHaveBeenCalledWith(expect.objectContaining({ id: 30 })));
  });

  it('SCN-126 发单人按人选：一次选同一个人的多天', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /tasks/30/tree': TREE,
      'GET /tasks/30/applicants': [{ applicant_id: 5, nickname: '小王', days: [{ date: '2030-01-06', task_id: 33, application_id: 1 }] }],
      'POST /tasks/30/accept-person': { accepted: [{ date: '2030-01-06', task_id: 33, contract_id: 8 }], skipped: [] } }, calls);
    render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} meId={9} />);
    fireEvent.press(await screen.findByText('小王 · 01-06 → 选 TA 的这 1 天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/30/accept-person')?.body).toEqual({ applicant_id: 5 }));
    expect(await screen.findByText('已选 小王：01-06（每天一份合约，去各名额签署、托管）')).toBeTruthy();
    expect(screen.queryByLabelText('一次报多天')).toBeNull();
  });
});

describe('SCN-121 App 发单人补招缺人的那天', () => {
  it('默认选第一个缺人的日子，只再推一次；结果写明', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /tasks/30/tree': TREE, 'GET /tasks/30/applicants': [],
      'POST /tasks/30/days/2030-01-06/reboost': { date: '2030-01-06', slot_ids: [33, 34], raise_cents: 0, budget_cents: [1666, 1666] } }, calls);
    render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} meId={9} />);
    await screen.findByLabelText('补招');
    expect(screen.queryByLabelText('补招 2030-01-05')).toBeNull();
    fireEvent.press(screen.getByText('补招这天'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/reboost'))?.body).toEqual({ raise_cents: 0 }));
    expect(await screen.findByText('已补招 01-06：2 个还在招的名额再推了一次。6 小时后可以再补一次。')).toBeTruthy();
  });

  it('帮手看不到补招', async () => {
    render(<TaskTreeBlock client={makeClient({ 'GET /tasks/30/tree': TREE })} task={TASK} onOpenTask={() => {}} meId={2} />);
    await screen.findByLabelText('按天看名额');
    expect(screen.queryByLabelText('补招')).toBeNull();
  });
});
