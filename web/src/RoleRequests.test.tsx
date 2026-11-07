// SEC-061i（315 号 spec）临时角色的申请与审批：客服申请财务，超级管理员批准 / 驳回；超级管理员自己不出申请表。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AdminRolesPanel } from './AdminRoles';
import { AppProvider } from './store';

const ROLES = [
  { key: 'super', label: '超级管理员', scope: '全部权限' }, { key: 'support', label: '客服', scope: '工单' },
  { key: 'finance', label: '财务', scope: '提现' },
];
const PENDING = { id: 5, user_id: 3, nickname: '小李', role: 'finance', hours: 24, reason: '月底对账', status: 'pending', created_at: '2026-10-24T00:00:00Z' };
type Call = { method: string; path: string; body?: unknown };

function mount(mine: string[], requests: unknown[], calls: Call[]) {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/admin/roles' ? { roles: ROLES, mine } : p === '/admin/admins' ? { unclassified: 0, admins: [] }
      : p === '/admin/role-requests' && method === 'GET' ? requests
      : p === '/admin/role-requests' ? { ...PENDING, id: 6 } : { ...PENDING, status: 'approved' };
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><AdminRolesPanel /></AppProvider>);
}

describe('SEC-061i 临时角色申请', () => {
  it('客服：只能申请自己没有的、不是超级管理员的角色；写了理由才能提交', async () => {
    const calls: Call[] = [];
    mount(['support'], [], calls);
    const box = await screen.findByLabelText('临时角色申请');
    const opts = [...within(box).getByLabelText('申请哪个角色').querySelectorAll('option')].map((o) => o.textContent);
    expect(opts).toEqual(['— 选角色 —', '财务']);
    fireEvent.change(within(box).getByLabelText('申请哪个角色'), { target: { value: 'finance' } });
    fireEvent.change(within(box).getByLabelText('多少小时'), { target: { value: '24' } });
    const submit = within(box).getByText('提交申请') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText('申请理由'), { target: { value: ' 月底对账 ' } });
    fireEvent.click(submit);
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/role-requests')?.body)
      .toEqual({ role: 'finance', hours: 24, reason: '月底对账' }));
    expect(await screen.findByText('已提交：等另一位超级管理员批准后，「财务」才生效')).toBeTruthy();
    expect(screen.queryByText('批准')).toBeNull();
  });

  it('超级管理员：不出申请表，看得到待批的，能批准、驳回（驳回要理由）', async () => {
    const calls: Call[] = [];
    mount(['super'], [PENDING], calls);
    const row = await screen.findByTestId('role-request-5');
    expect(row.textContent).toContain('小李 申请「财务」24 小时：月底对账');
    expect(screen.queryByLabelText('申请哪个角色')).toBeNull();
    fireEvent.click(within(row).getByText('批准'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/role-requests/5/approve')).toBe(true));
    const ask = vi.spyOn(window, 'prompt').mockReturnValueOnce('x').mockReturnValueOnce('这周人手够');
    try {
      fireEvent.click(within(await screen.findByTestId('role-request-5')).getByText('驳回'));
      expect(calls.some((c) => c.path === '/admin/role-requests/5/reject')).toBe(false);
      fireEvent.click(within(screen.getByTestId('role-request-5')).getByText('驳回'));
      await waitFor(() => expect(calls.find((c) => c.path === '/admin/role-requests/5/reject')?.body).toEqual({ note: '这周人手够' }));
    } finally { ask.mockRestore(); }
  });
});
