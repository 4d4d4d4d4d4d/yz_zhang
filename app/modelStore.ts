// SBX-111 端侧模型的下载、断点续传、分块校验、删除与启用（129 号 spec）。
//
// 模型文件从目录登记的地址**直接**下载到这台手机，不经平台服务器；下载完按登记的 sha256 分块校验，
// 对不上就删掉。真正跑模型要原生推理运行时（llama.cpp / ExecuTorch 一类），由原生构建通过 `registerRuntime` 注入；
// 没有注入时如实说「已下载并校验，但这个安装包里没有推理运行时」，继续用本机规则——不悄悄换成云端。
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Sha256, base64ToBytes, type LocalModel, type SandboxModelRow } from '@platform/core';
import { setLocalModel } from './sandboxState';

export interface InstalledModel {
  key: string;
  name: string;
  sha256: string;
  size_mb: number;
  path: string;
  verified_at: number;
}
export type ModelPhase = 'download' | 'verify';

/** 用到的那几个文件系统能力（默认是 expo-file-system；测试注入假的）。 */
export interface ModelFs {
  documentDirectory: string | null;
  getFreeDiskStorageAsync(): Promise<number>;
  makeDirectoryAsync(uri: string, opts?: { intermediates?: boolean }): Promise<void>;
  getInfoAsync(uri: string): Promise<{ exists: boolean; size?: number }>;
  readAsStringAsync(uri: string, opts: { encoding: 'base64'; position: number; length: number }): Promise<string>;
  deleteAsync(uri: string, opts?: { idempotent?: boolean }): Promise<void>;
  createDownloadResumable(url: string, fileUri: string, opts: object,
    cb: (p: { totalBytesWritten: number; totalBytesExpectedToWrite: number }) => void, resumeData?: string): {
    downloadAsync(): Promise<{ status: number } | undefined>;
    resumeAsync(): Promise<{ status: number } | undefined>;
    pauseAsync(): Promise<{ resumeData?: string }>;
  };
}

const INSTALLED = 'sandbox.models';
const RESUME = 'sandbox.dl.';
const CHUNK = 4 * 1024 * 1024;
const active = new Map<string, ReturnType<ModelFs['createDownloadResumable']>>();
let runtime: ((path: string, m: InstalledModel) => Promise<LocalModel>) | null = null;

async function expoFs(): Promise<ModelFs> {
  const fs = await import('expo-file-system');
  return fs as unknown as ModelFs;
}

export function registerRuntime(factory: ((path: string, m: InstalledModel) => Promise<LocalModel>) | null): void { runtime = factory; }
export function hasRuntime(): boolean { return runtime !== null; }

