// SCN-120 App 上的上门回报（176 号 spec）：发布页带上门次数与清单；详情页接单人勾清单交回报，双方看到漏了什么。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { PublishScreen, TaskDetailScreen } from './App';
import { VisitsBlock, hasVisits } from './visits';

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
const TASK = (extra: Partial<Task> = {}) => ({ id: 70, creator_id: 9, executor_id: 2, parent_id: null, depends_on: [], title: '上门喂猫 7 天',
  description: '', category: '宠物照护', task_type: 'service', required_skills: [], budget_cents: 50000, pricing: 'fixed',
  ip_assignment: 'assign', bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '',
  status: 'in_progress', deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z',
  visits_planned: 14, visit_checklist: ['喂食', '换水', '铲屎'], ...extra }) as Task;
const VISITS = { task_id: 70, planned: 14, checklist: ['喂食', '换水', '铲屎'], reported: 1, missed_total: 1,
  visits: [{ n: 1, id: 5, created_at: '2030-01-05T02:00:00Z', done: ['喂食', '铲屎'], missed: ['换水'], note: '猫很精神', images: [] }] };

describe('SCN-120 App 上门回报', () => {
  it('发布页：上门次数与清单带进请求', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient({ 'POST /tasks': TASK() }, calls)} onDone={done} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '喂猫');
    fireEvent.changeText(screen.getByLabelText('要上门几次'), '14');
    fireEvent.changeText(screen.getByLabelText('每次要做的事'), '喂食、换水，铲屎');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).toMatchObject(
      { visits_planned: 14, visit_checklist: ['喂食', '换水', '铲屎'] });
  });

  it('详情页：接单人看到漏了什么，勾清单交这次的回报', async () => {
    const calls: Call[] = [];
    const client = makeClient({ 'GET /tasks/70/visits': VISITS, 'POST /tasks/70/visits': { n: 2, id: 6, done: ['喂食'], missed: [] } }, calls);
    render(<TaskDetailScreen client={client} me={{ id: 2, nickname: '宠托师' } as never} task={TASK()} onBack={() => {}} onChanged={async () => {}} />);
    expect(await screen.findByText('上门回报 · 1/14 次')).toBeTruthy();
    expect(screen.getByText('一共有 1 项没做（见下面每次的记录）')).toBeTruthy();
    fireEvent.press(screen.getByLabelText('做了：喂食'));
    fireEvent.press(screen.getByLabelText('做了：换水'));
    fireEvent.changeText(screen.getByLabelText('这次的备注'), '一切正常');
    fireEvent.press(screen.getByText('交这次的上门回报'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/70/visits')?.body).toEqual(
      { done: ['喂食', '换水'], note: '一切正常', images: [] }));
  });

  it('发单人只看不交；没写次数和清单的单没有这一块', async () => {
    const client = makeClient({ 'GET /tasks/70/visits': VISITS });
    const { unmount } = render(<TaskDetailScreen client={client} me={{ id: 9, nickname: '主人' } as never} task={TASK()} onBack={() => {}} onChanged={async () => {}} />);
    expect(await screen.findByText('上门回报 · 1/14 次')).toBeTruthy();
    expect(screen.queryByText('交这次的上门回报')).toBeNull();
    unmount();
    expect(hasVisits({ visits_planned: 0, visit_checklist: [] })).toBe(false);
    expect(hasVisits({ visits_planned: 3 })).toBe(true);
    expect(hasVisits({ visit_checklist: ['喂食'] })).toBe(true);
  });
});

describe('SCN-124 App 上门回报带上到场打卡', () => {
  it('勾了「带上当前位置」才取定位并随回报交上去；列表写明到场与距离', async () => {
    const calls: Call[] = [];
    const v = { ...VISITS, visits: [{ ...VISITS.visits[0], at_site_m: 35 }] };
    const client = makeClient({ 'GET /tasks/70/visits': v, 'POST /tasks/70/visits': { n: 2, id: 6, done: [], missed: [], at_site_m: 12 } }, calls);
    const locate = jest.fn(async () => ({ lat: 31.23, lng: 121.47 }));
    render(<VisitsBlock client={client} task={TASK({ lat: 31.23, lng: 121.47 })} isExecutor locate={locate} />);
    expect(await screen.findByText(/· 到场（距 35 米）/)).toBeTruthy();
    fireEvent.changeText(screen.getByLabelText('这次的备注'), '到了');
    fireEvent.press(screen.getByText('交这次的上门回报'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST').length).toBe(1));
    expect(locate).not.toHaveBeenCalled();
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ done: [], note: '到了', images: [] });
    fireEvent.press(screen.getByLabelText('带上当前位置'));
    fireEvent.changeText(screen.getByLabelText('这次的备注'), '又到了');
    fireEvent.press(screen.getByText('交这次的上门回报'));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST').length).toBe(2));
    expect(calls.filter((c) => c.method === 'POST')[1].body).toEqual({ done: [], note: '又到了', images: [], lat: 31.23, lng: 121.47 });
  });

  it('线上任务或没有定位能力时不显示这一项', async () => {
    const client = makeClient({ 'GET /tasks/70/visits': VISITS });
    const { unmount } = render(<VisitsBlock client={client} task={TASK({ is_remote: true })} isExecutor locate={async () => ({ lat: 1, lng: 1 })} />);
    expect(await screen.findByText('交这次的上门回报')).toBeTruthy();
    expect(screen.queryByLabelText('带上当前位置')).toBeNull();
    unmount();
    render(<VisitsBlock client={client} task={TASK()} isExecutor />);
    expect(await screen.findByText('交这次的上门回报')).toBeTruthy();
    expect(screen.queryByLabelText('带上当前位置')).toBeNull();
  });
});
