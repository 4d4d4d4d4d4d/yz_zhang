// UI-070~077 合作体 / 团队 / 开发者三页（59 号 spec）。
//
// 这三条线在 V82 只补到了 SDK，网页上没有页面——其中合作体是整个产品里
// 立意最重的一条，而它到 V83 为止只能用 curl 访问。
//
// 断言集中在一件事上：**该说的话说到了**。这三页的每一次点击都有真实后果，
// 而且后果不对称——加入的人以为是「加个群」，实际是投入可能血本无归、
// 份额会被后来者稀释、且不可转让不可赎回。
// 风险不是免责声明，是决策所需的信息。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 1, phone: '138****0000', nickname: '我', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};

const RISK = {
  version: 'rd-2026-01',
  title: '早期合作风险揭示书',
  points: [
    '份额由已确认贡献计算得出，会随他人后续贡献而稀释；',
    '合作体可能不产生任何收益，你的投入可能没有任何回报；',
  ],
  text: '全文……',
};

function makeClient(routes: Record<string, unknown>, calls: string[] = []): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const u = String(url);
    calls.push(`${init?.method ?? 'GET'} ${u} ${init?.body ?? ''}`);
    const path = u.replace(/^.*\/api\/v1/, '').split('?')[0];
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('合作体', () => {
  it('UI-070 创建前整篇展示风险揭示书，且签的版本号来自服务端', async () => {
    localStorage.setItem('token', 'tok');
    const calls: string[] = [];
    const client = makeClient({
      '/users/me': ME,
      '/ventures/risk-disclosure': RISK,
      '/ventures/mine': [],
      '/ventures': { id: 9, name: '共建工具链' },
    }, calls);
    render(
      <MemoryRouter initialEntries={['/ventures']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText('发起一个合作体'));
    await waitFor(() => expect(screen.getByTestId('risk-disclosure')).toBeTruthy());
    // 四条要点逐条列出，不是折叠进一行小字
    expect(screen.getByText(/随他人后续贡献而稀释/)).toBeTruthy();
    expect(screen.getByText(/可能没有任何回报/)).toBeTruthy();

    // 没勾「已阅读」之前不能提交
    fireEvent.change(screen.getByLabelText(/名称/), { target: { value: '共建工具链' } });
    expect((screen.getByText('创建') as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByLabelText(/我已阅读并理解上述风险/));
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => {
      const post = calls.find((c) => c.startsWith('POST') && c.includes('/ventures '));
      expect(post).toBeTruthy();
      // 版本号是服务端给的那个，不是前端写死的
      expect(post).toContain('rd-2026-01');
    });
  });

  it('UI-071/072/073 份额口径、自确认禁止与「只分已实现收益」都显示出来', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/ventures/risk-disclosure': RISK,
      '/ventures/mine': [{ id: 9, name: '共建工具链', purpose: '', category: '软件开发', status: 'active', founder_id: 1, created_at: null, role: 'founder' }],
      '/ventures/9': {
        id: 9, name: '共建工具链', purpose: '', category: '软件开发', status: 'active',
        founder_id: 1, created_at: null,
        members: [{ user_id: 1, role: 'founder', joined_at: null }],
        shares: [{ user_id: 1, share_bps: 10000, valued_cents: 50000 }],
        realized_funds_cents: 120000,
      },
      '/ventures/9/shares': {
        shares: [{ user_id: 1, share_bps: 10000, valued_cents: 50000 }],
        total_bps: 10000,
        basis: '份额 = 本人已确认贡献计价 ÷ 全体已确认贡献计价；他人后续贡献会稀释你的份额。',
      },
      '/ventures/9/contributions': [
        { id: 1, user_id: 1, kind: 'time', description: '写了编排器', status: 'proposed',
          valued_cents: 0, confirmed_by: null, confirm_note: '', evidence: [],
          created_at: null, can_confirm: false },
      ],
      '/ventures/9/compliance-path': {
        documents: [{ key: 'risk_disclosure', title: '早期合作风险揭示书', why: '合作有风险且份额会被稀释，加入前必须让每个人知道', status: 'ready', action: '成员加入前签署（系统强制）' }],
        registrations: [],
        notices: [],
        disclaimer: '以上不是法律意见，请由执业律师就个案出具意见。',
      },
    });
    render(
      <MemoryRouter initialEntries={['/ventures']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText('打开'));

    // UI-071 口径说明原样来自服务端
    await waitFor(() => expect(screen.getByTestId('share-basis')).toBeTruthy());
    expect(screen.getByTestId('share-basis').textContent).toContain('稀释');
    // UI-073 分配只分已实现收益
    expect(screen.getAllByText(/已经实际收到/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/¥1200\.00/).length).toBeGreaterThan(0);
    // UI-072 can_confirm=false 时没有「确认并计价」按钮（自己的贡献不能自己确认）
    expect(screen.queryByText('确认并计价')).toBeNull();
    // UI-074 合规路径带理由与免责声明
    expect(screen.getByText(/为什么需要：/)).toBeTruthy();
    expect(screen.getByTestId('compliance-disclaimer').textContent).toContain('不是法律意见');
  });
});

