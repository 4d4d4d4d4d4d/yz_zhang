// SCN-166（297 号 spec）App 上的交付文件：先看预览，原图锁着时说几张、放款后提示去网页版下载。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';
import { PlatformClient } from '@platform/core';
import { DeliverablesList } from './deliverables';

function client(list: unknown[]) {
  const fetchImpl = (async () => ({ ok: true, status: 200, text: async () => JSON.stringify(list) })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}
const P = { id: 8, kind: 'preview', created_at: '2026-10-24T00:00:00Z', locked: false, url: '/api/v1/files/abc' };
const O = { id: 9, kind: 'original', created_at: '2026-10-24T00:00:00Z', locked: true, url: null };

describe('SCN-166 App 交付文件', () => {
  it('放款前：预览可看，原图说锁着', async () => {
    render(<DeliverablesList client={client([P, O])} contractId={3} baseUrl="https://x" />);
    expect((await screen.findByLabelText('预览')).props.source).toEqual({ uri: 'https://x/api/v1/files/abc' });
    expect(screen.getByText('原图 1 张：验收放款后可以下载')).toBeTruthy();
    expect(screen.queryByText(/已可下载/)).toBeNull();
  });

  it('放款后：提示原图已可下载', async () => {
    render(<DeliverablesList client={client([P, { ...O, locked: false, url: '/api/v1/contracts/3/deliverables/9/file' }])} contractId={3} />);
    expect(await screen.findByText('原图 1 张已可下载：请在网页版下载')).toBeTruthy();
    expect(screen.queryByText(/验收放款后可以下载/)).toBeNull();
  });

  it('没有交付文件时不出这一块', async () => {
    const c = client([]);
    const spy = jest.spyOn(c, 'contractDeliverables');
    render(<DeliverablesList client={c} contractId={4} />);
    await waitFor(() => expect(spy).toHaveBeenCalledWith(4));
    expect(screen.queryByLabelText('交付文件')).toBeNull();
  });

  it('SCN-168 执行方在托管期间：原图按原质量上传后挂到合约上；超 2MB 本地先拦', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      const body = path === '/files' ? { url: '/api/v1/files/n', ref: 'newref123' }
        : method === 'POST' ? { ...O, id: 10 } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    const c = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
    const perm = jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    const pick = jest.spyOn(ImagePicker, 'launchImageLibraryAsync')
      .mockResolvedValueOnce({ canceled: false, assets: [{ base64: 'A'.repeat(4 * 1024 * 1024), mimeType: 'image/jpeg' }] } as never)
      .mockResolvedValueOnce({ canceled: false, assets: [{ base64: 'iVBORw0KGgo=', mimeType: 'image/png' }] } as never);
    try {
      render(<DeliverablesList client={c} contractId={3} isExecutor live />);
      fireEvent.press(await screen.findByText('上传原图'));
      expect(await screen.findByText('单个文件最大 2MB：请压缩后再传')).toBeTruthy();
      expect(calls.some((x) => x.path === '/files')).toBe(false);
      fireEvent.press(screen.getByText('上传原图'));
      await waitFor(() => expect(calls.find((x) => x.method === 'POST' && x.path === '/contracts/3/deliverables')?.body)
        .toEqual({ ref: 'newref123', kind: 'original' }));
      expect(pick.mock.calls[1][0]).toMatchObject({ quality: 1, base64: true });
    } finally {
      perm.mockRestore(); pick.mockRestore();
    }
  });

  it('不是执行方或合约不在托管中时没有上传按钮', async () => {
    render(<DeliverablesList client={client([P])} contractId={3} isExecutor={false} live />);
    await screen.findByLabelText('预览');
    expect(screen.queryByText('上传原图')).toBeNull();
  });
});

describe('SC-017 App 上挂到某一期', () => {
  const STAGES = [{ idx: 1, title: '设计', status: 'released' as const }, { idx: 2, title: '施工', status: 'pending' as const }];

  it('执行方选了第 2 期：上传后挂到第 2 期；已放款的期不在可选里', async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
      const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
      const method = init?.method ?? 'GET';
      calls.push({ method, path, body: init?.body ? JSON.parse(init.body) : null });
      const body = path === '/files' ? { url: '/api/v1/files/n', ref: 'newref123' } : method === 'POST' ? { ...O, id: 10 } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    const c = new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
    const perm = jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync').mockResolvedValue({ status: 'granted' } as never);
    const pick = jest.spyOn(ImagePicker, 'launchImageLibraryAsync')
      .mockResolvedValue({ canceled: false, assets: [{ base64: 'iVBORw0KGgo=', mimeType: 'image/png' }] } as never);
    try {
      render(<DeliverablesList client={c} contractId={3} isExecutor live stages={STAGES} />);
      expect(await screen.findByText('整份合约')).toBeTruthy();
      expect(screen.queryByText('第 1 期 设计')).toBeNull();
      fireEvent.press(screen.getByText('第 2 期 施工'));
      fireEvent.press(screen.getByText('上传原图'));
      await waitFor(() => expect(calls.find((x) => x.method === 'POST' && x.path === '/contracts/3/deliverables')?.body)
        .toEqual({ ref: 'newref123', kind: 'original', milestone_idx: 2 }));
    } finally {
      perm.mockRestore(); pick.mockRestore();
    }
  });

  it('锁着的原图说清各等哪一期；只有一期时不出选择', async () => {
    render(<DeliverablesList client={client([{ ...P, milestone_idx: 2 }, { ...O, milestone_idx: 2 }, { ...O, id: 11 }])} contractId={3}
                             isExecutor live stages={[{ idx: 1, title: '全款', status: 'pending' }]} />);
    expect(await screen.findByLabelText('预览（第 2 期）')).toBeTruthy();
    expect(screen.getByText('原图 2 张：第 2 期 1 张在这一期放款后可以下载；其余 1 张全部放款后可以下载')).toBeTruthy();
    expect(screen.queryByText('整份合约')).toBeNull();
  });
});
