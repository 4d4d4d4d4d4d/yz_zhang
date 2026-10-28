// SCN-205（330 号 spec）账号交接清单：执行方登记、删未确认的；发单人逐项确认「已在我名下」；没确认完标红。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import HandoverBlock from './Handover';
import { AppProvider } from './store';

type Call = { method: string; path: string; body: unknown };
const A = { id: 1, kind: 'domain', name: 'xiaodian.com', note: '', created_at: '2026-10-28T00:00:00Z', confirmed_at: null };
const B = { id: 2, kind: 'miniapp', name: '小店点单', note: '已转主体', created_at: '2026-10-28T00:00:00Z', confirmed_at: '2026-10-28T01:00:00Z' };

function mount(list: unknown[], calls: Call[], props: { isExecutor: boolean; isRequester: boolean; live: boolean }, after: unknown[] = list) {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'GET' ? list : after), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><HandoverBlock contractId={3} {...props} /></AppProvider>);
}

describe('SCN-205 账号交接清单', () => {
  it('执行方：没写账号不发；登记一项；已确认的不能删', async () => {
    const calls: Call[] = [];
    mount([B], calls, { isExecutor: true, isRequester: false, live: true }, [A, B]);
    const box = await screen.findByLabelText('账号交接');
    expect(within(box).queryByText('删掉')).toBeNull();
    fireEvent.click(within(box).getByText('登记一项'));
    expect(await within(box).findByText(/写上账号是什么/)).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.change(within(box).getByLabelText('账号'), { target: { value: ' xiaodian.com ' } });
    fireEvent.click(within(box).getByText('登记一项'));
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ kind: 'domain', name: 'xiaodian.com', note: '' }));
    expect(await within(box).findByText('删掉')).toBeTruthy();
    expect(within(box).queryByText('已在我名下')).toBeNull();
  });

  it('发单人：没确认完标出来；点「已在我名下」', async () => {
    const calls: Call[] = [];
    mount([A, B], calls, { isExecutor: false, isRequester: true, live: true }, [{ ...A, confirmed_at: '2026-10-28T02:00:00Z' }, B]);
    expect((await screen.findByTestId('handover-summary')).textContent).toBe('2 项账号里还有 1 项没确认在发单人名下');
    expect(screen.queryByText('删掉')).toBeNull();
    fireEvent.click(screen.getByText('已在我名下'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/contracts/3/handover/1/confirm')).toBe(true));
    expect((await screen.findByTestId('handover-summary')).textContent).toBe('2 项账号都已确认在发单人名下');
  });

  it('发单人：一项都没登记就不出这一块', async () => {
    const calls: Call[] = [];
    mount([], calls, { isExecutor: false, isRequester: true, live: true });
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByLabelText('账号交接')).toBeNull();
  });
});
