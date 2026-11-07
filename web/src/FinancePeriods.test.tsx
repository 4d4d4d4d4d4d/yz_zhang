// FIN-061 按期间的平台财务（144 号 spec）：按月 / 按季度切换，期末对不上要标出来，导出说清时区并进审计。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '财务', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: ['finance'], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const P = (period: string, fee: number, balanced = true) => ({ period, start: '', end: '', fee_cents: fee, fee_count: 2, settled_cents: 800,
  subsidy_cents: 0, other_cents: 0, net_cents: fee - 800, opening_cents: 0, closing_cents: 5500, balanced });

function open(urls: string[]) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const full = String(url).replace(/^.*\/api\/v1/, '');
    urls.push(full);
    const path = full.split('?')[0];
    const body: unknown = path === '/users/me' ? ADMIN
      : path === '/admin/platform-finance' ? { balance_cents: 5500, total_fee_cents: 9000, settled_cents: 800, fee_count: 4 }
      : path === '/admin/platform-finance/periods' ? { granularity: full.includes('quarter') ? 'quarter' : 'month',
          periods: full.includes('quarter') ? [P('2026-Q3', 9000)] : [P('2026-08', 1000), P('2026-09', 500, false)] }
      : path === '/admin/platform-finance/periods/export' ? { filename: 'f.csv', rows: 12, timezone: '北京时间 UTC+8', csv: 'x' }
      : path === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('FIN-061 按期间的平台财务', () => {
  it('按月显示（新的在上），期末对不上的期间标出来；切到按季度', async () => {
    const urls: string[] = [];
    open(urls);
    const box = await screen.findByLabelText('按期间');
    await waitFor(() => expect(within(box).getAllByRole('row').length).toBe(3));
    const rows = within(box).getAllByRole('row');
    expect(rows[1].textContent).toContain('2026-09');
    expect(rows[1].textContent).toContain('期末与期初对不上');
    expect(rows[2].textContent).not.toContain('对不上');
    fireEvent.change(within(box).getByLabelText('期间粒度'), { target: { value: 'quarter' } });
    await waitFor(() => expect(within(box).getByText('2026-Q3')).toBeTruthy());
    expect(urls).toContain('/admin/platform-finance/periods?granularity=quarter');
  });

  it('导出说清时区并说明已进审计', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:x');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    open([]);
    const box = await screen.findByLabelText('按期间');
    fireEvent.click(within(box).getByText('导出 CSV'));
    expect((await within(box).findByRole('status')).textContent).toBe('已导出 12 个期间（起止时间为北京时间 UTC+8）。导出已记入审计。');
  });
});
