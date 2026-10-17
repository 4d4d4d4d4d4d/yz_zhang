// PAY-040 提现复核台。管理后台里此前**没有这一条**——
// V82 的豁免表写着「提现人审是风控岗位的动作，在管理后台做」，
// 而没有任何东西核对过那个地方是否真的有它。V91 把提现接通之后，
// 大额进人审的钱就冻在用户账上，没有任何界面能放行。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = {
  id: 1, phone: '138****0001', nickname: '风控', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r1',
};

const METRICS = {
  total_users: 10, verified_users: 8, total_tasks: 20, published_tasks: 3,
  completed_tasks: 12, closed_loop_rate: 0.6, dispute_count: 1,
  gmv_cents: 1000000, fee_income_cents: 80000,
};

const ROW = {
  id: 5, user_id: 9, amount_cents: 3000000, status: 'pending',
  created_at: '2026-09-27T00:00:00Z', nickname: '提现的人', is_verified: true,
  registered_at: '2026-09-01T00:00:00Z', withdrawn_total_cents: 500000,
  flags: [{ pattern: 'structuring', detail: '24 小时内 3 笔合计 ¥29000', amount_cents: 2900000 }],
};

function makeClient(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string }> = [],
): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path });
    const hit = Object.keys(routes).find((k) => k === full)
      ?? Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

function openAdmin(
  routes: Record<string, unknown> = {},
  calls: Array<{ method: string; path: string }> = [],
) {
  localStorage.setItem('token', 'tok');
  const client = makeClient({
    '/users/me': ADMIN,
    '/admin/metrics': METRICS,
    '/admin/reports': [],
    '/admin/users': [],
    '/wallet/withdraw-requests?status=pending': [ROW],
    '/wallet/withdraw-requests?status=awaiting_second': [],
    '/admin/aml/activities': { items: [], note: '' },
    ...routes,
  }, calls);
  render(
    <MemoryRouter initialEntries={['/admin']}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

describe('PAY-040 提现复核台', () => {
  it('列出待复核，并说清这些钱正冻在用户账上', async () => {
    openAdmin();
    await waitFor(() => expect(screen.getByText('提现复核（1）')).toBeTruthy());
    expect(screen.getByText(/正冻在用户账上等人放行，合计 ¥30000.00/)).toBeTruthy();
    // 金额在行里也出现一次（合计与行金额同值，所以按 testid 取行）
    expect(screen.getByTestId('wd-5').textContent).toContain('¥30000.00');
  });

  it('把做判断需要的东西摆出来：实名、注册时间、历史提现、命中依据', async () => {
    openAdmin();
    await waitFor(() => expect(screen.getByTestId('wd-5')).toBeTruthy());
    const row = screen.getByTestId('wd-5').textContent ?? '';
    expect(row).toContain('提现的人');
    expect(row).toContain('已实名');
    expect(row).toContain('历史已提现 ¥5000.00');
    // 命中依据要带**具体数值**：只写「疑似拆分」，复核的人无从判断
    expect(screen.getByTestId('wd-flags-5').textContent).toContain('24 小时内 3 笔合计 ¥29000');
  });

  it('批准打到 approve 端点', async () => {
    const calls = openAdmin({ '/wallet/withdraw-requests/5/approve': { status: 'approved', amount_cents: 3000000 } });
    await waitFor(() => expect(screen.getByText('批准打款')).toBeTruthy());
    fireEvent.click(screen.getByText('批准打款'));
    await waitFor(() => expect(
      calls.some((c) => c.method === 'POST' && c.path === '/wallet/withdraw-requests/5/approve'),
    ).toBe(true));
  });

  it('驳回打到 reject 端点', async () => {
    const calls = openAdmin({ '/wallet/withdraw-requests/5/reject': { status: 'rejected', amount_cents: 3000000 } });
    await waitFor(() => expect(screen.getByText('驳回退回')).toBeTruthy());
    fireEvent.click(screen.getByText('驳回退回'));
    await waitFor(() => expect(
      calls.some((c) => c.method === 'POST' && c.path === '/wallet/withdraw-requests/5/reject'),
    ).toBe(true));
  });

  it('AML-040 可疑活动为空时不占地方，有则显示服务端那句保密提示', async () => {
    openAdmin({
      '/admin/aml/activities': {
        items: [{
          id: 2, user_id: 9, pattern: 'fast_in_out', pattern_label: '快进快出',
          detail: '入账 2 小时内提现 ¥28000', amount_cents: 2800000,
          ref_type: 'withdraw_request', ref_id: 5, status: 'pending',
          review_note: '', at: '2026-09-27T00:00:00Z',
        }],
        note: '本清单及其内容属反洗钱工作信息，依《反洗钱法》第五条应予保密',
      },
    });
    await waitFor(() => expect(screen.getByText('可疑活动待复核（1）')).toBeTruthy());
    expect(screen.getByText('快进快出')).toBeTruthy();
    // 这句提示原样来自服务端：平台不自动对外报送，报送与否由合规官判断
    expect(screen.getByText(/依《反洗钱法》第五条应予保密/)).toBeTruthy();
  });
  it('PAY-042 等二次确认的申请要出现在队列里，并说清钱还冻着', async () => {
    // 只看 pending 的话，**等二次确认的那些会从界面上消失**——
    // 而那正是钱冻着等人的状态，消失了就没人会去处理
    openAdmin({
      '/wallet/withdraw-requests?status=pending': [],
      '/wallet/withdraw-requests?status=awaiting_second': [
        { ...ROW, id: 6, status: 'awaiting_second', first_approved_by: 3 },
      ],
    });
    await waitFor(() => expect(screen.getByTestId('wd-first-6')).toBeTruthy());
    const line = screen.getByTestId('wd-first-6').textContent ?? '';
    expect(line).toContain('#3');
    expect(line).toContain('钱仍在冻结中');
    // 按钮文案跟着状态变：第二个人要知道自己在确认别人的意见，不是初审
    expect(screen.getByText('二次确认并打款')).toBeTruthy();
  });
});

