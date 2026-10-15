// SC-004 / SC-014 App 上的分期（146 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, type Contract } from '@platform/core';
import { MilestonesBlock } from './milestones';

type Call = { method: string; path: string; body: unknown };
function makeClient(routes: Record<string, unknown>, calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : {}) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const C = (statuses: string[]) => ({
  id: 7, task_id: 3, requester_id: 1, executor_id: 2, status: 'funded', frozen: false, amount_cents: 90000, released_cents: 0,
  milestones: statuses.map((st, i) => ({ idx: i + 1, title: ['设计', '施工', '收尾'][i], amount_cents: [20000, 30000, 40000][i], status: st })),
}) as unknown as Contract;

describe('SC-014 App 上的分期', () => {
  it('发布方：两期已交付时可以一次只放这两期，先列清楚再确认；没交付的不放', async () => {
    const calls: Call[] = [];
    const onChanged = jest.fn();
    const client = makeClient({ '/contracts/7/milestones/release-delivered': C(['released', 'released', 'pending']) }, calls);
    render(<MilestonesBlock client={client} contract={C(['delivered', 'delivered', 'pending'])} isCreator isExecutor={false} onChanged={onChanged} />);
    expect(screen.getAllByText('验收本期')).toHaveLength(2);
    fireEvent.press(screen.getByText('放款已交付的 2 期（共 ¥500.00）'));
    expect(screen.getByText('只放这 2 期已交付的，合计 ¥500.00')).toBeTruthy();
    expect(screen.getByText('还没交付的期不会动。')).toBeTruthy();
    expect(calls).toHaveLength(0);
    fireEvent.press(screen.getByText('确认放款'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(calls[0]).toEqual({ method: 'POST', path: '/contracts/7/milestones/release-delivered', body: { idxs: [1, 2], expected_total_cents: 50000 } });
  });

  it('执行方：逐期交付；只有一期待验收时不出批量按钮；冻结时什么都不能点', async () => {
    const calls: Call[] = [];
    const client = makeClient({ '/contracts/7/milestones/3/deliver': C(['released', 'delivered', 'delivered']) }, calls);
    const { rerender } = render(<MilestonesBlock client={client} contract={C(['released', 'delivered', 'pending'])} isCreator={false} isExecutor onChanged={() => undefined} />);
    fireEvent.press(screen.getByText('交付本期'));
    await waitFor(() => expect(calls.some((c) => c.path === '/contracts/7/milestones/3/deliver')).toBe(true));
    rerender(<MilestonesBlock client={client} contract={C(['released', 'delivered', 'pending'])} isCreator isExecutor={false} onChanged={() => undefined} />);
    expect(screen.queryByText(/放款已交付的/)).toBeNull();
    rerender(<MilestonesBlock client={client} contract={{ ...C(['delivered', 'delivered', 'pending']), frozen: true }} isCreator isExecutor={false} onChanged={() => undefined} />);
    expect(screen.queryByText('验收本期')).toBeNull();
    expect(screen.queryByText(/放款已交付的/)).toBeNull();
  });
});
