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

// 工单台没有工单时整块不显示，给一张
const TICKET = { id: 7, user_id: 9, subject: '钱没到账', body: '', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 0, escalation_label: '', waited_hours: 1, sla_hours: 4, overdue_hours: 0,
  first_responded: false, first_response_hours: 1, first_response_overdue: false, replies_count: 0,
  last_user_reply: '', last_user_reply_at: null, awaiting_staff: false, category: 'funds', priority: 'urgent', priority_label: '加急' };

function open(roles: string[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const u = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body = u === '/users/me' ? me(roles)
      : u === '/admin/reports' ? [{ id: 1, reporter_id: 2, target_type: 'user', target_id: 5, reason: '骚扰', created_at: '2026-10-24T00:00:00Z' }]
      : u === '/admin/users' ? USERS
      : u === '/admin/support/my-categories' ? { categories: [], declared: false, labels: {} }
      : u === '/admin/tickets' ? [TICKET] : [];
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

  it('SEC-061l 客服看得到工单，但看不到「看客服状态」；超级管理员看得到', async () => {
    open(['support']);
    expect(await screen.findByLabelText('待处理工单')).toBeTruthy();
    expect(screen.queryByText('看客服状态')).toBeNull();
  });

  it('SEC-061l 超级管理员看得到「看客服状态」', async () => {
    open(['super']);
    expect(await screen.findByText('看客服状态')).toBeTruthy();
  });
});
