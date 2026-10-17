// SBX-111 端侧模型下载、断点续传、分块 sha256 校验、删除与启用（129 号 spec）。
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient, sha256Hex, type SandboxModelRow } from '@platform/core';
import {
  activateModel, downloadModel, installedModels, pauseDownload, registerRuntime, staleModels, type ModelFs,
} from './modelStore';
import { SandboxScreen } from './sandbox';
import { getLocalModel, setLocalModel, setSandboxLocal } from './sandboxState';

const CONTENT = 'GGUF'.repeat(3_000_000);   // 12 MB：跨过 4 MB 的分块边界
const GOOD = sha256Hex(CONTENT);
const MODEL: SandboxModelRow = {
  id: 1, key: 'tiny-q4', name: 'Tiny Q4', family: 't', params_b: 0.1, quant: 'Q4_K_M', file_format: 'gguf', size_mb: 12,
  sha256: GOOD.toUpperCase(), url: 'https://example.org/tiny.gguf', license: 'MIT', min_ram_gb: 1, languages: [], skills: [], note: '',
  published_at: '2026-10-14T00:00:00Z',
};

function fakeFs(opts: { free?: number; body?: string; pauseFirst?: boolean } = {}) {
  const files = new Map<string, Buffer>();
  const log: string[] = [];
  let paused = !!opts.pauseFirst;
  let release: () => void = () => undefined;
  const gate = new Promise<void>((r) => { release = r; });
  const fs: ModelFs = {
    documentDirectory: 'file:///docs/',
    getFreeDiskStorageAsync: async () => opts.free ?? 10_000 * 1024 * 1024,
    makeDirectoryAsync: async () => undefined,
    getInfoAsync: async (u) => ({ exists: files.has(u), size: files.get(u)?.length }),
    readAsStringAsync: async (u, o) => files.get(u)!.subarray(o.position, o.position + o.length).toString('base64'),
    deleteAsync: async (u) => { files.delete(u); log.push(`delete ${u}`); },
    createDownloadResumable: (url, fileUri, _o, cb, resumeData) => ({
      downloadAsync: async () => {
        log.push(`download ${url}`);
        if (paused) { await gate; return undefined; }     // 像 expo 一样：暂停后 downloadAsync 才返回 undefined
        files.set(fileUri, Buffer.from(opts.body ?? CONTENT)); cb({ totalBytesWritten: 1, totalBytesExpectedToWrite: 1 });
        return { status: 200 };
      },
      resumeAsync: async () => {
        log.push(`resume ${resumeData}`);
        files.set(fileUri, Buffer.from(opts.body ?? CONTENT)); return { status: 200 };
      },
      pauseAsync: async () => { paused = false; release(); return { resumeData: 'resume-token' }; },
    }),
  };
  return { fs, files, log };
}
afterEach(async () => { await AsyncStorage.clear(); registerRuntime(null); setLocalModel(null); await setSandboxLocal(false); });

describe('SBX-111 端侧模型', () => {
  it('下载 → 分块校验 → 登记；没有推理运行时就如实说；注入运行时后启用', async () => {
    const { fs } = fakeFs();
    const phases: string[] = [];
    const inst = await downloadModel(MODEL, (p) => phases.push(p), fs);
    expect(inst.sha256).toBe(GOOD);
    expect(phases).toContain('download');
    expect(phases.filter((p) => p === 'verify').length).toBeGreaterThanOrEqual(3);   // 12 MB 分了 3 块
    expect((await installedModels()).map((i) => i.key)).toEqual(['tiny-q4']);
    expect((await activateModel(inst)).reason).toContain('没有端侧推理运行时');
    registerRuntime(async (path) => ({ id: `tiny@${path}`, generate: async () => '- 一' }));
    const r = await activateModel(inst);
    expect(r.model?.id).toBe('tiny@file:///docs/models/tiny-q4.gguf');
    expect(getLocalModel()).toBe(r.model);
  });

  it('sha256 对不上：删掉文件、不登记、说清楚', async () => {
    const { fs, files } = fakeFs({ body: 'tampered' });
    await expect(downloadModel(MODEL, () => undefined, fs)).rejects.toThrow('校验没通过');
    expect(files.size).toBe(0);
    expect(await installedModels()).toEqual([]);
  });

  it('存储空间不够：下载之前就说', async () => {
    const { fs, log } = fakeFs({ free: 5 * 1024 * 1024 });
    await expect(downloadModel(MODEL, () => undefined, fs)).rejects.toThrow('存储空间不够');
    expect(log).toEqual([]);
  });

  it('暂停后再下：从断开的地方续上', async () => {
    const { fs, log } = fakeFs({ pauseFirst: true });
    const first = downloadModel(MODEL, () => undefined, fs).catch((e: Error) => e);
    await waitFor(async () => expect(await pauseDownload('tiny-q4')).toBe(true));
    expect(((await first) as Error).message).toContain('已暂停');
    await downloadModel(MODEL, () => undefined, fs);
    expect(log).toContain('resume resume-token');
    expect(await AsyncStorage.getItem('sandbox.dl.tiny-q4')).toBeNull();
  });

  it('平台下架或换了版本的：提示删除', () => {
    const inst = { key: 'tiny-q4', name: 'Tiny', sha256: GOOD, size_mb: 12, path: 'p', verified_at: 0 };
    expect(staleModels([inst], [MODEL])).toEqual([]);
    expect(staleModels([inst], [{ ...MODEL, sha256: 'b'.repeat(64) }])).toEqual([inst]);
    expect(staleModels([inst], [])).toEqual([inst]);
  });

  it('沙箱页：下载并校验、启用、删除；下架的提示删掉', async () => {
    const { fs } = fakeFs();
    const fetchImpl = (async (url: string) => {
      const path = String(url).replace(/^.*\/api\/v1/, '');
      const body = path === '/sandbox/models' ? { items: [MODEL], note: '模型文件不经平台' }
        : path === '/users/me/sandbox' ? { enabled: true, since: null, blocked_endpoints: 14, note: '' } : [];
      return { ok: true, status: 200, text: async () => JSON.stringify(body) };
    }) as unknown as typeof fetch;
    await AsyncStorage.setItem('sandbox.models', JSON.stringify([{ key: 'old', name: '旧模型', sha256: 'c'.repeat(64), size_mb: 1, path: 'file:///docs/models/old.gguf', verified_at: 0 }]));
    render(<SandboxScreen client={new PlatformClient({ baseUrl: '', getToken: () => 't', fetchImpl })} fs={fs} />);
    expect(await screen.findByText('「旧模型」平台已下架或换了版本，建议删掉')).toBeTruthy();
    fireEvent.press(screen.getByText('下载并校验'));
    expect(await screen.findByText('「Tiny Q4」已下载并通过 sha256 校验')).toBeTruthy();
    registerRuntime(async () => ({ id: 'tiny', generate: async () => '- 一' }));
    fireEvent.press(screen.getByText('启用'));
    expect(await screen.findByText('已启用「Tiny Q4」：本机助手用它生成')).toBeTruthy();
    expect(screen.getByText('端侧模型：tiny')).toBeTruthy();
    fireEvent.press(screen.getByText('删除'));
    expect(await screen.findByText('已从这台手机上删掉「Tiny Q4」')).toBeTruthy();
    expect(screen.getByText('这台手机还没有装端侧模型，用的是本机规则')).toBeTruthy();
  });
});
