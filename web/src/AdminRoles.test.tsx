// SEC-061b 管理员与角色（141 号 spec）：每位管理员看得到自己的角色；超级管理员能分配。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AdminRolesPanel } from './AdminRoles';
import { AppProvider } from './store';

const ROLES = [
  { key: 'super', label: '超级管理员', scope: '全部权限' }, { key: 'support', label: '客服', scope: '工单' },
  { key: 'finance', label: '财务', scope: '提现' },
];
type Call = { method: string; path: string; body?: unknown };

function mount(mine: string[], calls: Call[] = []) {
  const routes: Record<string, unknown> = {
    '/admin/roles': { roles: ROLES, mine },
    '/admin/admins': { unclassified: 1, admins: [
      { user_id: 1, nickname: '老板', roles: ['super'], unclassified: false },
      { user_id: 2, nickname: '小王', roles: ['super'], unclassified: true },
    ] },
    'PUT /admin/admins/2/roles': { user_id: 2, nickname: '小王', roles: ['finance'], unclassified: false },
  };
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${p}`) ?? Object.keys(routes).find((k) => k === p);
    return { ok: true, status: 200, text: async () => JSON.stringify(key ? routes[key] : {}) };
  }) as unknown as typeof fetch;
  render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><AdminRolesPanel /></AppProvider>);
  return calls;
}

describe('SEC-061b 管理员与角色', () => {
  it('超级管理员：看到未分级的提醒，勾选后保存', async () => {
    const calls = mount(['super']);
    expect(await screen.findByText(/还有 1 位管理员没分配角色/)).toBeTruthy();
    expect(screen.getByText('未分级')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('小王 财务'));
    fireEvent.click(screen.getAllByRole('button', { name: '保存' })[1]);
    await screen.findByText('已更新「小王」的角色：财务');
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')).toEqual({ method: 'PUT', path: '/admin/admins/2/roles', body: { roles: ['finance'] } }));
  });

  it('不是超级管理员：只看到自己的角色，不去拉管理员名单', async () => {
    const calls = mount(['support']);
    expect(await screen.findByText('我的角色：客服')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
    expect(calls.some((c) => c.path === '/admin/admins')).toBe(false);
  });
});
