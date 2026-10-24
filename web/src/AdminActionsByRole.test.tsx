// SEC-061h（295 号 spec）后台板块里的按钮按角色收起：客服看得到举报与用户管理，但封禁 / 解封换成「要合规来做」。
import { PlatformClient } from '@platform/core';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const me = (roles: string[]) => ({
  id: 1, phone: '138****0000', nickname: '管理员', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: roles, credit_score: 100, rating_avg: 0, tasks_completed: 0,
});
const USERS = [
  { id: 5, nickname: '甲', phone: '138****0005', credit_score: 100, tasks_completed: 0, is_banned: false, is_verified: true },
  { id: 6, nickname: '乙', phone: '138****0006', credit_score: 60, tasks_completed: 0, is_banned: true, is_verified: true },
];

function open(roles: string[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const u = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body = u === '/users/me' ? me(roles)
      : u === '/admin/reports' ? [{ id: 1, reporter_id: 2, target_type: 'user', target_id: 5, reason: '骚扰', created_at: '2026-10-24T00:00:00Z' }]
      : u === '/admin/users' ? USERS
      : u === '/admin/support/my-categories' ? { categories: [], declared: false, labels: {} } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SEC-061h 按钮按角色', () => {
  it('客服：能驳回、下架，封禁与解封换成一句话', async () => {
    open(['support']);
    const reports = await screen.findByLabelText('举报处置');
    expect(await within(reports).findByText('驳回')).toBeTruthy();
    expect(within(reports).queryByText('封禁')).toBeNull();
    expect(within(reports).getByTestId('report-ban-hint-1').textContent).toBe('封禁用户要合规来做');
    expect((await screen.findByTestId('ban-hint-5')).textContent).toBe('封禁用户要合规来做');
    expect(screen.getByTestId('unban-hint-6').textContent).toBe('解封用户要合规来做');
    expect(screen.queryByText('解封')).toBeNull();
  });

  it('合规：按钮都在', async () => {
    open(['compliance']);
    const reports = await screen.findByLabelText('举报处置');
    expect(await within(reports).findByText('封禁')).toBeTruthy();
    expect(await screen.findByText('解封')).toBeTruthy();
    expect(screen.queryByTestId('ban-hint-5')).toBeNull();
  });
});
