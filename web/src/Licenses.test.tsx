// SCN-202（329 号 spec）交付附授权清单：执行方托管期间逐项登记、删错的；发单人只看；没登记过的发单人看不到这一块。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LicensesBlock from './Licenses';
import { AppProvider } from './store';

type Call = { method: string; path: string; body: unknown };
const ITEM = { id: 4, kind: 'music', title: '《夏日》', source: '某曲库商用授权', scope: '仅限抖音', created_at: '2026-10-26T00:00:00Z' };

function mount(list: unknown[], calls: Call[], props: { isExecutor: boolean; live: boolean }, after: unknown[] = list) {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'GET' ? list : after), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><LicensesBlock contractId={3} {...props} /></AppProvider>);
}

describe('SCN-202 授权清单', () => {
  it('执行方：没写来源不发；写全了登记一项，删掉登记错的', async () => {
    const calls: Call[] = [];
    mount([], calls, { isExecutor: true, live: true }, [ITEM]);
    const box = await screen.findByLabelText('授权清单');
    fireEvent.change(within(box).getByLabelText('名称'), { target: { value: '《夏日》' } });
    fireEvent.click(within(box).getByText('登记一项'));
    expect(await within(box).findByText(/写上名称和授权来源/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.change(within(box).getByLabelText('授权来源'), { target: { value: ' 某曲库商用授权 ' } });
    fireEvent.change(within(box).getByLabelText('授权范围'), { target: { value: '仅限抖音' } });
    fireEvent.click(within(box).getByText('登记一项'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/contracts/3/licenses')?.body)
      .toEqual({ kind: 'music', title: '《夏日》', source: '某曲库商用授权', scope: '仅限抖音' }));
    expect(await within(box).findByText(/音乐：《夏日》——某曲库商用授权（仅限抖音）/)).toBeTruthy();
    fireEvent.click(within(box).getByText('删掉'));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/contracts/3/licenses/4')).toBe(true));
  });

  it('发单人：只看，没有登记与删除', async () => {
    mount([ITEM], [], { isExecutor: false, live: true });
    expect(await screen.findByText(/音乐：《夏日》/)).toBeTruthy();
    expect(screen.queryByText('登记一项')).toBeNull();
    expect(screen.queryByText('删掉')).toBeNull();
  });

  it('发单人：一项都没登记就不出这一块', async () => {
    const calls: Call[] = [];
    mount([], calls, { isExecutor: false, live: true });
    await waitFor(() => expect(calls.some((c) => c.path === '/contracts/3/licenses')).toBe(true));
    expect(screen.queryByLabelText('授权清单')).toBeNull();
  });
});
