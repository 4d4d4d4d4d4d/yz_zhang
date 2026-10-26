// SCN-192（317 号 spec）发单人对每一次上门回报表态：对得上就确认，对不上写清哪里不对；接单人只看得到结果。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ME = (id: number) => ({ id, phone: '138****0002', nickname: 'x', bio: '', city: '上海', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: false, credit_score: 100, rating_avg: 0, tasks_completed: 0, certifications: [], credit_level: '普通', referral_code: 'r' });
const TASK = { id: 70, title: '上门收废品', description: '', category: '废品回收', status: 'in_progress', budget_cents: 5000,
  creator_id: 9, executor_id: 2, is_remote: false, city: '上海', address_hint: '', address_exact: '', parent_id: null,
  task_type: 'service', pricing: 'fixed', bonus_cents: 0, ip_assignment: 'assign', deposit_status: 'none',
  visits_planned: 1, visit_checklist: ['分类', '当面称'] };
const V = (extra = {}) => ({ task_id: 70, planned: 1, checklist: ['分类', '当面称'], reported: 1, missed_total: 0,
  visits: [{ n: 1, id: 5, created_at: '2030-01-05T02:00:00Z', done: ['分类', '当面称'], missed: [], note: '纸箱 12.4 斤', images: [], at_site_m: null, ...extra }] });
type Call = { method: string; path: string; body?: unknown };

function open(me: number, visits: unknown, calls: Call[], after: unknown = visits) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path: p, body: init?.body ? JSON.parse(init.body) : undefined });
    const body = p === '/users/me' ? ME(me) : p === '/tasks/70' ? TASK : p === '/tasks/70/visits' ? visits
      : p.startsWith('/tasks/70/visits/') ? after : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/tasks/70']}>
    <AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('SCN-192 上门回报的确认与异议', () => {
  it('发单人：点「对得上」确认；「有异议」要写理由才发', async () => {
    const calls: Call[] = [];
    open(9, V(), calls, V({ confirmed_at: '2030-01-05T03:00:00Z' }));
    const box = await screen.findByLabelText('上门回报');
    fireEvent.click(await within(box).findByText('对得上'));
    expect(await screen.findByTestId('visit-ok-5')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/70/visits/5/confirm')).toBe(true);
    const ask = vi.spyOn(window, 'prompt').mockReturnValueOnce(' ').mockReturnValueOnce(' 实际不到 12 斤 ');
    try {
      fireEvent.click(within(box).getByText('有异议'));
      expect(calls.some((c) => c.path === '/tasks/70/visits/5/object')).toBe(false);
      fireEvent.click(within(box).getByText('有异议'));
      await waitFor(() => expect(calls.find((c) => c.path === '/tasks/70/visits/5/object')?.body).toEqual({ reason: '实际不到 12 斤' }));
    } finally { ask.mockRestore(); }
  });

  it('接单人：看得到异议，没有表态的按钮', async () => {
    open(2, V({ objection: '实际不到 12 斤' }), []);
    expect((await screen.findByTestId('visit-objection-5')).textContent).toContain('有异议：实际不到 12 斤');
    expect(screen.queryByText('对得上')).toBeNull();
    expect(screen.queryByText('有异议')).toBeNull();
  });
});
