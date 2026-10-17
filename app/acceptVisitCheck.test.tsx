// SCN-125 App 上验收前的上门回报提醒（179 号 spec）：少回报或有漏项时第一下只摊开差距，第二下才验收；齐了直接验收。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Me, type Task } from '@platform/core';
import { TaskDetailScreen } from './App';

type Call = { method: string; path: string };
function makeClient(routes: Record<string, unknown>, calls: Call[] = []) {
  const fetchImpl = (async (url: string, init?: { method?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const TASK = { id: 7, creator_id: 1, executor_id: 2, parent_id: null, depends_on: [], title: '上门喂猫', description: '',
  category: '宠物照护', task_type: 'service', required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null, address_hint: '', address_exact: '', status: 'pending_acceptance',
  deadline: null, reject_count: 0, created_at: '2026-10-16T00:00:00Z', visits_planned: 14, visit_checklist: ['喂食'] } as Task;
const REQUESTER = { id: 1, nickname: '主人' } as unknown as Me;
const CONTRACT = { id: 3, task_id: 7, requester_id: 1, executor_id: 2, amount_cents: 20000, released_cents: 0, fee_bps: 800, terms: '',
  status: 'funded', signed_by_requester: true, signed_by_executor: true, frozen: false, version: 1, deposit_cents: 0,
  deposit_status: 'none', milestones: [{ idx: 1, title: '全部', amount_cents: 20000, status: 'pending' }] };
const visits = (reported: number, missed: number) => ({ task_id: 7, planned: 14, checklist: ['喂食'], reported, missed_total: missed, visits: [] });

describe('SCN-125 App 验收前提醒', () => {
  it('少回报：第一下只摊开差距、不放款；第二下才验收', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/contracts/by-task/7': CONTRACT, '/tasks/7/visits': visits(12, 1) }, calls);
    render(<TaskDetailScreen client={client} me={REQUESTER} task={TASK} onBack={() => {}} onChanged={async () => {}} />);
    await screen.findByText('上门回报 · 12/14 次');   // 等异步加载都落定再按（按钮节点会随加载重画）
    fireEvent.press(screen.getByText('验收通过（放款）'));
    expect(await screen.findByText('计划上门 14 次，回报了 12 次；回报里一共有 1 项没做。验收前可以先问问接单的人。')).toBeTruthy();
    expect(calls.some((c) => c.path === '/tasks/7/accept-delivery')).toBe(false);
    fireEvent.press(screen.getByText('仍然验收通过（放款）'));
    await waitFor(() => expect(calls.some((c) => c.path === '/tasks/7/accept-delivery')).toBe(true));
  });

  it('都齐了：一下就验收', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/contracts/by-task/7': CONTRACT, '/tasks/7/visits': visits(14, 0) }, calls);
    render(<TaskDetailScreen client={client} me={REQUESTER} task={TASK} onBack={() => {}} onChanged={async () => {}} />);
    await screen.findByText('上门回报 · 14/14 次');
    fireEvent.press(screen.getByText('验收通过（放款）'));
    await waitFor(() => expect(calls.some((c) => c.path === '/tasks/7/accept-delivery')).toBe(true));
  });
});

describe('SCN-136 App 验收确认里写明到场次数', () => {
  it('回报都齐了但只有一次到场：第一下摊开，回报块里也写明', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/contracts/by-task/7': CONTRACT, '/tasks/7/visits': { ...visits(14, 0), at_site: 1 } }, calls);
    render(<TaskDetailScreen client={client} me={REQUESTER} task={TASK} onBack={() => {}} onChanged={async () => {}} />);
    expect(await screen.findByLabelText('到场次数')).toBeTruthy();
    fireEvent.press(screen.getByText('验收通过（放款）'));
    expect(await screen.findByText('14 次回报里有 1 次带了到场打卡。验收前可以先问问接单的人。')).toBeTruthy();
    expect(calls.some((c) => c.path === '/tasks/7/accept-delivery')).toBe(false);
  });
});