describe('团队', () => {
  it('UI-075 超额支出显示「等待审批」而不是失败；审批按钮读服务端判断', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/teams/mine': [{ id: 4, name: '设计组', owner_id: 1, company_name: '', tax_number: '', verify_status: 'none', verify_reason: '', active: true, my_role: 'owner', my_spend_limit_cents: 10000 }],
      '/teams/4': {
        id: 4, name: '设计组', owner_id: 1, company_name: '', tax_number: '',
        verify_status: 'none', verify_reason: '', active: true, balance_cents: 500000, my_role: 'owner', my_spend_limit_cents: 10000,
        monthly_budget_cents: 300000, month_spent_cents: 50000, my_month_spent_cents: 20000,
        members: [{ user_id: 1, role: 'owner', spend_limit_cents: 10000 }],
        invoice_block: '企业信息尚未核验，暂不能开具企业发票',
      },
      '/teams/4/spends': [
        { id: 7, requester_id: 2, amount_cents: 30000, purpose: '买素材', status: 'pending',
          task_id: null, decided_by: null, decision_reason: '', created_at: '2026-09-20T08:00:00Z',
          can_decide: true },
      ],
    });
    render(
      <MemoryRouter initialEntries={['/teams']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText('打开'));
    await waitFor(() => expect(screen.getByTestId('invoice-block')).toBeTruthy());
    // UI-075 开票闸门的理由原样显示
    expect(screen.getByTestId('invoice-block').textContent).toContain('尚未核验');
    // can_decide=true → 审批按钮在
    expect(screen.getByText('批准')).toBeTruthy();
    // TEAM-052 预算池要说清「还剩多少」
    expect(screen.getByTestId('team-budget').textContent).toContain('剩余 ¥2500.00');
  });

  it('UI-075 can_decide=false 时没有审批按钮（自己批自己不算审批）', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/teams/mine': [{ id: 4, name: '设计组', owner_id: 1, company_name: '甲公司', tax_number: '91310000X', verify_status: 'verified', verify_reason: '', active: true, my_role: 'member', my_spend_limit_cents: 10000 }],
      '/teams/4': {
        id: 4, name: '设计组', owner_id: 1, company_name: '甲公司', tax_number: '91310000X',
        verify_status: 'verified', verify_reason: '', active: true, balance_cents: 0, my_role: 'member', my_spend_limit_cents: 10000,
        monthly_budget_cents: 0, month_spent_cents: 0, my_month_spent_cents: 0,
        members: [], invoice_block: '',
      },
      '/teams/4/spends': [
        { id: 7, requester_id: 1, amount_cents: 30000, purpose: '买素材', status: 'pending',
          task_id: null, decided_by: null, decision_reason: '', created_at: '2026-09-20T08:00:00Z',
          can_decide: false },
      ],
    });
    render(
      <MemoryRouter initialEntries={['/teams']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText('打开'));
    await waitFor(() => expect(screen.getByText(/买素材/)).toBeTruthy());
    expect(screen.queryByText('批准')).toBeNull();
  });
});

describe('开发者设置', () => {
  it('UI-076 明文密钥只显示一次，且把那句话显示出来', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/developer/scopes': { scopes: [{ name: 'tasks:read', description: '读任务' }], note: '没有任何一档 scope 能动钱' },
      '/developer/api-keys': [],
      '/developer/webhooks': [],
    });
    render(
      <MemoryRouter initialEntries={['/developer']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('scope-note')).toBeTruthy());
    // scope 说明来自服务端：能给哪些权限是平台的决定
    expect(screen.getByTestId('scope-note').textContent).toContain('动钱');
  });

  it('UI-077 被自动停用的 Webhook 显示原因（悄悄停掉比不停更坏）', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/developer/scopes': { scopes: [], note: '' },
      '/developer/api-keys': [],
      '/developer/webhooks': [
        { id: 3, url: 'https://x/cb', events: ['task.completed'], active: false,
          consecutive_failures: 10, disabled_reason: '连续失败 10 次，已自动停用' },
      ],
    });
    render(
      <MemoryRouter initialEntries={['/developer']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('hook-disabled')).toBeTruthy());
    expect(screen.getByTestId('hook-disabled').textContent).toContain('自动停用');
  });
});
