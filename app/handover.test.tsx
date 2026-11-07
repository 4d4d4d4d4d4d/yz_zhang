// SCN-205（330 号 spec）App 上的账号交接清单：执行方登记；发单人确认「已在我名下」；一项都没有时发单人看不到。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { HandoverList } from './handover';

type Call = { method: string; path: string; body: unknown };
const A = { id: 1, kind: 'domain', name: 'xiaodian.com', note: '', created_at: '2026-10-28T00:00:00Z', confirmed_at: null };

function client(list: unknown[], after: unknown[], calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'GET' ? list : after) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SCN-205 App 账号交接清单', () => {
  it('执行方：没写账号不发；选小程序登记', async () => {
    const calls: Call[] = [];
    render(<HandoverList client={client([], [{ ...A, kind: 'miniapp', name: '小店点单' }], calls)} contractId={3} isExecutor live />);
    fireEvent.press(await screen.findByText('登记一项'));
    expect(await screen.findByText(/写上账号是什么/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.press(screen.getByText('小程序'));
    fireEvent.changeText(screen.getByLabelText('账号'), '小店点单');
    fireEvent.press(screen.getByText('登记一项'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ kind: 'miniapp', name: '小店点单', note: '' }));
    expect(screen.queryByText('已在我名下')).toBeNull();
  });

  it('发单人：托管期间也只能确认，不能登记与删除', async () => {
    const calls: Call[] = [];
    render(<HandoverList client={client([A], [{ ...A, confirmed_at: '2026-10-28T02:00:00Z' }], calls)} contractId={3} isRequester live />);
    expect(await screen.findByText('1 项账号里还有 1 项没确认在发单人名下')).toBeTruthy();
    expect(screen.queryByText('登记一项')).toBeNull();
    expect(screen.queryByText('删掉')).toBeNull();
    fireEvent.press(screen.getByText('已在我名下'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/contracts/3/handover/1/confirm')).toBe(true));
    expect(await screen.findByText('1 项账号都已确认在发单人名下')).toBeTruthy();
  });

  it('发单人：一项都没有就不出这一块', async () => {
    const calls: Call[] = [];
    render(<HandoverList client={client([], [], calls)} contractId={3} isRequester live />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByText('账号交接')).toBeNull();
  });
});
