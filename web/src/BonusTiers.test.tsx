// OUT-050（443 号 spec）任务详情上的浮动对价：没分档的照旧「达标可加付至多」，分档的逐档写出来。
import { PlatformClient } from '@platform/core';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '执行方', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0 };
const TASK = {
  id: 7, title: '写一篇接口文档', description: '', category: '软件开发', status: 'published', budget_cents: 20000, creator_id: 1,
  executor_id: null, is_remote: true, city: '', address_hint: '', address_exact: '', parent_id: null, task_type: 'simple',
  pricing: 'outcome', bonus_cents: 9000, ip_assignment: 'assign', deposit_status: 'none',
};

function open(task: Record<string, unknown>) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body = path === '/users/me' ? ME : path === '/tasks/7' ? task : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/7']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider>
  </MemoryRouter>);
}

describe('OUT-050 浮动对价分档', () => {
  it('分档的逐档写出来，说明取最高一档不累加', async () => {
    open({ ...TASK, bonus_tiers: [{ min_passed: 1, bonus_cents: 2000 }, { min_passed: 3, bonus_cents: 9000 }] });
    await waitFor(() => expect(screen.getByTestId('task-terms').textContent).toContain('分档加付'));
    const text = screen.getByTestId('task-terms').textContent ?? '';
    expect(text).toContain('过 1 条加付 ¥20.00，过 3 条加付 ¥90.00（取最高一档，不累加）');
    expect(text).not.toContain('达标可加付至多');
  });

  it('没分档的照旧（老数据没有这个字段也一样）', async () => {
    open(TASK);
    await waitFor(() => expect(screen.getByTestId('task-terms').textContent).toContain('达标可加付至多'));
    expect(screen.getByTestId('task-terms').textContent).toContain('¥90.00');
  });
});
