// SCN-219 App 上的发单复核（336 号 spec）：发布被拦下时出现「申请人工复核」，原样带上标题；
// 写够一句话才能交；交了之后发布页下面列出「我的发单复核」。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { PublishScreen } from './App';

type Call = { method: string; path: string; body: Record<string, unknown> | null };
const ROW = { id: 5, kind: 'fake_review', kind_label: '刷单虚假评价', title: '探店合作', description: '', explanation: '写明合作按真实体验写',
  status: 'pending', decision_note: '', task_id: null, created_at: '2026-10-30T00:00:00Z', decided_at: null };

function makeClient(calls: Call[], mine: unknown[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    if (method === 'POST' && path === '/tasks') {
      return { ok: false, status: 400, text: async () => JSON.stringify({ detail: { code: 'fake_review', message: '平台不承接刷单' } }) };
    }
    if (method === 'POST' && path === '/tasks/errand-reviews') return { ok: true, status: 200, text: async () => JSON.stringify(ROW) };
    if (method === 'GET' && path === '/tasks/errand-reviews') {
      return { ok: true, status: 200, text: async () => JSON.stringify(calls.some((c) => c.method === 'POST' && c.path === '/tasks/errand-reviews') ? [ROW] : mine) };
    }
    return { ok: true, status: 200, text: async () => '[]' };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('SCN-219 发单复核', () => {
  it('被拦下才出现申请入口；写够一句话才能交；交了列进「我的发单复核」', async () => {
    const calls: Call[] = [];
    render(<PublishScreen client={makeClient(calls)} onDone={jest.fn()} />);
    expect(screen.queryByText('觉得拦错了？申请人工复核')).toBeNull();
    fireEvent.changeText(screen.getByPlaceholderText(/标题/), '探店合作');
    fireEvent.press(screen.getAllByText(/^○ /)[0]);
    fireEvent.press(screen.getByText('发布（线上任务）'));
    fireEvent.press(await screen.findByText('觉得拦错了？申请人工复核'));
    fireEvent.changeText(screen.getByLabelText('复核说明'), '误拦');
    fireEvent.press(screen.getByText('提交复核'));
    expect(calls.some((c) => c.method === 'POST' && c.path === '/tasks/errand-reviews')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('复核说明'), '写明合作按真实体验写');
    fireEvent.press(screen.getByText('提交复核'));
    await screen.findByText(/已申请复核/);
    expect(calls.find((c) => c.method === 'POST' && c.path === '/tasks/errand-reviews')!.body)
      .toEqual({ title: '探店合作', description: '', explanation: '写明合作按真实体验写' });
    await waitFor(() => expect(screen.getByLabelText('我的发单复核')).toBeTruthy());
  });

  it('没申请过的不显示「我的发单复核」；维持的写出理由', async () => {
    const calls: Call[] = [];
    const { unmount } = render(<PublishScreen client={makeClient(calls)} onDone={jest.fn()} />);
    await waitFor(() => expect(calls.some((c) => c.path === '/tasks/errand-reviews')).toBe(true));
    expect(screen.queryByLabelText('我的发单复核')).toBeNull();
    unmount();
    render(<PublishScreen client={makeClient([], [{ ...ROW, status: 'rejected', decision_note: '就是刷好评' }])} onDone={jest.fn()} />);
    expect(await screen.findByText(/就是刷好评/)).toBeTruthy();
  });
});
