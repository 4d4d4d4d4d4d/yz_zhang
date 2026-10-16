// 管理后台冒烟：权限守卫 + 指标/队列渲染
import { PlatformClient } from '@platform/core';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const METRICS = {
  total_users: 10, verified_users: 8, total_tasks: 5, published_tasks: 2,
  completed_tasks: 3, closed_loop_rate: 0.6, dispute_count: 1,
  gmv_cents: 123400, fee_income_cents: 9872,
};

function clientAs(me: Record<string, unknown> | null): PlatformClient {
  const fetchImpl = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    text: async () => {
      const u = String(url);
      if (u.includes('/users/me')) return JSON.stringify(me);
      if (u.includes('/admin/metrics')) return JSON.stringify(METRICS);
      if (u.includes('/admin/reports')) return JSON.stringify([
        { id: 1, reporter_id: 2, target_type: 'content', target_id: 9, reason: '低俗', created_at: '2026-07-03T00:00:00' },
      ]);
      if (u.includes('/admin/users')) return JSON.stringify([]);
      return JSON.stringify([]);
    },
  })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const ADMIN_ME = {
  id: 1, phone: '138****0000', nickname: '管理员', bio: '', city: '', lat: null, lng: null,
  skills: [], interests: [], is_verified: true, is_admin: true, credit_score: 100,
  rating_avg: 0, tasks_completed: 0,
};

describe('Admin', () => {
  it('管理员可见指标与举报队列', async () => {
    localStorage.setItem('token', 'tok');
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AppProvider client={clientAs(ADMIN_ME)}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('60.0%')).toBeTruthy()); // 闭环率
    expect(screen.getByText('¥1234.00')).toBeTruthy(); // GMV
    expect(screen.getByText('低俗')).toBeTruthy(); // 举报队列
  });

  it('SEC-061d 财务只看到自己的板块：不相干的不显示、不发请求，页脚说清哪些不在职责里', async () => {
    localStorage.setItem('token', 'tok');
    const client = clientAs({ ...ADMIN_ME, admin_roles: ['finance'] });
    const urls: string[] = [];
    const orig = (client as unknown as { opts: { fetchImpl: typeof fetch } }).opts.fetchImpl;
    (client as unknown as { opts: { fetchImpl: typeof fetch } }).opts.fetchImpl = ((u: string, i?: RequestInit) => { urls.push(String(u)); return orig(u, i); }) as typeof fetch;
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AppProvider client={client}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('60.0%')).toBeTruthy());
    const footer = await screen.findByLabelText('不在你职责里的板块');
    expect(footer.textContent).toContain('服务包');
    expect(footer.textContent).toContain('举报处置');
    expect(footer.textContent).not.toContain('提现复核');
    expect(screen.queryByText('低俗')).toBeNull();
    expect(screen.queryByLabelText('服务包运营')).toBeNull();
    expect(urls.some((u) => u.includes('/admin/reports') || u.includes('/admin/packs') || u.includes('/admin/tickets'))).toBe(false);
    expect(urls.some((u) => u.includes('/wallet/withdraw-requests'))).toBe(true);
  });

  it('没分配角色的老管理员照旧全部可见（按超级管理员对待），没有「不在职责里」那句', async () => {
    localStorage.setItem('token', 'tok');
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AppProvider client={clientAs(ADMIN_ME)}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('低俗')).toBeTruthy());
    expect(screen.queryByLabelText('不在你职责里的板块')).toBeNull();
    expect(await screen.findByLabelText('服务包运营')).toBeTruthy();
  });

  it('非管理员被拦截', async () => {
    localStorage.setItem('token', 'tok');
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AppProvider client={clientAs({ ...ADMIN_ME, is_admin: false })}><App /></AppProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('需要管理员权限')).toBeTruthy());
  });
});
