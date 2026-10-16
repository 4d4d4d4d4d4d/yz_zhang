// SCN-117 App 上每天的时段（178 号 spec）：发布页写几点到几点；详情页显示。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { PublishScreen, TaskDetailScreen } from './App';

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
const TASK = { id: 80, creator_id: 9, executor_id: null, parent_id: null, depends_on: [], title: '快闪店帮手', description: '',
  category: '跑腿', task_type: 'service', required_skills: [], budget_cents: 10000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '', status: 'published',
  deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z', days: 3, shift_start: '09:00', shift_end: '18:30' } as Task;

describe('SCN-117 App 每天的时段', () => {
  it('发布页：写了就带进请求；没写不带', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK }, calls)} onDone={done} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '快闪店帮手');
    fireEvent.changeText(screen.getByLabelText('每天几点开始'), '09:00');
    fireEvent.changeText(screen.getByLabelText('每天几点结束'), '18:30');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).toMatchObject({ shift_start: '09:00', shift_end: '18:30' });
  });

  it('详情页：每天 09:00–18:30', () => {
    render(<TaskDetailScreen client={makeClient({})} me={{ id: 2, nickname: '帮手' } as never} task={TASK}
                             onBack={() => {}} onChanged={async () => {}} />);
    expect(screen.getByLabelText('时段').props.children.join('')).toContain('每天 09:00–18:30');
  });
});
