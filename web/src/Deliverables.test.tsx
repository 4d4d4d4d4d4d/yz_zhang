// SCN-166（297 号 spec）交付文件：发布方放款前看预览、原图锁着；放款后带登录态下载；执行方上传原图不压缩、超 2MB 先拦。
import { PlatformClient } from '@platform/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DeliverablesBlock from './Deliverables';
import { AppProvider } from './store';

type Call = { method: string; path: string; body: unknown; auth?: string };
const PREVIEW = { id: 8, kind: 'preview', created_at: '2026-10-24T00:00:00Z', locked: false, url: '/api/v1/files/abc' };
const LOCKED = { id: 9, kind: 'original', created_at: '2026-10-24T00:00:00Z', locked: true, url: null };
const OPEN = { ...LOCKED, locked: false, url: '/api/v1/contracts/3/deliverables/9/file' };

type Stage = { idx: number; title: string; status: 'pending' | 'delivered' | 'released' };
function mount(list: unknown[], calls: Call[], props: { isExecutor: boolean; live: boolean; stages?: Stage[] }) {
  const fetchImpl = vi.fn(async (url: string, init?: { method?: string; body?: string; headers?: Record<string, string> }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null, auth: init?.headers?.Authorization });
    const body = path === '/contracts/3/deliverables' && (init?.method ?? 'GET') === 'GET' ? list
      : path === '/files' ? { url: '/api/v1/files/new', ref: 'newref123' }
      : path === '/contracts/3/deliverables' ? { ...LOCKED, id: 10 } : null;
    return { ok: true, status: 200, text: async () => JSON.stringify(body), blob: async () => new Blob(['png']), headers: { get: () => null } };
  }) as unknown as typeof fetch;
  render(<AppProvider client={new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl })}><DeliverablesBlock contractId={3} {...props} /></AppProvider>);
}

describe('SCN-166 交付文件', () => {
  it('发布方放款前：看得到预览，原图只说几张、没有下载按钮，也不能上传', async () => {
    mount([PREVIEW, LOCKED], [], { isExecutor: false, live: true });
    expect((await screen.findByAltText('预览')).getAttribute('src')).toBe('/api/v1/files/abc');
    expect(screen.getByTestId('originals-locked').textContent).toBe('原图 1 张：验收放款后可以下载');
    expect(screen.queryByText(/下载原图/)).toBeNull();
    expect(screen.queryByLabelText('上传原图')).toBeNull();
  });

  it('放款后：带登录态下载原图', async () => {
    const calls: Call[] = [];
    const create = vi.fn(() => 'blob:x');
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
    mount([PREVIEW, OPEN], calls, { isExecutor: false, live: false });
    fireEvent.click(await screen.findByText('下载原图 #9'));
    await waitFor(() => expect(create).toHaveBeenCalled());
    const dl = calls.find((c) => c.path === '/contracts/3/deliverables/9/file');
    expect(dl?.auth).toBe('Bearer tok');
    expect(screen.queryByTestId('originals-locked')).toBeNull();
  });

  it('执行方：原图原样上传后挂到合约上；超过 2MB 先拦，不发请求', async () => {
    const calls: Call[] = [];
    mount([], calls, { isExecutor: true, live: true });
    const input = await screen.findByLabelText('上传原图');
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'big.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [big] } });
    expect(await screen.findByText('单个文件最大 2MB：请压缩后再传')).toBeTruthy();
    expect(calls.some((c) => c.path === '/files')).toBe(false);
    const ok = new File([new Uint8Array([137, 80, 78, 71])], 'a.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [ok] } });
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/contracts/3/deliverables')?.body)
      .toEqual({ ref: 'newref123', kind: 'original' }));
    expect((calls.find((c) => c.path === '/files')?.body as { content_type: string }).content_type).toBe('image/png');
  });
});

describe('SC-017 每一期挂各自的交付附件', () => {
  const STAGES: Stage[] = [{ idx: 1, title: '设计', status: 'released' }, { idx: 2, title: '施工', status: 'delivered' },
    { idx: 3, title: '收尾', status: 'pending' }];

  it('执行方选了第 2 期：上传后挂到第 2 期；已放款的期不在可选里；默认挂整份合约', async () => {
    const calls: Call[] = [];
    mount([], calls, { isExecutor: true, live: true, stages: STAGES });
    const pick = await screen.findByLabelText('挂到哪一期');
    const opts = [...pick.querySelectorAll('option')].map((o) => o.textContent);
    expect(opts).toEqual(['整份合约（全部放款后才能下载原图）', '第 2 期 施工（这一期放款后就能下载）', '第 3 期 收尾（这一期放款后就能下载）']);
    const ok = new File([new Uint8Array([137, 80, 78, 71])], 'a.png', { type: 'image/png' });
    fireEvent.change(pick, { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('上传原图'), { target: { files: [ok] } });
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.path === '/contracts/3/deliverables')?.body)
      .toEqual({ ref: 'newref123', kind: 'original', milestone_idx: 2 }));
  });

  it('只有一期时不出选择；锁着的原图说清各等哪一期', async () => {
    mount([{ ...LOCKED, milestone_idx: 2 }, { ...LOCKED, id: 11 }, { ...OPEN, id: 12, milestone_idx: 1 }], [],
      { isExecutor: true, live: true, stages: [{ idx: 1, title: '全款', status: 'pending' }] });
    expect(await screen.findByText('下载原图 #12（第 1 期）')).toBeTruthy();
    expect(screen.queryByLabelText('挂到哪一期')).toBeNull();
    expect(screen.getByTestId('originals-locked').textContent).toBe('原图 2 张：第 2 期 1 张在这一期放款后可以下载；其余 1 张全部放款后可以下载');
  });
});
