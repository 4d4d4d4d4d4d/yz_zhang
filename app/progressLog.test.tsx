// TASK-022 / AI-DEC-021d App 上的执行动态（386 号 spec）。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { MAX_PROGRESS_PHOTOS, ProgressBlock, canSeeProgress } from './progressLog';

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
    const body = method !== 'POST' ? progress : path === '/files' ? { url: `/api/v1/files/p${calls.length}`, ref: `p${calls.length}` } : { ok: true };
    return { ok: true, status: 200, text: async () => JSON.stringify(body) };
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

describe('TASK-022c App 写进度拍照留证（388 号 spec）', () => {
  afterEach(() => jest.restoreAllMocks());
  const img = { canceled: false, assets: [{ base64: 'iVBORw0KGgo=', mimeType: 'image/png' }] };

  it('拍照或选图上传后随进度一起提交，提交后清空', async () => {
    jest.spyOn(ImagePicker, 'requestCameraPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    jest.spyOn(ImagePicker, 'launchCameraAsync').mockResolvedValue(img as never);
    jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    jest.spyOn(ImagePicker, 'launchImageLibraryAsync').mockResolvedValue(img as never);
    const calls: Call[] = [];
    render(<ProgressBlock client={makeClient(LOGS, calls)} task={TASK} meId={2} />);
    await screen.findByText(/首页做完/);
    fireEvent.press(screen.getByText('拍照'));
    expect(await screen.findByText('已附 1 张照片')).toBeTruthy();
    fireEvent.press(screen.getByText('从相册选'));
    expect(await screen.findByText('已附 2 张照片')).toBeTruthy();
    const uploads = calls.filter((c) => c.path === '/files');
    expect(uploads).toHaveLength(2);
    expect(uploads[0].body).toEqual({ content_type: 'image/png', data_base64: 'iVBORw0KGgo=' });
    fireEvent.changeText(screen.getByPlaceholderText('进度说明…'), '现场照片');
    fireEvent.press(screen.getByText('更新进度'));
    await waitFor(() => expect(calls.some((c) => c.path === '/tasks/21/progress' && c.method === 'POST')).toBe(true));
    const sent = calls.find((c) => c.path === '/tasks/21/progress' && c.method === 'POST')!.body as { images: string[] };
    expect(sent.images).toHaveLength(2);
    expect(sent.images.every((u) => u.startsWith('/api/v1/files/'))).toBe(true);
    await waitFor(() => expect(screen.queryByText(/已附/)).toBeNull());
  });

  it('没有权限、图太大都说清楚，不上传；可以去掉最后一张', async () => {
    jest.spyOn(ImagePicker, 'requestCameraPermissionsAsync').mockResolvedValue({ status: 'denied' } as never);
    jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    jest.spyOn(ImagePicker, 'launchImageLibraryAsync')
      .mockResolvedValueOnce({ canceled: false, assets: [{ base64: 'A'.repeat(4 * 1024 * 1024), mimeType: 'image/jpeg' }] } as never)
      .mockResolvedValue(img as never);
    const calls: Call[] = [];
    render(<ProgressBlock client={makeClient(LOGS, calls)} task={TASK} meId={5} />);
    await screen.findByText(/首页做完/);
    fireEvent.press(screen.getByText('拍照'));
    expect(await screen.findByText('没有相机权限，请在系统设置里允许后重试')).toBeTruthy();
    fireEvent.press(screen.getByText('从相册选'));
    expect(await screen.findByText('这张图超过 2MB，请拍得近一些或选一张更小的')).toBeTruthy();
    expect(calls.some((c) => c.path === '/files')).toBe(false);
    fireEvent.press(screen.getByText('从相册选'));
    expect(await screen.findByText('已附 1 张照片')).toBeTruthy();
    fireEvent.press(screen.getByText('去掉最后一张'));
    await waitFor(() => expect(screen.queryByText(/已附/)).toBeNull());
  });

  it(`最多 ${MAX_PROGRESS_PHOTOS} 张：满了按钮不能再点`, async () => {
    const perm = jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    const lib = jest.spyOn(ImagePicker, 'launchImageLibraryAsync').mockResolvedValue(img as never);
    render(<ProgressBlock client={makeClient(LOGS)} task={TASK} meId={5} />);
    await screen.findByText(/首页做完/);
    for (let i = 1; i <= MAX_PROGRESS_PHOTOS; i += 1) {
      fireEvent.press(screen.getByText('从相册选'));
      await screen.findByText(new RegExp(`已附 ${i} 张照片`));
    }
    expect(screen.getByText(`已附 ${MAX_PROGRESS_PHOTOS} 张照片（最多 ${MAX_PROGRESS_PHOTOS} 张）`)).toBeTruthy();
    fireEvent.press(screen.getByText('从相册选'));
    // 选图是异步的（先要权限再开相册）：等它走完再数，不然按钮没禁用也看不出来
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(perm).toHaveBeenCalledTimes(MAX_PROGRESS_PHOTOS);
    expect(lib).toHaveBeenCalledTimes(MAX_PROGRESS_PHOTOS);
    expect(screen.getByText(/已附 9 张照片/)).toBeTruthy();
  });
});
