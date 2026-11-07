// SCN-119 App 上替别人发单（175 号 spec）：勾上才出现三项、只在勾了时带进请求；详情页按可见性显示。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { PublishScreen, TaskDetailScreen } from './App';
import { RecipientEditorBlock, canChangeRecipient } from './recipient';

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
const TASK = (extra: Partial<Task>) => ({ id: 60, creator_id: 9, executor_id: null, parent_id: null, depends_on: [], title: '装扶手',
  description: '', category: '维修', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed',
  ip_assignment: 'assign', bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'published', deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z', ...extra }) as Task;

describe('SCN-119 App 替别人发单', () => {
  it('勾上才出现三项；请求带称呼、到场联系与「问过本人」', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK({}) }, calls)} onDone={done} />);
    expect(screen.queryByLabelText('服务对象称呼')).toBeNull();
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '装扶手');
    fireEvent.press(screen.getByLabelText('替别人发'));
    fireEvent.changeText(screen.getByLabelText('服务对象称呼'), '我妈');
    fireEvent.changeText(screen.getByLabelText('到场联系'), '王阿姨 139');
    fireEvent.press(screen.getByLabelText('已经问过本人'));
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).toMatchObject(
      { on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139', recipient_consented: true });
  });

  it('不勾就不带这几项', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK({}) }, calls)} onDone={done} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '取快递');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect('on_behalf' in body || 'recipient_label' in body || 'onsite_contact' in body).toBe(false);
  });

  it('详情页：别人只看到「替别人发的单」，成交双方看到称呼与到场联系', () => {
    const client = makeClient({});
    const { unmount } = render(<TaskDetailScreen client={client} me={{ id: 5, nickname: '路人' } as never}
      task={TASK({ on_behalf: true, recipient_label: '', onsite_contact: '' })} onBack={() => {}} onChanged={async () => {}} />);
    expect(screen.getByLabelText('服务对象').props.children.join('')).toContain('成交后可见');
    unmount();
    render(<TaskDetailScreen client={client} me={{ id: 2, nickname: '师傅' } as never}
      task={TASK({ on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨 139', executor_id: 2 })} onBack={() => {}} onChanged={async () => {}} />);
    const text = screen.getByLabelText('服务对象').props.children.join('');
    expect(text).toContain('服务对象「我妈」');
    expect(text).toContain('到场联系 王阿姨 139');
  });
});

describe('SCN-123 App 发单后改服务对象', () => {
  it('发单人勾「已经问过本人」后保存，请求带上新称呼与联系方式；保存后刷新', async () => {
    const calls: Call[] = [];
    const changed = jest.fn();
    render(<RecipientEditorBlock client={makeClient({ 'PATCH /tasks/60/recipient': TASK({}) }, calls)}
                                 task={TASK({ on_behalf: true, recipient_label: '我妈', onsite_contact: '王阿姨' })} onChanged={changed} />);
    fireEvent.press(screen.getByText('改服务对象'));
    fireEvent.changeText(screen.getByLabelText('服务对象怎么称呼'), '我爸');
    fireEvent.press(screen.getByLabelText('已经问过本人'));
    fireEvent.press(screen.getByText('保存'));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ recipient_label: '我爸', onsite_contact: '王阿姨', recipient_consented: true });
    expect(screen.getByText('已改好，接单的人会收到通知')).toBeTruthy();
  });

  it('入口只给发单人、只在单没结束时', () => {
    expect(canChangeRecipient(TASK({ on_behalf: true }), 9)).toBe(true);
    expect(canChangeRecipient(TASK({ on_behalf: true }), 2)).toBe(false);
    expect(canChangeRecipient(TASK({ on_behalf: false }), 9)).toBe(false);
    for (const status of ['completed', 'cancelled', 'disputed'] as const) expect(canChangeRecipient(TASK({ on_behalf: true, status }), 9)).toBe(false);
  });
});

describe('SCN-144 App 服务对象是未成年人', () => {
  it('勾上选监护人在场并确认，请求带这三项', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK({}) }, calls)} onDone={done} />);
    expect(screen.queryByText('○ 监护人在场')).toBeNull();
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '钢琴陪练');
    fireEvent.press(screen.getByLabelText('服务对象是未成年人'));
    fireEvent.press(screen.getByText('○ 监护人在场'));
    fireEvent.press(screen.getByLabelText('我是监护人或已经监护人同意'));
    fireEvent.press(screen.getByText(/^○ 著作权转让给我/));
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).toMatchObject(
      { minor_involved: true, guardian_mode: 'guardian_present', guardian_consented: true });
  });
});

describe('SCN-144 App 详情页写明未成年人服务的安排', () => {
  it('安排方式与要求的证明都写上', () => {
    render(<TaskDetailScreen client={makeClient({}, [])} me={{ id: 5, nickname: '路人' } as never}
      task={TASK({ minor_involved: true, guardian_mode: 'public_place' })} onBack={() => {}} onChanged={async () => {}} />);
    expect(screen.getByLabelText('未成年人服务').props.children).toBe('服务对象是未成年人 · 在公开场所 · 接单要有平台审核通过的无犯罪记录证明');
  });
});
