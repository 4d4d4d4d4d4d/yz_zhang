// MOD-060 / ADMIN-060 / FIN-060 运营侧剩下的四条（73 号 spec）。
//
// 这里验的是源码扫描闸门验不到的那一条：**封禁之前有没有真的先看影响面**。
// 闸门只能看出「`banImpact` 被调用了、组件挂上了」；它看不出
// 按钮到底是先弹确认还是直接把人封了——而那正是「管理员盲封」的要害。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = {
  id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r1',
};

const METRICS = {
  total_users: 10, verified_users: 8, total_tasks: 20, published_tasks: 3,
  completed_tasks: 12, closed_loop_rate: 0.6, dispute_count: 1,
  gmv_cents: 1000000, fee_income_cents: 80000,
};

const USER = {
  id: 9, phone: '139****0009', nickname: '要封的人', is_verified: true,
  is_banned: false, credit_score: 60, tasks_completed: 3,
};

const IMPACT = {
  in_flight_contracts: [
    { contract_id: 3, task_id: 7, status: 'funded', amount_cents: 20000, counterparty_id: 5 },
  ],
  in_flight_count: 1,
  escrow_at_risk_cents: 20000,
  open_task_ids: [11, 12],
  open_task_count: 2,
  wallet: { available_cents: 5000, escrow_cents: 0, frozen_cents: 1000 },
};

function makeClient(
  routes: Record<string, unknown>,
  calls: Array<{ method: string; path: string; body: unknown }> = [],
): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

function openAdmin(
  routes: Record<string, unknown> = {},
  calls: Array<{ method: string; path: string; body: unknown }> = [],
) {
  localStorage.setItem('token', 'tok');
  const client = makeClient({
    '/users/me': ADMIN,
    '/admin/metrics': METRICS,
    '/admin/reports': [],
    '/admin/users': [USER],
    '/wallet/withdraw-requests': [],
    '/admin/aml/activities': { items: [], note: '' },
    '/admin/audit-log': [],
    '/admin/platform-finance': { balance_cents: 80000, total_fee_cents: 80000, settled_cents: 0, fee_count: 4 },
    '/admin/users/9/ban-impact': IMPACT,
    ...routes,
  }, calls);
  render(
    <MemoryRouter initialEntries={['/admin']}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

describe('MOD-060 封禁前先看影响面', () => {
  it('点封禁不直接封人，先把代价摆出来', async () => {
    const calls = openAdmin();
    await waitFor(() => expect(screen.getByText('要封的人')).toBeTruthy());
    fireEvent.click(screen.getByText('封禁'));

    await waitFor(() => expect(screen.getByTestId('ban-confirm')).toBeTruthy());
    // **这一步之前不能有任何封禁请求发出去**
    expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/users/9/ban')).toBe(false);
    expect(calls.some((c) => c.path === '/admin/users/9/ban-impact')).toBe(true);
  });

  it('影响面要说清在途合约、托管资金与会被下架的任务', async () => {
    openAdmin();
    await waitFor(() => expect(screen.getByText('要封的人')).toBeTruthy());
    fireEvent.click(screen.getByText('封禁'));

    await waitFor(() => expect(screen.getByTestId('ban-escrow')).toBeTruthy());
    expect(screen.getByTestId('ban-escrow').textContent).toContain('¥200.00');
    // open_task_ids / open_task_count 服务端一直在返回，而 SDK 的行内类型里没有，
    // 于是界面显示不出「几个招募中的任务会被下架」（V89 那一类漂移）
    expect(screen.getByTestId('ban-tasks').textContent).toContain('2 个');
    expect(screen.getByTestId('ban-tasks').textContent).toContain('#11, #12');
  });

  it('确认之后才真的封', async () => {
    const calls = openAdmin({ '/admin/users/9/ban': { ok: true } });
    await waitFor(() => expect(screen.getByText('要封的人')).toBeTruthy());
    fireEvent.click(screen.getByText('封禁'));
    await waitFor(() => expect(screen.getByText('我已知晓影响，确认封禁')).toBeTruthy());
    fireEvent.click(screen.getByText('我已知晓影响，确认封禁'));

    await waitFor(() => expect(
      calls.some((c) => c.method === 'POST' && c.path === '/admin/users/9/ban'),
    ).toBe(true));
  });

  it('取消就什么都不做', async () => {
    const calls = openAdmin();
    await waitFor(() => expect(screen.getByText('要封的人')).toBeTruthy());
    fireEvent.click(screen.getByText('封禁'));
    await waitFor(() => expect(screen.getByText('取消')).toBeTruthy());
    fireEvent.click(screen.getByText('取消'));
    expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/users/9/ban')).toBe(false);
  });
});

describe('ADMIN-060 / FIN-060 / 公告', () => {
  it('审计日志按动作过滤，并显示是谁做的', async () => {
    const calls = openAdmin({
      '/admin/audit-log': [{
        id: 1, admin_id: 1, action: 'withdraw_approve', target_type: 'withdraw_request',
        target_id: 5, detail: '批准提现 3000000 分', created_at: '2026-09-28T00:00:00Z',
      }],
    });
    await waitFor(() => expect(screen.getByText('withdraw_approve')).toBeTruthy());
    // 谁批的、批了哪一笔、多少钱——三件事都要在界面上答得出来
    expect(screen.getByText('#1')).toBeTruthy();
    expect(screen.getByText('批准提现 3000000 分')).toBeTruthy();
    expect(calls.some((c) => c.path === '/admin/audit-log')).toBe(true);
  });

  it('平台财务显示佣金与已结算，结算打到 settle 端点', async () => {
    const calls = openAdmin({ '/admin/platform-finance/settle': { settled_cents: 100, balance_cents: 79900 } });
    await waitFor(() => expect(screen.getByText('平台财务')).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText('结算金额（元）'), { target: { value: '1' } });
    fireEvent.click(screen.getByText('结算划出'));
    await waitFor(() => {
      const c = calls.find((x) => x.path === '/admin/platform-finance/settle');
      expect(c?.body).toMatchObject({ amount_cents: 100 });
    });
  });

  it('公告发完回显送达人数（发出去收不回来）', async () => {
    openAdmin({ '/admin/announcements': { delivered: 42 } });
    await waitFor(() => expect(screen.getByText('发布全站公告')).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText('标题'), { target: { value: '系统维护' } });
    fireEvent.click(screen.getByRole('button', { name: '发布' }));
    await waitFor(() => expect(screen.getByTestId('ann-result').textContent).toContain('42 人'));
  });
});
