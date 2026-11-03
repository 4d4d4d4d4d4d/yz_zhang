// TEAM-056（370 号 spec）：团队预算池按每月几号重置——App 上看得到，所有者改得了，乱填会被说清楚。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { SubScreenHost } from './TeamCoopDev';

type Call = { method: string; path: string; body: unknown };

function open(role: string, extra: Record<string, unknown> = {}, calls: Call[] = []) {
  const TEAM = {
    id: 5, name: '某某科技', company_name: '', tax_number: '', verify_status: 'none', verify_reason: '', active: true,
    my_role: role, balance_cents: 500000, my_spend_limit_cents: 100000, my_month_spent_cents: 0,
    monthly_budget_cents: 300000, month_spent_cents: 50000, invoice_block: '', members: [],
    budget_cycle_day: 25, budget_cycle_starts_at: '2026-10-25T00:00:00+00:00', budget_cycle_resets_at: '2026-11-25T12:00:00+00:00',
    ...extra,
  };
  const routes: Record<string, unknown> = { '/teams/mine': [TEAM], '/teams/5': TEAM, '/teams/5/spends': [],
    '/teams/5/budget': { id: 5, monthly_budget_cents: 300000, month_spent_cents: 50000, budget_cycle_day: 10 } };
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(routes[path] ?? []) };
  }) as unknown as typeof fetch;
  render(<SubScreenHost client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })} screen="teams" onBack={() => undefined} />);
  return calls;
}

describe('TEAM-056 App 预算池账期', () => {
  it('所有者改账期：只收 1~28，金额照旧带上', async () => {
    const calls = open('owner');
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));
    const line = await screen.findByLabelText('预算池账期');
    expect(String(line.props.children.join(''))).toContain('每月 25 日重置');
    fireEvent.changeText(screen.getByPlaceholderText('每月几号重置（1~28）'), '31');
    fireEvent.press(screen.getByText('改账期'));
    expect(await screen.findByText('账期填 1~28 的整数：29~31 号不是每个月都有，要月底结账的选 28')).toBeTruthy();
    expect(calls.some((c) => c.path === '/teams/5/budget')).toBe(false);
    fireEvent.changeText(screen.getByPlaceholderText('每月几号重置（1~28）'), '10');
    fireEvent.press(screen.getByText('改账期'));
    await waitFor(() => expect(calls.find((c) => c.path === '/teams/5/budget')?.body).toEqual({ monthly_budget_cents: 300000, budget_cycle_day: 10 }));
    expect(await screen.findByText('预算池改为每月 10 日重置')).toBeTruthy();
  });

  it('成员只看不改；老服务端没有账期字段时不显示', async () => {
    open('member');
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));
    await screen.findByLabelText('预算池账期');
    expect(screen.queryByText('改账期')).toBeNull();
  });

  it('老服务端', async () => {
    open('owner', { budget_cycle_day: undefined, budget_cycle_resets_at: undefined });
    await waitFor(() => expect(screen.getByText('某某科技')).toBeTruthy());
    fireEvent.press(screen.getByText('某某科技'));
    await screen.findByText(/团队本月预算池/);
    expect(screen.queryByLabelText('预算池账期')).toBeNull();
    expect(screen.queryByText('改账期')).toBeNull();
  });
});
