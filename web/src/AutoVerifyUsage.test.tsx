// AGT-073（224 号 spec）后台平台指标里写明自费核验用了多少；快用完、用完了标出来。
import { PlatformClient } from '@platform/core';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { AppProvider } from './store';

const ADMIN = { id: 1, phone: '138****0001', nickname: '运营', bio: '', city: '', lat: null, lng: null, skills: [], interests: [],
  is_verified: true, is_admin: true, admin_roles: [], credit_score: 100, rating_avg: 0, tasks_completed: 0,
  certifications: [], credit_level: '普通', referral_code: 'r1' };
const METRICS = { total_users: 3, verified_users: 1, total_tasks: 2, published_tasks: 1, completed_tasks: 1,
  closed_loop_rate: 0.5, dispute_count: 0, gmv_cents: 0, fee_income_cents: 0 };

function open(metrics: unknown) {
  localStorage.setItem('token', 'tok');
  const fetchImpl = vi.fn(async (url: string) => {
    const p = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const body = p === '/users/me' ? ADMIN : p === '/admin/metrics' ? metrics
      : p === '/admin/aml/activities' ? { items: [], note: '' } : [];
    return { ok: true, status: 200, text: async () => JSON.stringify(body), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<MemoryRouter initialEntries={['/admin']}><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><App /></AppProvider></MemoryRouter>);
}

describe('AGT-073 自费核验用量', () => {
  it('没到八成：灰字报数', async () => {
    open({ ...METRICS, auto_verify: { used_24h: 3, daily_max: 50, remaining: 47, fee_cents_24h: 1500, skipped_24h: 0 } });
    const p = await screen.findByTestId('auto-verify-usage');
    expect(p.textContent).toBe('近 24 小时平台自费核验 3 / 50 张（¥15.00）');
    expect(p.className).toBe('muted');
  });

  it('用完了：标红，写明之后不再自动请人看、漏了几次', async () => {
    open({ ...METRICS, auto_verify: { used_24h: 50, daily_max: 50, remaining: 0, fee_cents_24h: 25000, skipped_24h: 2 } });
    const p = await screen.findByTestId('auto-verify-usage');
    expect(p.className).toBe('error');
    expect(p.textContent).toContain('额度已用完');
    expect(p.textContent).toContain('（已有 2 次）');
  });

  it('旧服务端没给这一项：不显示，不报错', async () => {
    open(METRICS);
    expect(await screen.findByText('平台指标')).toBeTruthy();
    expect(screen.queryByTestId('auto-verify-usage')).toBeNull();
  });
});
