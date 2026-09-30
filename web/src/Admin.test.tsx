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
