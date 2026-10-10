// SC-007 / SC-004 变更单与分期在网页上的行为（70 号 spec）。
//
// 服务端两条都做得很完整，而**两端都没有入口**；变更单更缺一层：
// 连「列出变更单」的接口都没有，对方拿不到 order_id，有按钮也点不了。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = {
  id: 2, phone: '138****0002', nickname: '执行者', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: false, credit_score: 100,
  rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r2',
};

const TASK = {
  id: 7, title: '上门保洁', description: '', category: '保洁', status: 'in_progress',
  budget_cents: 20000, creator_id: 1, executor_id: 2, is_remote: false, city: '上海',
  address_hint: '徐汇', address_exact: '某某路 1 号', parent_id: null, task_type: 'service',
  pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
};

const CONTRACT = {
  id: 3, task_id: 7, requester_id: 1, executor_id: 2, amount_cents: 20000,
  released_cents: 0, fee_bps: 800, deposit_cents: 0, deposit_status: 'none',
  terms: '合同条款', status: 'funded', signed_by_requester: true,
  signed_by_executor: true, frozen: false, version: 1, milestones: [],
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

function open(routes: Record<string, unknown>, calls: Array<{ method: string; path: string; body: unknown }> = []) {
  localStorage.setItem('token', 'tok');
  const client = makeClient({
    '/users/me': ME, '/tasks/7': TASK, '/contracts/by-task/7': CONTRACT, ...routes,
  }, calls);
  render(
    <MemoryRouter initialEntries={['/tasks/7']}>
      <AppProvider client={client}><App /></AppProvider>
    </MemoryRouter>,
  );
  return calls;
}

describe('SC-007 变更单', () => {
  it('提案把金额与事由都发上去', async () => {
    const calls = open({ '/contracts/3/change-orders': [] });
    await waitFor(() => expect(screen.getByText('提出变更')).toBeTruthy());

    fireEvent.change(screen.getByPlaceholderText('新金额（元）'), { target: { value: '300' } });
    fireEvent.change(screen.getByPlaceholderText('事由（对方会看到）'), { target: { value: '加了两个房间' } });
    fireEvent.click(screen.getByText('提出变更'));

    await waitFor(() => {
      const c = calls.find((x) => x.method === 'POST' && x.path === '/contracts/3/change-orders');
      expect(c?.body).toMatchObject({ new_amount_cents: 30000, reason: '加了两个房间' });
    });
  });

  it('读服务端的 can_decide，不自己重算「谁能接受」', async () => {
    open({
      '/contracts/3/change-orders': [{
        id: 1, contract_id: 3, proposed_by: 2, new_amount_cents: 30000,
        reason: '加了两个房间', status: 'pending', created_at: '2026-09-24T00:00:00Z',
        can_decide: false,
      }],
    });
    await waitFor(() => expect(screen.getByText(/加了两个房间/)).toBeTruthy());
    expect(screen.queryByText('接受')).toBeNull();
    // 已有待处理变更单时不再给提案入口（服务端也会回 change_pending）
    expect(screen.queryByText('提出变更')).toBeNull();
  });
});

describe('SC-004 分期', () => {
  const PENDING = { ...CONTRACT, status: 'pending_signatures', signed_by_requester: false, signed_by_executor: false };
  const CREATOR_ME = { ...ME, id: 1 };

  it('把「还差多少」算给用户看，但判定仍以服务端为准', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': CREATOR_ME, '/tasks/7': TASK, '/contracts/by-task/7': PENDING,
      '/contracts/3/change-orders': [],
    });
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('milestone-sum')).toBeTruthy());
    // 两期都还没填：合计 0，差整份合约金额
    expect(screen.getByTestId('milestone-sum').textContent).toContain('还差 ¥200.00');

    const amounts = screen.getAllByPlaceholderText('金额（元）');
    fireEvent.change(amounts[0], { target: { value: '80' } });
    fireEvent.change(amounts[1], { target: { value: '120' } });
    await waitFor(() =>
      expect(screen.getByTestId('milestone-sum').textContent).not.toContain('还差'));
  });

  it('双签前才给分期入口（签署后服务端会回 milestones_locked）', async () => {
    open({ '/contracts/3/change-orders': [] });   // funded 合约
    await waitFor(() => expect(screen.getByText('提出变更')).toBeTruthy());
    expect(screen.queryByText('保存分期')).toBeNull();
  });
});

// SC-013 整单验收会放掉**剩余全部**期（服务端如此设计，93 号 spec）。
//
// 发布方当初定分期，正是为了不一次付完。在一个只写「验收通过（放款）」的
// 按钮上一次放光，他失去的是自己设置的那道保护——所以还有未放期时，
// 必须先把「几期、多少钱」说清。
describe('SC-013 整单验收前要说清会放掉几期', () => {
  const PENDING_TASK = { ...TASK, status: 'pending_acceptance' };
  const REQUESTER = { ...ME, id: 1, nickname: '发布者' };
  const STAGED = {
    ...CONTRACT,
    milestones: [
      { idx: 1, title: '一期', amount_cents: 6000, status: 'released' },
      { idx: 2, title: '二期', amount_cents: 6000, status: 'pending' },
      { idx: 3, title: '三期', amount_cents: 8000, status: 'pending' },
    ],
  };

  function openAsRequester(contract: unknown, calls: Array<{ method: string; path: string; body: unknown }> = []) {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': REQUESTER, '/tasks/7': PENDING_TASK,
      '/contracts/by-task/7': contract, '/contracts/3/change-orders': [],
    }, calls);
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    return calls;
  }

  it('有两期未放时，确认框说出期数与金额；取消则不放款', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    try {
      const calls = openAsRequester(STAGED);
      fireEvent.click(await screen.findByText('验收通过（放款）'));
      // 只剩二期与三期未放：6000 + 8000 = 14000 分
      expect(confirmSpy.mock.calls[0][0]).toContain('剩余 2 期');
      expect(confirmSpy.mock.calls[0][0]).toContain('¥140.00');
      // 取消就是取消——不发请求
      expect(calls.some((c) => c.path === '/tasks/7/accept-delivery')).toBe(false);
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it('确认之后才真的整单放款', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    try {
      const calls = openAsRequester(STAGED);
      fireEvent.click(await screen.findByText('验收通过（放款）'));
      await waitFor(() => expect(
        calls.some((c) => c.method === 'POST' && c.path === '/tasks/7/accept-delivery'),
      ).toBe(true));
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it('单期合约不多问一遍——那是绝大多数合约，问了就是噪音', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    try {
      const single = {
        ...CONTRACT,
        milestones: [{ idx: 1, title: '全部', amount_cents: 20000, status: 'pending' }],
      };
      const calls = openAsRequester(single);
      fireEvent.click(await screen.findByText('验收通过（放款）'));
      // 一个假报警多的确认框会被人养成无脑点「确定」的习惯
      expect(confirmSpy).not.toHaveBeenCalled();
      await waitFor(() => expect(
        calls.some((c) => c.path === '/tasks/7/accept-delivery'),
      ).toBe(true));
    } finally {
      confirmSpy.mockRestore();
    }
  });
});
