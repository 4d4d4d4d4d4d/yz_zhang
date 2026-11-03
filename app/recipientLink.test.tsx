// SCN-122 App 上的服务对象进度链接（356 号 spec）：发单人生成并交给系统分享（完整网页地址），能作废；
// 不是替别人发的单、不是发单人、单子结束都不出现；没配网页地址时不生成（对方打不开）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';
import { RecipientLinkBlock, canShareRecipientLink } from './recipientLink';

type Call = { method: string; path: string; body: unknown };
const NONE = { state: 'none', task_id: null, created_at: null, expires_at: null, view_count: 0, last_viewed_at: null };
const ACTIVE = { state: 'active', task_id: 60, created_at: '2026-11-03T00:00:00Z', expires_at: '2026-11-10T00:00:00Z', view_count: 0, last_viewed_at: null };
function makeClient(routes: Record<string, unknown>, calls: Call[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[`${method} ${path}`] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const TASK = (extra: Partial<Task>) => ({ id: 60, creator_id: 9, executor_id: null, parent_id: null, depends_on: [], title: '装扶手',
  description: '', category: '维修', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed',
  ip_assignment: 'assign', bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'published', deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z',
  on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139', ...extra }) as Task;

describe('SCN-122 App 服务对象进度链接', () => {
  it('只在替别人发、发单人本人、单子没结束时出现', () => {
    expect(canShareRecipientLink(TASK({}), 9)).toBe(true);
    expect(canShareRecipientLink(TASK({ on_behalf: false }), 9)).toBe(false);
    expect(canShareRecipientLink(TASK({}), 5)).toBe(false);
    expect(canShareRecipientLink(TASK({ status: 'completed' }), 9)).toBe(false);
    expect(canShareRecipientLink(TASK({ status: 'cancelled' }), 9)).toBe(false);
    expect(canShareRecipientLink(TASK({ status: 'in_progress' }), 9)).toBe(true);
  });

  it('生成：带上选的天数，分享完整网页地址；作废', async () => {
    const calls: Call[] = [];
    const share = jest.fn(async () => undefined);
    const client = makeClient({
      'GET /tasks/60/recipient-link': NONE,
      'POST /tasks/60/recipient-link': { ...ACTIVE, token: 'abcTOKEN', path: '/r/abcTOKEN', hint: '' },
      'DELETE /tasks/60/recipient-link': { ...ACTIVE, state: 'revoked', revoked: 1 },
    }, calls);
    render(<RecipientLinkBlock client={client} taskId={60} origin="https://opc.example" share={share} />);
    await screen.findByText(/还没有生成/);
    fireEvent.press(screen.getByLabelText('有效 3 天'));
    fireEvent.press(screen.getByText('生成并分享链接'));
    await waitFor(() => expect(share).toHaveBeenCalled());
    expect((share.mock.calls[0] as unknown as [{ message: string }])[0].message).toContain('https://opc.example/r/abcTOKEN');
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ days: 3 });
    fireEvent.press(await screen.findByText('作废链接'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/tasks/60/recipient-link')).toBe(true));
    expect(await screen.findByText(/^链接已作废；/)).toBeTruthy();
    expect(screen.getByText(/对方再打开会看到/)).toBeTruthy();
  });

  it('没配网页地址：不生成，说清在网页上生成', async () => {
    const calls: Call[] = [];
    const share = jest.fn(async () => undefined);
    render(<RecipientLinkBlock client={makeClient({ 'GET /tasks/60/recipient-link': NONE }, calls)} taskId={60} origin="" share={share} />);
    fireEvent.press(await screen.findByText('生成并分享链接'));
    expect(await screen.findByText(/没有配置网页地址/)).toBeTruthy();
    expect(share).not.toHaveBeenCalled();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('详情页接上：发单人看得到，别人看不到', async () => {
    const client = makeClient({ 'GET /tasks/60/recipient-link': NONE });
    const { unmount } = render(<TaskDetailScreen client={client} me={{ id: 9, nickname: '女儿' } as never}
      task={TASK({})} onBack={() => {}} onChanged={async () => {}} />);
    expect(await screen.findByLabelText('服务对象进度链接')).toBeTruthy();
    unmount();
    render(<TaskDetailScreen client={client} me={{ id: 5, nickname: '路人' } as never}
      task={TASK({})} onBack={() => {}} onChanged={async () => {}} />);
    expect(screen.queryByLabelText('服务对象进度链接')).toBeNull();
  });
});
