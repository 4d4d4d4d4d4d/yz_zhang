// AI-DEC-024（321 号 spec）App 上项目里的一步：交付人开放给下一步、收回；下一步的执行者看前一步开放的成果。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Me, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';

const TASK = (id: number, status: string, executor: number) => ({ id, creator_id: 9, executor_id: executor, parent_id: 10,
  depends_on: id === 12 ? [11] : [], title: id === 11 ? '需求文档' : '前端开发', description: '', category: '软件开发',
  task_type: 'project', required_skills: [], budget_cents: 5000, pricing: 'fixed', ip_assignment: 'assign', bonus_cents: 0,
  is_remote: true, city: '', lat: null, lng: null, address_hint: '', address_exact: '', deadline: null, reject_count: 0,
  created_at: '2026-10-16T00:00:00Z', status }) as unknown as Task;
const VIEW = (shared: boolean, delivered = true) => ({ task_id: 11, delivered,
  next_steps: [{ task_id: 12, title: '前端开发', status: 'in_progress', executor_nickname: '小李', shared, ...(shared ? { share_id: 5 } : {}) }] });
type Call = { method: string; path: string; body: unknown };

function open(me: number, task: Task, calls: Call[], routes: Record<string, unknown>) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[`${method} ${path}`] ?? []) };
  }) as unknown as typeof fetch;
  render(<TaskDetailScreen client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}
                           me={{ id: me, nickname: 'x' } as unknown as Me} task={task}
                           onBack={() => {}} onChanged={async () => {}} onOpenTask={() => {}} />);
}

describe('AI-DEC-024 App 跨子任务产出共享', () => {
  it('交付人：开放给下一步、再收回', async () => {
    const calls: Call[] = [];
    open(2, TASK(11, 'pending_acceptance', 2), calls, {
      'GET /tasks/11/shares': VIEW(false), 'POST /tasks/11/shares': VIEW(true), 'DELETE /tasks/11/shares/5': VIEW(false) });
    fireEvent.press(await screen.findByText('开放给这一步'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/11/shares')?.body).toEqual({ to_task_id: 12 }));
    fireEvent.press(await screen.findByText('收回'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/tasks/11/shares/5')).toBe(true));
    expect(await screen.findByText('开放给这一步')).toBeTruthy();
  });

  it('还没交付：只说明，没有按钮', async () => {
    open(2, TASK(11, 'in_progress', 2), [], { 'GET /tasks/11/shares': VIEW(false, false) });
    expect(await screen.findByText(/交付之后，可以把交付说明和预览图开放/)).toBeTruthy();
    expect(screen.queryByText('开放给这一步')).toBeNull();
  });

  it('下一步的执行者：看得到前一步开放的交付说明；没开放就没有这一块', async () => {
    open(3, TASK(12, 'in_progress', 3), [], { 'GET /tasks/12/inputs': [{ from_task_id: 11, title: '需求文档', shared_at: '2030-01-05T02:00:00Z',
      deliveries: [{ content: '接口约定见第 3 页', images: [], created_at: '2030-01-05T01:00:00Z' }], previews: [{ id: 3, url: '/api/v1/files/p.png' }] }] });
    expect(await screen.findByText('接口约定见第 3 页')).toBeTruthy();
    expect(screen.getByLabelText('前一步的预览图')).toBeTruthy();
  });

  it('前一步没开放：不出「前一步的成果」', async () => {
    open(3, TASK(12, 'in_progress', 3), [], {});
    expect(await screen.findByText(/前端开发/)).toBeTruthy();
    expect(screen.queryByText('前一步的成果')).toBeNull();
  });
});
