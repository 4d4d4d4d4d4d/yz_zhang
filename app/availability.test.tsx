// SPACE-023 App 上设置可用时段与少量接单（118 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { AvailabilityScreen } from './availability';

function makeClient(me: Record<string, unknown>, calls: Array<{ method: string; path: string; body?: unknown }>) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : undefined });
    return { ok: true, status: 200, text: async () => JSON.stringify(me) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SPACE-023 App 上的可用时间', () => {
  it('勾一天、改时间、保存；时间写错先拦下，不发请求', async () => {
    const calls: Array<{ method: string; path: string; body?: unknown }> = [];
    render(<AvailabilityScreen client={makeClient({ weekly_slots: [], limited_capacity: false }, calls)} />);
    fireEvent.press(await screen.findByText('☐ 周六'));
    fireEvent.changeText(screen.getByLabelText('周六结束'), '8点');
    fireEvent.press(screen.getByText('保存可用时间'));
    expect(await screen.findByText('时间格式为 HH:MM，且结束要晚于开始')).toBeTruthy();
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('周六结束'), '12:00');
    fireEvent.press(screen.getByText('保存可用时间'));
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')?.body)
      .toEqual({ weekly_slots: [{ d: 5, from: '09:00', to: '12:00' }], limited_capacity: false }));
  });
});
