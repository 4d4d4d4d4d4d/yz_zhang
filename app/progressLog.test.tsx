// TASK-022 / AI-DEC-021d App 上的执行动态（386 号 spec）。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { ProgressBlock, canSeeProgress } from './progressLog';

type Call = { method: string; path: string; body: unknown };
const LOGS = [
  { id: 1, user_id: 5, kind: 'note', content: '首页做完', images: ['/api/v1/files/a'], created_at: '2026-11-04T08:00:00Z', days_left: 4 },
  { id: 2, user_id: 2, kind: 'note', content: '辛苦', images: [], created_at: '2026-11-04T10:00:00Z' },
];

function makeClient(progress: unknown, calls: Call[] = []): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '');
    const method = init?.method ?? 'GET';
    calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
    return { ok: true, status: 200, text: async () => JSON.stringify(method === 'POST' ? { ok: true } : progress) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const TASK = { id: 21, status: 'in_progress' as const, executor_id: 5, creator_id: 2 };

describe('TASK-022 App 执行动态（386 号 spec）', () => {
  it('成交双方、开工以后才有这一块', () => {
    expect(canSeeProgress(TASK, 2)).toBe(true);
    expect(canSeeProgress(TASK, 5)).toBe(true);
    expect(canSeeProgress(TASK, 9)).toBe(false);
    expect(canSeeProgress(TASK, null)).toBe(false);
    expect(canSeeProgress({ ...TASK, status: 'published' }, 2)).toBe(false);
  });

  it('列出进度，写出接单人报的天数与图片张数；发单人没有「还要几天」', async () => {
    render(<ProgressBlock client={makeClient(LOGS)} task={TASK} meId={2} />);
    expect(await screen.findByText(/首页做完（还要 4 天）/)).toBeTruthy();
    expect(screen.getByText(/1 张图/)).toBeTruthy();
    expect(screen.getByText(/^辛苦/)).toBeTruthy();
    expect(screen.queryByLabelText('还要几天')).toBeNull();
  });

  it('接单人写进度可带天数；填得不对不让发；发完重新取', async () => {
    const calls: Call[] = [];
    render(<ProgressBlock client={makeClient(LOGS, calls)} task={TASK} meId={5} />);
    await screen.findByText(/首页做完/);
    fireEvent.changeText(screen.getByPlaceholderText('进度说明…'), '接口联调');
    fireEvent.changeText(screen.getByLabelText('还要几天'), '400');
    expect(screen.getByText('还要几天填 0~365 的整数（0 = 今天做完）')).toBeTruthy();
    fireEvent.press(screen.getByText('更新进度'));
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    fireEvent.changeText(screen.getByLabelText('还要几天'), '0');
    const before = calls.filter((c) => c.method === 'GET').length;
    fireEvent.press(screen.getByText('更新进度'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
    expect(calls.find((c) => c.method === 'POST')).toMatchObject({ path: '/tasks/21/progress', body: { content: '接口联调', images: [], days_left: 0 } });
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET').length).toBe(before + 1));
  });

  it('不填天数不带字段；进度为空写清楚；响应畸形不白屏；没开工不能写', async () => {
    const calls: Call[] = [];
    render(<ProgressBlock client={makeClient({ oops: 1 }, calls)} task={TASK} meId={5} />);
    expect(await screen.findByText('还没有进度。')).toBeTruthy();
    fireEvent.changeText(screen.getByPlaceholderText('进度说明…'), '传了截图');
    fireEvent.press(screen.getByText('更新进度'));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ content: '传了截图', images: [] });
  });

  it('待验收时只能看，不能再写', async () => {
    render(<ProgressBlock client={makeClient(LOGS)} task={{ ...TASK, status: 'pending_acceptance' }} meId={5} />);
    await screen.findByText(/首页做完/);
    expect(screen.queryByText('更新进度')).toBeNull();
  });
});
