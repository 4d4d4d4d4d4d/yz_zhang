// FIN-062（242 号 spec）后台「按期间」下的「成交额与代扣税」：草稿提示、每期一行、口径可展开；切季度重新读。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '财务', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['finance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const ROW = (period: string, gmv: number) => ({ period, start: '', end: '', gmv_cents: gmv, release_count: 2, executor_net_cents: gmv - 1500,
  fee_cents: 1500, dispute_split_cents: 3000, refund_cents: 7000, withheld_cents: 900, withheld_count: 2, withheld_people: 2,
  withheld_income_cents: 13500, remitted_cents: 600, tax_pending_cents: 300 });

describe('FIN-062 成交额与代扣税', () => {
  it('写明是口径草稿；每期一行；口径逐条；切季度带上粒度', async () => {
    localStorage.setItem('token', 'tok');
    const calls: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      const full = String(url).replace(/^.*\/api\/v1/, '');
      const path = full.split('?')[0];
      calls.push(full);
      const body: unknown = path === '/users/me' ? ADMIN
        : path === '/admin/platform-finance' ? { balance_cents: 0, total_fee_cents: 0, settled_cents: 0, fee_count: 0 }
        : path === '/admin/platform-finance/gmv-tax' ? { granularity: 'month', periods: [{ ...ROW('2026-08', 15000), closed: true, late_gmv_cents: 1000, late_withheld_cents: 50 }, ROW('2026-09', 2000)],
            basis: ['成交额（GMV）按放款算', '代扣税额按税款专户的流水算'], draft_note: '口径草稿：对外申报、报送前请财税负责人确认口径' }
        : path === '/admin/platform-finance/gmv-tax/export' ? { filename: 'gmv-tax-2026-08-2026-09.csv', rows: 2, timezone: '北京时间（UTC+8）', csv: '期间\n' }
        : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
    }) as unknown as typeof fetch;
    render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
    const box = await screen.findByLabelText('成交额与代扣税');
    expect(box.textContent).toContain('请财税负责人确认口径');
    const aug = within(box).getByTestId('gmv-2026-08');
    expect(aug.textContent).toContain('¥150.00');
    expect(aug.textContent).toContain('¥9.00（2 笔）');
    expect(aug.textContent).toContain('¥3.00');
    expect(aug.textContent).toContain('已锁');
    expect(aug.textContent).toContain('锁账后又记进成交额 ¥10.00、代扣 ¥0.50，未计入上面的数');
    expect(within(box).getByTestId('gmv-2026-09').textContent).not.toContain('已锁');
    expect(box.textContent).toContain('成交额（GMV）按放款算');
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    fireEvent.click(within(box).getByText('导出成交额与代扣税 CSV'));
    await waitFor(() => expect(calls.some((c) => c.startsWith('/admin/platform-finance/gmv-tax/export') && c.includes('granularity=month'))).toBe(true));
    expect((await within(box).findByRole('status')).textContent).toContain('已导出 2 个期间');
    fireEvent.change(screen.getByLabelText('期间粒度'), { target: { value: 'quarter' } });
    await waitFor(() => expect(calls.some((c) => c.startsWith('/admin/platform-finance/gmv-tax') && c.includes('granularity=quarter'))).toBe(true));
  });
});
