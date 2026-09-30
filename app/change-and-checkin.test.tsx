// SC-007 / GEO-021 变更单与到场打卡在 App 上的行为（70 号 spec）。
//
// 扫描闸门能证明入口存在。这里验的是闸门验不到的那些：
// 提案有没有把事由带上、`can_decide` 有没有被客户端重算、
// 超距时服务端算出的**实际距离**有没有显示出来。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Contract, type Task } from '@platform/core';
import { ChangeOrderBlock, SafetyBlock } from './App';

function makeClient(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string; body: unknown }> = [],
  errors: Record<string, { status: number; code: string; message: string }> = {},
): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const err = errors[path];
    if (err) {
      return {
        ok: false, status: err.status,
        text: async () => JSON.stringify({ detail: { code: err.code, message: err.message } }),
      };
    }
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const TASK: Task = {
  id: 7, creator_id: 1, executor_id: 2, parent_id: null, depends_on: [],
  title: '上门保洁', description: '', category: '保洁', task_type: 'service',
  required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null,
  address_hint: '徐汇', address_exact: '某某路 1 号', status: 'in_progress',
  deadline: null, reject_count: 0, created_at: '2026-09-24T00:00:00Z',
};

describe('GEO-021 到场打卡', () => {
  it('打卡成功后显示服务端算出的距离', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({ '/tasks/7/checkin': { ok: true, distance_m: 42 } }, calls);
    render(<SafetyBlock client={client} task={TASK} meId={2} />);
    fireEvent.press(screen.getByText('到场打卡'));
    await waitFor(() => expect(screen.getByText(/距任务地点 42 米/)).toBeTruthy());
    expect(calls.some((c) => c.path === '/tasks/7/checkin')).toBe(true);
  });

  it('超距时把服务端给的实际距离原样显示出来', async () => {
    // 只说「超出范围」的话，他不知道是差 50 米还是差 5 公里——
    // 服务端把实际距离写在消息里，就是为了让他能判断要不要再走两步
    const client = makeClient({}, [], {
      '/tasks/7/checkin': { status: 400, code: 'too_far', message: '距任务地点 4205 米，超出打卡范围' },
    });
    render(<SafetyBlock client={client} task={TASK} meId={2} />);
    fireEvent.press(screen.getByText('到场打卡'));
    await waitFor(() => expect(screen.getByText(/4205 米/)).toBeTruthy());
  });

  it('只有执行方能打卡（发布方不到场）', () => {
    const client = makeClient({});
    render(<SafetyBlock client={client} task={TASK} meId={1} />);
    expect(screen.queryByText('到场打卡')).toBeNull();
  });
});

// ------------------------------------------------------------------ 变更单
const CONTRACT: Contract = {
  id: 3, task_id: 7, requester_id: 1, executor_id: 2, amount_cents: 20000,
  released_cents: 0, fee_bps: 800, deposit_cents: 0, deposit_status: 'none',
  terms: '合同条款', status: 'funded', signed_by_requester: true,
  signed_by_executor: true, frozen: false, version: 1,
};

describe('SC-007 变更单', () => {
  it('提案把金额与事由都发上去（事由是对方判断的依据）', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({ '/contracts/3/change-orders': [] }, calls);
    render(<ChangeOrderBlock client={client} contract={CONTRACT}
                                   onChanged={async () => undefined} />);
    await waitFor(() => expect(screen.getByText(/没有变更单/)).toBeTruthy());

    fireEvent.changeText(screen.getByPlaceholderText('新金额（元）'), '300');
    fireEvent.changeText(screen.getByPlaceholderText('事由（对方会看到）'), '加了两个房间');
    fireEvent.press(screen.getByText('提出变更'));

    await waitFor(() => {
      const c = calls.find((x) => x.method === 'POST' && x.path === '/contracts/3/change-orders');
      expect(c?.body).toMatchObject({ new_amount_cents: 30000, reason: '加了两个房间' });
    });
  });

  it('can_decide=false 时不画接受/拒绝按钮（提案人自己不能接受）', async () => {
    const client = makeClient({
      '/contracts/3/change-orders': [{
        id: 1, contract_id: 3, proposed_by: 2, new_amount_cents: 30000,
        reason: '加了两个房间', status: 'pending',
        created_at: '2026-09-24T00:00:00Z', can_decide: false,
      }],
    });
    render(<ChangeOrderBlock client={client} contract={CONTRACT}
                                   onChanged={async () => undefined} />);
    await waitFor(() => expect(screen.getByText('改为 ¥300.00')).toBeTruthy());
    expect(screen.queryByText('接受')).toBeNull();
    expect(screen.queryByText('拒绝')).toBeNull();
    // 已有待处理的变更单时不再给「提出变更」——服务端也会拒（change_pending）
    expect(screen.queryByText('提出变更')).toBeNull();
  });

  it('can_decide=true 时接受打到 accept 端点', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({
      '/contracts/3/change-orders': [{
        id: 1, contract_id: 3, proposed_by: 1, new_amount_cents: 30000,
        reason: '加了两个房间', status: 'pending',
        created_at: '2026-09-24T00:00:00Z', can_decide: true,
      }],
      '/contracts/3/change-orders/1/accept': CONTRACT,
    }, calls);
    render(<ChangeOrderBlock client={client} contract={CONTRACT}
                                   onChanged={async () => undefined} />);
    await waitFor(() => expect(screen.getByText('接受')).toBeTruthy());
    fireEvent.press(screen.getByText('接受'));
    await waitFor(() => expect(
      calls.some((c) => c.path === '/contracts/3/change-orders/1/accept'),
    ).toBe(true));
  });
});