export async function installedModels(): Promise<InstalledModel[]> {
  try {
    const raw = JSON.parse((await AsyncStorage.getItem(INSTALLED)) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch { return []; }
}
async function saveInstalled(list: InstalledModel[]): Promise<void> {
  await AsyncStorage.setItem(INSTALLED, JSON.stringify(list));
}

/** 装在手机上、但平台已经下架（或改了 sha256）的：提示删除。 */
export function staleModels(installed: InstalledModel[], catalog: SandboxModelRow[]): InstalledModel[] {
  return installed.filter((i) => !catalog.some((c) => c.key === i.key && c.sha256.toLowerCase() === i.sha256.toLowerCase()));
}

/** 按块读出来算 sha256：几百 MB 的文件也不用整个读进内存。 */
export async function verifyFile(fs: ModelFs, path: string, expected: string, onRatio?: (r: number) => void): Promise<boolean> {
  const info = await fs.getInfoAsync(path);
  if (!info.exists) return false;
  const total = info.size ?? 0;
  const h = new Sha256();
  for (let pos = 0; pos < total; pos += CHUNK) {
    const b64 = await fs.readAsStringAsync(path, { encoding: 'base64', position: pos, length: Math.min(CHUNK, total - pos) });
    h.update(base64ToBytes(b64));
    onRatio?.(Math.min(1, (pos + CHUNK) / total));
  }
  return h.hex() === expected.toLowerCase();
}

export class ModelError extends Error {}

/** 下载（有暂停留下的进度就续上）→ 校验 → 登记为已安装。校验不过就删文件并报错。 */
export async function downloadModel(m: SandboxModelRow, onProgress: (phase: ModelPhase, ratio: number) => void,
  fs?: ModelFs): Promise<InstalledModel> {
  const f = fs ?? await expoFs();
  if (!f.documentDirectory) throw new ModelError('这台设备拿不到存储目录');
  const free = await f.getFreeDiskStorageAsync();
  const need = m.size_mb * 1.1 * 1024 * 1024;
  if (free < need) throw new ModelError(`存储空间不够：要 ${Math.ceil(m.size_mb * 1.1)} MB，还剩 ${Math.floor(free / 1024 / 1024)} MB`);
  const dir = `${f.documentDirectory}models/`;
  await f.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
  const path = `${dir}${m.key}.${m.file_format || 'gguf'}`;
  const resume = (await AsyncStorage.getItem(RESUME + m.key)) || undefined;
  const dl = f.createDownloadResumable(m.url, path, {}, (p) => {
    if (p.totalBytesExpectedToWrite > 0) onProgress('download', p.totalBytesWritten / p.totalBytesExpectedToWrite);
  }, resume);
  active.set(m.key, dl);
  let res: { status: number } | undefined;
  try {
    res = resume ? await dl.resumeAsync() : await dl.downloadAsync();
  } finally {
    active.delete(m.key);
  }
  if (!res) throw new ModelError('已暂停：再点一次「继续下载」会从断开的地方接着下');
  if (res.status < 200 || res.status >= 300) throw new ModelError(`下载失败（HTTP ${res.status}）：稍后再试，或者换个网络`);
  await AsyncStorage.removeItem(RESUME + m.key);
  onProgress('verify', 0);
  const ok = await verifyFile(f, path, m.sha256, (r) => onProgress('verify', r));
  if (!ok) {
    await f.deleteAsync(path, { idempotent: true });
    throw new ModelError('校验没通过：文件和平台登记的 sha256 对不上，已经删掉了，不会使用');
  }
  const inst: InstalledModel = { key: m.key, name: m.name, sha256: m.sha256.toLowerCase(), size_mb: m.size_mb, path, verified_at: Date.now() };
  await saveInstalled([inst, ...(await installedModels()).filter((x) => x.key !== m.key)]);
  return inst;
}

/** 暂停：把续传需要的信息存下来，下次接着下。 */
export async function pauseDownload(key: string): Promise<boolean> {
  const dl = active.get(key);
  if (!dl) return false;
  const saved = await dl.pauseAsync();
  if (saved.resumeData) await AsyncStorage.setItem(RESUME + key, saved.resumeData);
  return true;
}

export async function removeModel(inst: InstalledModel, fs?: ModelFs): Promise<void> {
  const f = fs ?? await expoFs();
  await f.deleteAsync(inst.path, { idempotent: true });
  await AsyncStorage.removeItem(RESUME + inst.key);
  await saveInstalled((await installedModels()).filter((x) => x.key !== inst.key));
  setLocalModel(null);
}

/** 启用：有推理运行时就加载并设为本机助手的模型；没有就如实返回原因。 */
export async function activateModel(inst: InstalledModel): Promise<{ model: LocalModel | null; reason: string }> {
  if (!runtime) {
    return { model: null, reason: '模型已下载并校验，但这个安装包里没有端侧推理运行时（要原生构建），暂时用本机规则' };
  }
  try {
    const model = await runtime(inst.path, inst);
    setLocalModel(model);
    return { model, reason: '' };
  } catch {
    return { model: null, reason: '这台设备没能加载这个模型（多半是内存不够）：换更小的模型，或者用本机规则' };
  }
}
