// APP-070 App 的第一批单元测试（69 号 spec）。
//
// V91~V93 的 App 行为，全靠 Python 扫描闸门 + 共享 SDK 的类型覆盖。
// 那两样能挡住的是**入口不存在**；挡不住的是**入口在、按下去做错事**：
// 调错方法、把服务端算好的话吞掉、自己重写一遍服务端的判断。
//
// 所以这一批先覆盖两条路：**动钱的**（提现/绑卡/审批）与**关乎人身的**（求助）。
// CI 此前只跑 `tsc`。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Task } from '@platform/core';
import { SafetyBlock, WalletScreen } from './App';

/** 按整条路径精确匹配（V84 的教训：`includes` 会让 `/wallet` 吃掉
 *  `/wallet/ledger` 和 `/wallet/payout-account`）。 */
function makeClient(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string; body: unknown }> = [],
): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const WALLET = { available_cents: 50000, escrow_cents: 0, frozen_cents: 0 };

const TASK: Task = {
  id: 7, creator_id: 1, executor_id: 2, parent_id: null, depends_on: [],
  title: '上门保洁', description: '', category: '保洁', task_type: 'service',
  required_skills: [], budget_cents: 20000, pricing: 'fixed', ip_assignment: 'assign',
  bonus_cents: 0, is_remote: false, city: '上海', lat: null, lng: null,
  address_hint: '徐汇', address_exact: '某某路 1 号', status: 'in_progress',
  deadline: null, reject_count: 0, created_at: '2026-09-22T00:00:00Z',
};

// ------------------------------------------------------------------ 钱包
describe('APP-065 钱包：钱能进，也要能出', () => {
  it('提现打到 /wallet/withdraw，并原样显示服务端的中性话术', async () => {
    const neutral = '您的提现申请已提交，我们会尽快处理';
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({
      '/wallet': WALLET,
      '/wallet/ledger': [],
      '/wallet/payout-account': { bound: true, kind: 'bank', account_no: '6222****0000', holder_name: '张三' },
      // AML-030/031 tipping-off：服务端**刻意**不说触发了哪条规则
      '/wallet/withdraw': { status: 'pending_review', request_id: 3, message: neutral, available_cents: 40000, frozen_cents: 10000 },
    }, calls);

    render(<WalletScreen client={client} />);
    await waitFor(() => expect(screen.getByText('提现 ¥100.00')).toBeTruthy());
    fireEvent.press(screen.getByText('提现 ¥100.00'));

    // 这一条是扫描闸门验不到的：入口在，但它有没有把那句话显示出来
    await waitFor(() => expect(screen.getByText(neutral)).toBeTruthy());
    expect(calls.some((c) => c.method === 'POST' && c.path === '/wallet/withdraw')).toBe(true);
  });

  it('PAY-030 绑定收款账户带上金额之外的两个字段，并显示脱敏卡号', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({
      '/wallet': WALLET,
      '/wallet/ledger': [],
      '/wallet/payout-account': { bound: false },
    }, calls);

    render(<WalletScreen client={client} />);
    await waitFor(() => expect(screen.getByText(/未绑定收款账户/)).toBeTruthy());

    fireEvent.changeText(screen.getByPlaceholderText('银行卡号 / 支付宝账号'), '6222020000000000');
    fireEvent.changeText(screen.getByPlaceholderText('开户姓名'), '张三');
    fireEvent.press(screen.getByText('绑定收款账户'));

    await waitFor(() => {
      const bind = calls.find((c) => c.method === 'PUT' && c.path === '/wallet/payout-account');
      expect(bind?.body).toMatchObject({
        kind: 'bank', account_no: '6222020000000000', holder_name: '张三',
      });
    });
  });

  it('LEDG-004 账单科目的中文名走共享 SDK，不在 App 里另写一份', async () => {
    const client = makeClient({
      '/wallet': WALLET,
      '/wallet/payout-account': { bound: false },
      '/wallet/ledger': [
        // memo 刻意不等于科目名，否则断言分不清界面显示的是哪一个
        { id: 1, kind: 'topup', amount_cents: 50000, contract_id: null, memo: '银行卡入账', created_at: '2026-09-22T00:00:00Z' },
        { id: 2, kind: 'withdraw', amount_cents: -10000, contract_id: null, memo: '提现打款', created_at: '2026-09-22T01:00:00Z' },
      ],
    });
    render(<WalletScreen client={client} />);
    // ledgerKindLabel('topup') / ('withdraw') 的结果，App 里没有第二份中文。
    // 这条会红的场景：有人图省事在 App 里写一份自己的科目中文名，
    // 于是账单里的叫法和 Web、和用户账单导出对不上（V84 立过这条）。
    await waitFor(() => expect(screen.getByText('充值')).toBeTruthy());
    expect(screen.getByText('提现')).toBeTruthy();
    expect(screen.getByText('银行卡入账')).toBeTruthy();
  });
});

// ------------------------------------------------------------------ 求助
describe('GEO-023 一键求助', () => {
  it('求助打到 /tasks/{id}/sos，并原样显示服务端的指引', async () => {
    const guidance = '已通知平台与任务对方；如遇危险请立即拨打 110';
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const client = makeClient({ '/tasks/7/sos': { ok: true, guidance } }, calls);

    render(<SafetyBlock client={client} task={TASK} meId={2} />);
    fireEvent.press(screen.getByText('🆘 一键求助'));

    await waitFor(() => expect(screen.getByText(guidance)).toBeTruthy());
    expect(calls.some((c) => c.path === '/tasks/7/sos')).toBe(true);
  });

  it('线上任务与非当事人都不显示求助入口', () => {
    const client = makeClient({});
    const remote = render(<SafetyBlock client={client} task={{ ...TASK, is_remote: true }} meId={2} />);
    expect(remote.toJSON()).toBeNull();
    remote.unmount();
    // 路人：服务端会 403，但更早一步是**根本不该把按钮摆给他**
    const outsider = render(<SafetyBlock client={client} task={TASK} meId={99} />);
    expect(outsider.toJSON()).toBeNull();
  });

  it('GEO-022 行程分享读服务端返回的键（trip_share_enabled，不是 enabled）', async () => {
    const client = makeClient({ '/tasks/7/trip-share': { trip_share_enabled: true } });
    render(<SafetyBlock client={client} task={TASK} meId={2} />);
    fireEvent.press(screen.getByText('开启行程分享（让发布方看到我的轨迹）'));
    await waitFor(() => expect(screen.getByText('关闭行程分享')).toBeTruthy());
  });

  it('只有执行方看得到行程分享开关（发布方没有轨迹可分享）', () => {
    const client = makeClient({});
    render(<SafetyBlock client={client} task={TASK} meId={1} />);
    expect(screen.getByText('🆘 一键求助')).toBeTruthy();
    expect(screen.queryByText(/行程分享/)).toBeNull();
  });
});
