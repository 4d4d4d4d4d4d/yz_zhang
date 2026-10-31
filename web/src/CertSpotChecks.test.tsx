// CERT-053（348 号 spec）资质抽检：列出待复看的与审核员被推翻次数；自己审的不给按钮；推翻要写够理由。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = { id: 2, phone: '138****0002', nickname: '合规乙', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['compliance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r2' };
const ITEM = { id: 5, application_id: 40, user_id: 9, name: '驾驶证（三年以上驾龄）', reviewer_id: 3, reviewer_nickname: '合规甲',
  reason: 'high_risk', status: 'pending', checked_by: null, note: '', created_at: '2026-10-31T00:00:00Z', checked_at: null };
const LIST = { items: [ITEM, { ...ITEM, id: 6, application_id: 41, reviewer_id: 2, reviewer_nickname: '合规乙', reason: 'random' }],
  reviewers: [{ reviewer_id: 3, nickname: '合规甲', sampled: 4, overturned: 1 }] };
type Call = { method: string; path: string; body?: Record<string, unknown> };

function open(calls: Call[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME : p === '/admin/cert-spot-checks' ? LIST : p.startsWith('/admin/cert-spot-checks/') ? ITEM
      : p === '/admin/admins' ? { admins: [] } : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('CERT-053 资质抽检', () => {
  it('列出待复看的与被推翻次数；自己审的不给按钮；推翻要写够理由', async () => {
    const calls: Call[] = [];
    open(calls);
    const box = await screen.findByLabelText('资质抽检', {}, { timeout: 3000 });
    expect(box.textContent).toContain('合规甲 抽 4 推翻 1');
    expect(box.textContent).toContain('高风险资质全抽');
    const mine = within(box).getByText(/申请 #41/).closest('li')!;
    expect(within(mine).queryByText('维持')).toBeNull();
    const row = within(box).getByText(/申请 #40/).closest('li')!;
    const overturn = within(row).getByText('推翻并撤销') as HTMLButtonElement;
    expect(overturn.disabled).toBe(true);
    fireEvent.change(within(row).getByLabelText('抽检 5 的说明'), { target: { value: '证号查不到' } });
    expect(overturn.disabled).toBe(false);
    fireEvent.click(overturn);
    await waitFor(() => expect(calls.find((c) => c.path === '/admin/cert-spot-checks/5/overturn')?.body).toEqual({ note: '证号查不到' }));
    fireEvent.click(within(row).getByText('维持'));
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/cert-spot-checks/5/confirm')).toBe(true));
  });
});
