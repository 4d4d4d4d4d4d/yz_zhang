// FIN-063（223 号 spec）报表锁账：写明锁到哪个月；已锁的月份标出来、锁账后又记进来的写明去向；
// 锁账前确认（锁了不能解锁），锁完重新读报表。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '财务', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['finance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const P = (period: string, extra: Record<string, unknown> = {}) => ({ period, start: '', end: '', fee_cents: 1000, fee_count: 2,
  settled_cents: 0, subsidy_cents: 0, other_cents: 0, net_cents: 1000, opening_cents: 0, closing_cents: 1000, balanced: true,
  closed: false, late_cents: 0, late_count: 0, carried_in_cents: 0, carried_in_count: 0, ...extra });
type Call = { method: string; path: string; body?: unknown };

function open(calls: Call[], locked: boolean) {
  localStorage.setItem('token', 'tok');
  let afterLock = false;
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    const path = full.split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    if (path === '/admin/platform-finance/lock') afterLock = true;
    const isLocked = locked || afterLock;
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/platform-finance' ? { balance_cents: 0, total_fee_cents: 0, settled_cents: 0, fee_count: 0 }
      : path === '/admin/platform-finance/periods' ? {
          granularity: 'month', locked_through: isLocked ? '2026-08' : null, locked_at: isLocked ? '2026-09-02T02:00:00Z' : null,
          periods: isLocked
            ? [P('2026-08', { closed: true, late_cents: 250, late_count: 1 }), P('2026-09', { carried_in_cents: 250, carried_in_count: 1 })]
            : [P('2026-08'), P('2026-09')] }
      : path === '/admin/platform-finance/lock' ? { locked_through: '2026-08', months: ['2026-07', '2026-08'], locked_at: '2026-09-02T02:00:00Z' }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('FIN-063 报表锁账', () => {
  it('已锁的月份标出来，锁账后补记的写明记到了哪里', async () => {
    open([], true);
    const box = await screen.findByLabelText('按期间');
    await waitFor(() => expect(within(box).getByTestId('finance-locked-through').textContent).toContain('已锁到 2026-08'));
    const aug = within(box).getByTestId('period-note-2026-08').textContent ?? '';
    expect(aug).toContain('已锁');
    expect(aug).toContain('锁账后又记进 1 笔（¥2.50），已记到下一个未锁月份');
    const sep = within(box).getByTestId('period-note-2026-09').textContent ?? '';
    expect(sep).not.toContain('已锁');
    expect(sep).toContain('含补记以前期间 1 笔（¥2.50）');
  });

  it('没选月份不发；确认后锁账并重新读报表；取消确认不发', async () => {
    const calls: Call[] = [];
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    open(calls, false);
    const box = await screen.findByLabelText('按期间');
    await waitFor(() => expect(within(box).getByTestId('finance-locked-through').textContent).toContain('还没有锁过账'));
    fireEvent.click(within(box).getByText('锁账到此月'));
    expect(await within(box).findByText('先选要锁到哪个月')).toBeTruthy();
    fireEvent.change(within(box).getByLabelText('锁账到'), { target: { value: '2026-08' } });
    fireEvent.click(within(box).getByText('锁账到此月'));
    expect(confirm.mock.calls[0][0]).toContain('锁了不能解锁');
    expect(calls.some((c) => c.path === '/admin/platform-finance/lock')).toBe(false);
    confirm.mockReturnValue(true);
    fireEvent.click(within(box).getByText('锁账到此月'));
    expect((await within(box).findByRole('status')).textContent).toBe('已锁到 2026-08（这次锁了 2 个月：2026-07~2026-08）。已记入审计。');
    expect(calls.find((c) => c.path === '/admin/platform-finance/lock')?.body).toEqual({ through: '2026-08' });
    await waitFor(() => expect(within(box).getByTestId('finance-locked-through').textContent).toContain('已锁到 2026-08'));
  });
});
