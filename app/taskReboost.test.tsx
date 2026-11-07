// AI-DEC-023（320 号 spec）App 上没人报名的单：发单人一键再推一次，可选加价；有人报名、一单多天的母任务不给。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Me, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';

const TASK = { id: 8, creator_id: 1, executor_id: null, parent_id: null, depends_on: [], title: '上门开锁', description: '',
  category: '上门开锁', task_type: 'simple', required_skills: [], budget_cents: 10000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '', deadline: null,
  reject_count: 0, created_at: '2026-10-16T00:00:00Z', status: 'published', days: 1 } as unknown as Task;
type Call = { method: string; path: string; body: unknown };

function open(calls: Call[], task: Task = TASK, apps: unknown[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    const body = path === '/tasks/8/applications' ? apps
      : path === '/tasks/8/reboost' ? { task_id: 8, raise_cents: 0, budget_cents: 10000 } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<TaskDetailScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}
                           me={{ id: 1, nickname: 'x' } as unknown as Me} task={task}
                           onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
}

describe('AI-DEC-023 App 再推一次', () => {
  it('没人报名：加价写错不发；空着只再推一次', async () => {
    const calls: Call[] = [];
    open(calls);
    fireEvent.changeText(await screen.findByLabelText('加价（元）'), 'abc');
    fireEvent.press(screen.getByText('再推一次'));
    expect(await screen.findByText(/加价写一个正数/)).toBeTruthy();
    expect(calls.some((c) => c.path === '/tasks/8/reboost')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('加价（元）'), '');
    fireEvent.press(screen.getByText('再推一次'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/8/reboost')?.body).toEqual({ raise_cents: 0 }));
    expect(await screen.findByText('已再推一次：会推给附近有空、订阅了这个类目的人。6 小时后可以再推。')).toBeTruthy();
  });

  it('有人报名就不出', async () => {
    open([], TASK, [{ id: 21, applicant_id: 5, nickname: '甲', credit_score: 100, rating_avg: 0, bid_cents: 10000, message: '能来', status: 'pending' }]);
    expect(await screen.findByText(/甲 · 信用/)).toBeTruthy();
    expect(screen.queryByLabelText('再推一次')).toBeNull();
  });

  it('一单多天的母任务不出（走按天补招）', async () => {
    open([], { ...TASK, days: 3 } as Task);
    expect(await screen.findByText('暂无报名，可稍后下拉刷新')).toBeTruthy();
    expect(screen.queryByLabelText('再推一次')).toBeNull();
  });
});
