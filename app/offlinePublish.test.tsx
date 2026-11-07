// APP-102（318 号 spec）App 发线下单：勾「线下（要上门）」，写城市与地址提示、取一次当前位置；拿不到定位时说清，不乱发。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { PublishScreen } from './App';

type Call = { method: string; path: string; body: unknown };
function makeClient(calls: Call[]) {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'POST' && path === '/tasks' ? { id: 80, title: 'x' } : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('APP-102 App 发线下单', () => {
  it('写城市、地址提示、取位置后按线下单发；城市与位置都要有', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    const locate = jest.fn(async () => ({ lat: 31.23, lng: 121.47 }));
    render(<PublishScreen client={makeClient(calls)} onDone={done} category="老人助浴" locate={locate} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '给我爸上门助浴');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByLabelText('线下（要上门）'));
    fireEvent.press(screen.getByText('发布（线下任务）'));
    expect(await screen.findByText('线下单要写城市、取一次当前位置')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('城市'), ' 上海 ');
    fireEvent.changeText(screen.getByLabelText('地址提示'), ' 徐汇区某小区 ');
    fireEvent.press(screen.getByText('用我现在的位置'));
    expect(await screen.findByText('已取到位置，重新取')).toBeTruthy();
    fireEvent.press(screen.getByText('发布（线下任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body).toMatchObject(
      { is_remote: false, city: '上海', address_hint: '徐汇区某小区', lat: 31.23, lng: 121.47, category: '老人助浴' });
  });

  it('拿不到定位时说清怎么办；不勾线下照旧发线上单', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient(calls)} onDone={done} locate={async () => ({ lat: 0, lng: 0 })} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '帮忙取快递');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByLabelText('线下（要上门）'));
    fireEvent.press(screen.getByText('用我现在的位置'));
    expect(await screen.findByText('没拿到定位：请在系统设置里允许定位后再取，或者到了地方再发')).toBeTruthy();
    fireEvent.press(screen.getByLabelText('线下（要上门）'));
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect(body.is_remote).toBe(true);
    expect('lat' in body || 'city' in body).toBe(false);
  });

  it('取过位置又取消「线下」：按线上单发，不带位置', async () => {
    const calls: Call[] = [];
    const done = jest.fn();
    render(<PublishScreen client={makeClient(calls)} onDone={done} locate={async () => ({ lat: 31.2, lng: 121.4 })} />);
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '帮忙取快递');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByLabelText('线下（要上门）'));
    fireEvent.press(screen.getByText('用我现在的位置'));
    await screen.findByText('已取到位置，重新取');
    fireEvent.press(screen.getByLabelText('线下（要上门）'));
    fireEvent.press(screen.getByText('发布（线上任务）'));
    await waitFor(() => expect(done).toHaveBeenCalled());
    const body = calls.find((c) => c.method === 'POST' && c.path === '/tasks')!.body as Record<string, unknown>;
    expect(body.is_remote).toBe(true);
    expect('lat' in body).toBe(false);
  });
});
