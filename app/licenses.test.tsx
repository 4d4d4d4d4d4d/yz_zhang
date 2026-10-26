// SCN-202（329 号 spec）App 上的授权清单：执行方登记、删掉；发单人只看；一项都没有时发单人看不到这一块。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { LicensesList } from './licenses';

type Call = { method: string; path: string; body: unknown };
const ITEM = { id: 4, kind: 'font', title: '思源黑体', source: '开源 OFL', scope: '', created_at: '2026-10-26T00:00:00Z' };

function client(list: unknown[], after: unknown[], calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'GET' ? list : after) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SCN-202 App 授权清单', () => {
  it('执行方：没写来源不发；选字体、写全了登记；删掉', async () => {
    const calls: Call[] = [];
    render(<LicensesList client={client([], [ITEM], calls)} contractId={3} isExecutor live />);
    fireEvent.changeText(await screen.findByLabelText('名称'), '思源黑体');
    fireEvent.press(screen.getByText('登记一项'));
    expect(await screen.findByText(/写上名称和授权来源/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.press(screen.getByText('字体'));
    fireEvent.changeText(screen.getByLabelText('授权来源'), '开源 OFL');
    fireEvent.press(screen.getByText('登记一项'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body)
      .toEqual({ kind: 'font', title: '思源黑体', source: '开源 OFL', scope: '' }));
    expect(await screen.findByText('字体：思源黑体——开源 OFL')).toBeTruthy();
    fireEvent.press(screen.getByText('删掉'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/contracts/3/licenses/4')).toBe(true));
  });

  it('发单人：托管期间也只看', async () => {
    render(<LicensesList client={client([ITEM], [], [])} contractId={3} live />);
    expect(await screen.findByText('字体：思源黑体——开源 OFL')).toBeTruthy();
    expect(screen.queryByText('登记一项')).toBeNull();
    expect(screen.queryByText('删掉')).toBeNull();
  });

  it('发单人：一项都没有就不出这一块', async () => {
    const calls: Call[] = [];
    render(<LicensesList client={client([], [], calls)} contractId={3} />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByText('授权清单')).toBeNull();
  });
});
