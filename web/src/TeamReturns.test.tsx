// TEAM-070（226 号 spec）钱包页「团队拨款」：列出能退的、按填的金额退、带幂等键，退完写明结果。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppProvider } from './store';
import { TeamReturns } from './TeamReturns';

const ROW = { id: 5, team_id: 9, team_name: '某某科技', purpose: '活动物料', amount_cents: 8000, returned_cents: 0, returnable_cents: 8000, created_at: '' };
type Call = { method: string; path: string; body: unknown; key?: string };

function open(calls: Call[], rows: unknown[], fail = false) {
  localStorage.setItem('token', 'tok');
  let listed = 0;
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string; headers?: Record<string, string> }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null, key: init?.headers?.['Idempotency-Key'] });
    if (path === '/teams/returnable-spends') { listed += 1; return { ok: true, status: 200, text: async () => JSON.stringify(listed === 1 ? rows : []) }; }
    if (path === '/teams/9/spends/5/return') {
      if (fail) return { ok: false, status: 400, text: async () => JSON.stringify({ detail: { code: 'return_insufficient_balance', message: '你的可用余额只有 ¥10.00：钱可能在托管或冻结里，等任务结算或退款到账后再退' } }) };
      return { ok: true, status: 200, text: async () => JSON.stringify({ id: 5, returned_cents: 3000, returnable_cents: 5000, available_cents: 0 }) };
    }
    return { ok: true, status: 200, text: async () => JSON.stringify(path === '/users/me' ? { id: 2, nickname: '员工' } : []) };
  }) as unknown as typeof fetch;
  const onChanged = vi.fn();
  render(<MemoryRouter><AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><TeamReturns onChanged={onChanged} /></AppProvider></MemoryRouter>);
  return onChanged;
}

describe('TEAM-070 钱包页团队拨款', () => {
  it('列出能退的；按填的金额退、带幂等键；退完写明还能退多少并刷新钱包', async () => {
    const calls: Call[] = [];
    const onChanged = open(calls, [ROW]);
    expect((await screen.findByTestId('team-return-5')).textContent).toContain('某某科技 · 支出 #5（活动物料）：拨给你 ¥80.00，最多还能退 ¥80.00');
    expect(screen.getByText(/平台分不出用掉了多少/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('退回金额 5'), { target: { value: '30' } });
    fireEvent.click(screen.getByText('退回团队'));
    expect((await screen.findByRole('status')).textContent).toBe('已退回 ¥30.00，这笔还能退 ¥50.00');
    const hit = calls.find((c) => c.path === '/teams/9/spends/5/return')!;
    expect(hit.body).toEqual({ amount_cents: 3000 });
    expect(hit.key).toMatch(/^[0-9a-f]{32}$/);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('没有能退的不显示', async () => {
    open([], []);
    await waitFor(() => expect(screen.queryByLabelText('团队拨款')).toBeNull());
  });

  it('余额不够：显示为什么、怎么办', async () => {
    open([], [ROW], true);
    fireEvent.click(await screen.findByText('退回团队'));
    expect(await screen.findByText(/等任务结算或退款到账后再退/)).toBeTruthy();
  });
});
