// FIN-064（265 号 spec）已锁月份的更正说明：只在锁过账之后出现；提交带差额（分）；待批准的可批准 / 驳回，
// 批准后重新读报表；已批准的挂在那个月的行上。
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
const PENDING = { id: 3, period: '2026-08', report: 'platform', note: '一笔补贴误记为其他调整', amount_delta_cents: -500, requested_by: 2,
  status: 'awaiting_second', decided_by: null, decision_reason: '', created_at: '2026-09-03T00:00:00Z', decided_at: null,
  needs_super_second: false };
type Call = { method: string; path: string; body?: unknown };
const GMV = (corrections: unknown[]) => ({ period: '2026-08', start: '', end: '', gmv_cents: 100000, release_count: 3, executor_net_cents: 90000,
  fee_cents: 10000, dispute_split_cents: 0, refund_cents: 0, withheld_cents: 0, withheld_count: 0, withheld_people: 0, withheld_income_cents: 0,
  remitted_cents: 0, tax_pending_cents: 0, closed: true, late_gmv_cents: 0, late_withheld_cents: 0, ...(corrections.length ? { corrections } : {}) });

function open(calls: Call[], locked: boolean) {
  localStorage.setItem('token', 'tok');
  let approved = false;
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : undefined });
    if (path === '/admin/platform-finance/corrections/3/approve') approved = true;
    const note = { id: 3, period: '2026-08', note: PENDING.note, amount_delta_cents: -500, requested_by: 2, approved_by: 1, approved_at: '2026-09-04T00:00:00Z' };
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/platform-finance' ? { balance_cents: 0, total_fee_cents: 0, settled_cents: 0, fee_count: 0 }
      : path === '/admin/platform-finance/periods' ? {
          granularity: 'month', locked_through: locked ? '2026-08' : null, locked_at: null,
          periods: [P('2026-08', { closed: locked, ...(approved ? { corrections: [note] } : {}) }), P('2026-09')] }
      : path === '/admin/platform-finance/corrections' && method === 'GET' ? (approved ? [] : [PENDING, { ...PENDING, id: 8, amount_delta_cents: -20000000, needs_super_second: true }])
      : path === '/admin/platform-finance/corrections' ? { ...PENDING, id: 4 }
      : path.startsWith('/admin/platform-finance/corrections/') ? { ...PENDING, status: 'approved', decided_by: 1 }
      : path === '/admin/platform-finance/gmv-tax' ? { granularity: 'month', basis: [], draft_note: '', periods: [GMV(approved ? [{ ...note, id: 5, note: '一笔放款重复计入成交额' }] : [])] }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('FIN-064 更正说明', () => {
  it('没锁过账时不出现', async () => {
    const calls: Call[] = [];
    open(calls, false);
    await screen.findByLabelText('按期间');
    await waitFor(() => expect(calls.some((c) => c.path === '/admin/platform-finance/periods')).toBe(true));
    expect(screen.queryByLabelText('更正说明')).toBeNull();
  });

  it('FIN-068 选「成交额与代扣税表」提交带 report；平台收支表不带（与 V292 一样）；批准后挂到成交额表上', async () => {
    const calls: Call[] = [];
    open(calls, true);
    const box = await screen.findByLabelText('更正说明');
    fireEvent.change(within(box).getByLabelText('更正哪张表'), { target: { value: 'gmv_tax' } });
    fireEvent.change(within(box).getByLabelText('更正哪个月'), { target: { value: '2026-08' } });
    fireEvent.change(within(box).getByPlaceholderText('哪里错、为什么'), { target: { value: '一笔放款重复计入成交额' } });
    fireEvent.click(within(box).getByText('提交更正说明'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/platform-finance/corrections')?.body)
      .toEqual({ period: '2026-08', note: '一笔放款重复计入成交额', amount_delta_cents: 0, report: 'gmv_tax' }));
    expect(within(box).getByTestId('pending-correction-3').textContent).toContain('平台收支表 2026-08');
    expect(within(box).getByTestId('pending-correction-3').textContent).not.toContain('要超级管理员批准');
    expect(within(box).getByTestId('pending-correction-8').textContent).toContain('要超级管理员批准');
    fireEvent.click(within(within(box).getByTestId('pending-correction-3')).getByText('批准'));
    expect((await screen.findByTestId('gmv-correction-5')).textContent).toContain('一笔放款重复计入成交额');
  });

  it('提交带差额（元换成分）；批准待批的后重新读报表，说明挂在那个月上', async () => {
    const calls: Call[] = [];
    open(calls, true);
    const box = await screen.findByLabelText('更正说明');
    fireEvent.change(within(box).getByLabelText('更正哪个月'), { target: { value: '2026-07' } });
    fireEvent.change(within(box).getByLabelText('差额（元，可为负）'), { target: { value: '-12.5' } });
    fireEvent.change(within(box).getByPlaceholderText('哪里错、为什么'), { target: { value: '七月佣金笔数少记一笔' } });
    fireEvent.click(within(box).getByText('提交更正说明'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/admin/platform-finance/corrections')?.body)
      .toEqual({ period: '2026-07', note: '七月佣金笔数少记一笔', amount_delta_cents: -1250 }));
    expect((await within(box).findByRole('status')).textContent).toContain('批准前不出现在报表上');
    const row = within(box).getByTestId('pending-correction-3');
    const periodsBefore = calls.filter((c) => c.path === '/admin/platform-finance/periods').length;
    fireEvent.click(within(row).getByText('批准'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/admin/platform-finance/corrections/3/approve')).toBe(true));
    await waitFor(() => expect(calls.filter((c) => c.path === '/admin/platform-finance/periods').length).toBeGreaterThan(periodsBefore));
    expect((await screen.findByTestId('correction-3')).textContent).toContain('一笔补贴误记为其他调整');
    await waitFor(() => expect(within(box).queryByTestId('pending-correction-3')).toBeNull());
  });
});
