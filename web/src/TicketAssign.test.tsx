// ESCA-053 / ESCA-054 首次响应与主管指派（157 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '主管', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['super'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = { id: 7, user_id: 9, subject: '提现没到账', body: '急', created_at: '2026-10-13T00:00:00Z', assignee_id: null,
  assignee_nickname: '', escalation_level: 2, escalation_label: '已升级给主管', waited_hours: 50, sla_hours: 24, overdue_hours: 26 };

function open(path: string, urls: string[], me: unknown, tickets: unknown) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    urls.push(full);
    const p = full.split('?')[0];
    const body: unknown = p === '/users/me' ? me
      : p === '/admin/tickets' ? tickets
      : p === '/support/tickets' ? tickets
      : p === '/admin/tickets/7/claim' ? { id: 7, assignee_id: 1, assignee_nickname: '客服', previous_assignee_id: null }
      : p === '/admin/admins' ? { admins: [{ user_id: 5, nickname: '小王', roles: ['support'], unclassified: false }, { user_id: 6, nickname: '财务老李', roles: ['finance'], unclassified: false }], unclassified: 0 }
      : p === '/admin/tickets/7/reply' ? { id: 7, status: 'open', first_response_at: '2026-10-15T00:00:00Z', replies: 1 }
      : p === '/admin/tickets/7/assign' ? { id: 7, assignee_id: 5, assignee_nickname: '小王', previous_assignee_id: null }
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

const FR = { ...ROW, escalation_level: 0, escalation_label: '', waited_hours: 6, overdue_hours: 0, first_responded: false,
  first_response_hours: 4, first_response_overdue: true, replies_count: 0 };

describe('ESCA-053 / ESCA-054 后台工单台', () => {
  it('标出首次响应超时；可以先回一句不结单；主管可以指派给客服（只列有客服角色的人）', async () => {
    const urls: string[] = [];
    vi.spyOn(window, 'prompt').mockReturnValue('在查了，稍等');
    open('/admin', urls, ADMIN, [FR]);
    expect((await screen.findByTestId('ticket-fr-7')).textContent).toContain('首次响应已超时');
    expect(screen.getByTestId('ticket-sla-7').textContent).toContain('还没回过（首次响应时限 4 小时）');
    fireEvent.click(screen.getByText('先回一句'));
    await waitFor(() => expect(urls).toContain('/admin/tickets/7/reply'));
    const select = await screen.findByLabelText('指派工单 7');
    expect(select.textContent).toContain('小王');
    expect(select.textContent).not.toContain('财务老李');
    fireEvent.change(select, { target: { value: '5' } });
    await waitFor(() => expect(urls).toContain('/admin/tickets/7/assign'));
  });
});
