// SCN-122c App「出发了」（364 号 spec）：只有接单人、线下单、待上门时出现；带上选的分钟数；告诉他已通知发单人。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';
import { DepartBlock, canDepart } from './depart';

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
const TASK = (extra: Partial<Task>) => ({ id: 60, creator_id: 9, executor_id: 2, parent_id: null, depends_on: [], title: '装扶手',
  description: '', category: '维修', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed',
  ip_assignment: 'assign', bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'in_progress', deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z', ...extra }) as Task;

describe('SCN-122c App 出发了', () => {
  it('只有接单人、线下单、待上门时能报', () => {
    expect(canDepart(TASK({}), 2)).toBe(true);
    expect(canDepart(TASK({ status: 'matched' }), 2)).toBe(true);
    expect(canDepart(TASK({ is_remote: true }), 2)).toBe(false);
    expect(canDepart(TASK({}), 9)).toBe(false);
    expect(canDepart(TASK({ status: 'pending_acceptance' }), 2)).toBe(false);
  });

  it('选分钟数后点出发了：请求带分钟数，提示已告诉发单人', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'POST /tasks/60/depart': { id: 1, departed_at: '2026-11-03T01:00:00Z', eta_at: '2026-11-03T01:45:00Z', updated: false } }, calls);
    render(<DepartBlock client={client} taskId={60} />);
    fireEvent.press(screen.getByLabelText('预计 45 分钟到'));
    fireEvent.press(screen.getByText('出发了'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ eta_minutes: 45 }));
    expect(await screen.findByText(/已告诉发单人/)).toBeTruthy();
  });

  it('详情页接上：接单人看得到，发单人看不到', () => {
    const client = makeClient({});
    const { unmount } = render(<TaskDetailScreen client={client} me={{ id: 2, nickname: '师傅' } as never}
      task={TASK({})} onBack={() => {}} onChanged={async () => {}} />);
    expect(screen.getByLabelText('出发了')).toBeTruthy();
    unmount();
    render(<TaskDetailScreen client={client} me={{ id: 9, nickname: '女儿' } as never}
      task={TASK({})} onBack={() => {}} onChanged={async () => {}} />);
    expect(screen.queryByLabelText('出发了')).toBeNull();
  });
});
