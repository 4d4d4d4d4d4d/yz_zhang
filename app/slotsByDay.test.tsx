// SCN-116 App 上按天看名额（174 号 spec）：多天母任务的子任务进度里，一天一行，哪天还缺几个人。
import { render, screen } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';
import { TaskTreeBlock } from './decompose';

function makeClient(routes: Record<string, unknown>) {
  const fetchImpl = (async (url: string) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const child = (id: number, date: string | null, status: string) => ({ id, title: `名额 ${id}`, status, budget_cents: 2500,
  depends_on: [], executor_id: status === 'published' ? null : 5, work_date: date });
const TASK = { id: 30, title: '快闪店帮手', parent_id: null, task_type: 'service', days: 2, people_needed: 2 } as unknown as Task;

describe('SCN-116 App 按天看名额', () => {
  it('一天一行；有几天缺人', async () => {
    const client = makeClient({ '/tasks/30/tree': { parent_id: 30, parent_status: 'draft', progress_pct: 0, all_children_completed: false,
      children: [child(31, '2030-01-05', 'matched'), child(32, '2030-01-06', 'published')],
      by_day: [{ date: '2030-01-05', slots: 1, filled: 1, open: 0, done: 0, closed: 0 },
        { date: '2030-01-06', slots: 1, filled: 0, open: 1, done: 0, closed: 0 }] } });
    render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} />);
    expect(await screen.findByText('还有 1 天缺人')).toBeTruthy();
    expect(screen.getByText('01-05 · 1 个名额：招到 1，不缺人了')).toBeTruthy();
    expect(screen.getByText('01-06 · 1 个名额：招到 0，还缺 1')).toBeTruthy();
  });

  it('没有按天汇总（单天多人）：只出名额，不出按天那一块', async () => {
    const client = makeClient({ '/tasks/30/tree': { parent_id: 30, parent_status: 'draft', progress_pct: 0, all_children_completed: false,
      children: [child(31, null, 'published')], by_day: [] } });
    render(<TaskTreeBlock client={client} task={TASK} onOpenTask={() => {}} />);
    expect(await screen.findByText(/名额 31/)).toBeTruthy();
    expect(screen.queryByLabelText('按天看名额')).toBeNull();
  });

  it('详情页：多天的母任务（不是项目型）也出子任务进度与按天汇总', async () => {
    const parent = { id: 30, creator_id: 1, executor_id: null, parent_id: null, depends_on: [], title: '快闪店帮手', description: '',
      category: '跑腿', task_type: 'service', required_skills: [], budget_cents: 5000, pricing: 'fixed', ip_assignment: 'assign',
      bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '', status: 'draft',
      deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z', days: 2, people_needed: 1, work_date: '2030-01-05' } as Task;
    const client = makeClient({ '/tasks/30/tree': { parent_id: 30, parent_status: 'draft', progress_pct: 0, all_children_completed: false,
      children: [child(31, '2030-01-05', 'published'), child(32, '2030-01-06', 'published')],
      by_day: [{ date: '2030-01-05', slots: 1, filled: 0, open: 1, done: 0, closed: 0 },
        { date: '2030-01-06', slots: 1, filled: 0, open: 1, done: 0, closed: 0 }] } });
    render(<TaskDetailScreen client={client} me={{ id: 1, nickname: '店主' } as never} task={parent}
                             onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
    expect(await screen.findByText('还有 2 天缺人')).toBeTruthy();
    expect(screen.getByText(/子任务进度/)).toBeTruthy();
  });
});
