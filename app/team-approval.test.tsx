// APP-070 团队审批在 App 上的行为（69 号 spec）。
//
// 扫描闸门能证明「App 上有 decideTeamSpend 的入口」；它证明不了的是：
// 按钮摆给了谁、驳回时那段**服务端强制要写**的理由有没有真的传上去。
// 这两条错了，界面看上去照样正常。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SubScreenHost } from './TeamCoopDev';

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

const TEAM = {
  id: 5, name: '某某科技', company_name: '', tax_number: '', verify_status: 'none',
  verify_reason: '', active: true, my_role: 'owner', balance_cents: 500000,
  my_spend_limit_cents: 100000, my_month_spent_cents: 0,
  monthly_budget_cents: 300000, month_spent_cents: 50000,
  invoice_block: '企业信息未核验，暂不能开企业抬头发票',
  members: [],
};

function spend(overrides: Record<string, unknown> = {}) {
  return {
    id: 11, requester_id: 9, amount_cents: 200000, purpose: '采购一批物料',
    status: 'pending', task_id: null, decided_by: null, decision_reason: '',
    created_at: '2026-09-22T00:00:00Z', can_decide: true, ...overrides,
  };
}

function open(routes: Record<string, unknown>, calls: Array<{ method: string; path: string; body: unknown }> = []) {
  const client = makeClient({ '/teams/mine': [TEAM], '/teams/5': TEAM, ...routes }, calls);
  render(<SubScreenHost client={client} screen="teams" onBack={() => undefined} />);
  return calls;
}

describe('APP-069 团队支出审批', () => {
  it('驳回必须带上理由，并且理由真的发了上去', async () => {
    const calls = open({ '/teams/5/spends': [spend()] });
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));

    await waitFor(() => expect(screen.getByText('驳回')).toBeTruthy());
    fireEvent.press(screen.getByText('驳回'));

    const reason = '这批物料上月刚采购过，先用库存';
    fireEvent.changeText(screen.getByPlaceholderText('驳回理由（必填，对方会收到）'), reason);
    fireEvent.press(screen.getByText('确认驳回'));

    await waitFor(() => {
      const c = calls.find((x) => x.path === '/teams/5/spends/11/decide');
      // 服务端强制写理由（reason_required），而这段话的全部价值
      // 在于被驳回的人读到它——传丢了，强制就只剩一道手续
      expect(c?.body).toMatchObject({ approve: false, reason });
    });
  });

  it('UI-075 审批按钮读服务端的 can_decide，客户端不自己重算', async () => {
    // 自己批自己不算审批（TEAM-021）。服务端已经算好了 can_decide=false，
    // 客户端**再写一遍这个判断就是第二份实现，而第二份必然抄漏**。
    open({ '/teams/5/spends': [spend({ can_decide: false })] });
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));

    await waitFor(() => expect(screen.getByText(/采购一批物料/)).toBeTruthy());
    expect(screen.queryByText('批准')).toBeNull();
    expect(screen.queryByText('驳回')).toBeNull();
  });

  it('TEAM-061 已驳回的申请，把那段理由显示出来', async () => {
    const reason = '预算池本月只剩 ¥500';
    open({ '/teams/5/spends': [spend({ status: 'rejected', can_decide: false, decision_reason: reason })] });
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));
    await waitFor(() => expect(screen.getByText(new RegExp(reason))).toBeTruthy());
  });

  it('TEAM-050/052 额度与预算池按「月度累计」说清楚，别让人以为是单笔', async () => {
    open({ '/teams/5/spends': [] });
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));
    await waitFor(() => expect(screen.getByText(/我的本月额度/)).toBeTruthy());
    expect(screen.getByText(/团队本月预算池 ¥3000.00，已用 ¥500.00，剩余 ¥2500.00/)).toBeTruthy();
  });

  it('UI-075 开票能力读服务端的 invoice_block，理由原样显示', async () => {
    open({ '/teams/5/spends': [] });
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));
    await waitFor(() => expect(screen.getByText(TEAM.invoice_block)).toBeTruthy());
  });
});
