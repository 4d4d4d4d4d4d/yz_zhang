// ESCA-051 工单超时升级：后台工单台与我的工单（150 号 spec）。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '客服', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['support'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
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
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={[path]}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('ESCA-051 后台工单台', () => {
  it('显示升级级别、等了多久、超了多久、有没有人接手；可认领；筛选带到请求里', async () => {
    const urls: string[] = [];
    open('/admin', urls, ADMIN, [ROW]);
    expect((await screen.findByTestId('ticket-level-7')).textContent).toContain('已升级给主管');
    const sla = screen.getByTestId('ticket-sla-7').textContent ?? '';
    expect(sla).toContain('已等 50 小时');
    expect(sla).toContain('已超 26 小时');
    expect(sla).toContain('还没人接手');
    expect(urls.some((u) => u.startsWith('/admin/tickets?') && u.includes('sort=urgent'))).toBe(true);
    fireEvent.click(screen.getByText('我来处理'));
    await waitFor(() => expect(urls).toContain('/admin/tickets/7/claim'));
    fireEvent.click(screen.getByLabelText(/只看我接手的/));
    await waitFor(() => expect(urls.some((u) => u.startsWith('/admin/tickets?') && u.includes('mine=true'))).toBe(true));
  });
});

describe('ESCA-051 我的工单', () => {
  it('提单人看到处理进度：有人接手、已升级给主管', async () => {
    const urls: string[] = [];
    const me = { ...ADMIN, is_admin: false, admin_roles: [] };
    open('/support', urls, me, [{ id: 7, subject: '提现没到账', body: '急', status: 'open', reply: '', created_at: '2026-10-13T00:00:00Z',
      claimed: true, escalation_level: 2, escalation_label: '已升级给主管', waited_hours: 50, sla_hours: 24, overdue_hours: 26 }]);
    const p = await screen.findByTestId('ticket-progress-7');
    expect(p.textContent).toContain('已有客服接手');
    expect(p.textContent).toContain('已升级给客服主管跟进');
  });
});
