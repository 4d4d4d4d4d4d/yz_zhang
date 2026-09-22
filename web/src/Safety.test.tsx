// GEO-023 一键求助：服务端早就实现了，**两端都没有按钮**。
//
// `sos` 的服务端注释写着：「让求助按钮卡在合规弹窗上，是把合规做成了事故」——
// 为了让按钮不被弹窗挡住，特意去查了 PIPL 第十三条第(四)项；
// 而写这句话的时候，那个按钮在任何一个端上都不存在。
//
// 而且 SDK 把响应声明成了 `{ id, notified }`，服务端返回的是 `{ ok, guidance }`。
// **声明错了这么久没人发现，正因为没有任何一处调用过它。**
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

// 线下 + 进行中：求助按钮**只在这种任务上**出现。
// 任务没开始或已结束时摆一个求助按钮，只会稀释它。
const TASK = {
  id: 7, title: '上门保洁', description: '', category: '保洁', status: 'in_progress',
  budget_cents: 20000, creator_id: 1, executor_id: 2, is_remote: false, city: '上海',
  address_hint: '徐汇', address_exact: '某某路 1 号', parent_id: null, task_type: 'service',
  pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
};

const GUIDANCE = '已通知平台与任务对方；如遇危险请立即拨打 110';

function makeClient(routes: Record<string, unknown>, calls: string[] = []): PlatformClient {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push(`${init?.method ?? 'GET'} ${path}`);
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('GEO-023 一键求助', () => {
  it('进行中的线下任务上有求助入口，并原样显示服务端的指引', async () => {
    localStorage.setItem('token', 'tok');
    const calls: string[] = [];
    const client = makeClient({
      '/users/me': ME,
      '/tasks/7': TASK,
      '/tasks/7/sos': { ok: true, guidance: GUIDANCE },
    }, calls);
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('🆘 一键求助')).toBeTruthy());
    fireEvent.click(screen.getByText('🆘 一键求助'));

    await waitFor(() => expect(screen.getByTestId('sos-guidance')).toBeTruthy());
    // 指引原样显示：这一刻唯一对用户有用的就是这句话
    expect(screen.getByTestId('sos-guidance').textContent).toBe(GUIDANCE);
    expect(calls).toContain('POST /tasks/7/sos');
  });

  it('线上任务不显示求助入口', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/tasks/7': { ...TASK, is_remote: true },
    });
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('上门保洁')).toBeTruthy());
    expect(screen.queryByText('🆘 一键求助')).toBeNull();
  });

  it('GEO-022 执行方能开行程分享，读的是服务端返回的键', async () => {
    localStorage.setItem('token', 'tok');
    const client = makeClient({
      '/users/me': ME,
      '/tasks/7': TASK,
      // 服务端返回的键是 trip_share_enabled，不是 enabled——
      // SDK 此前声明错了，而没人调用过所以没人发现
      '/tasks/7/trip-share': { trip_share_enabled: true },
    });
    render(
      <MemoryRouter initialEntries={['/tasks/7']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('开启行程分享')).toBeTruthy());
    fireEvent.click(screen.getByText('开启行程分享'));
    await waitFor(() => expect(screen.getByText('关闭行程分享')).toBeTruthy());
  });
});
