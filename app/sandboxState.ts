// SBX-101/104 App 上的隐私沙箱状态、本机笔记与端侧模型注入点（128 号 spec）。
// 本机笔记只存在这台手机上（AsyncStorage），不发到服务端；同步要人确认、先脱敏。
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { LocalModel } from '@platform/core';

export interface LocalNote { id: string; text: string; updated_at: number }
const FLAG = 'sandbox';
const NOTES = 'sandbox.notes';

let enabled = false;
let model: LocalModel | null = null;

/** SDK 客户端用它判断要不要拦下云端 AI 请求（同步读，所以放在内存里，启动时从存储恢复）。 */
export function isSandbox(): boolean { return enabled; }

export async function loadSandbox(): Promise<boolean> {
  try { enabled = (await AsyncStorage.getItem(FLAG)) === '1'; } catch { /* 读不到按关着处理，服务端还有一道 */ }
  return enabled;
}
export async function setSandboxLocal(on: boolean): Promise<void> {
  enabled = on;
  try { if (on) await AsyncStorage.setItem(FLAG, '1'); else await AsyncStorage.removeItem(FLAG); } catch { /* 只在这次运行里有效 */ }
}

export async function loadLocalNotes(): Promise<LocalNote[]> {
  try {
    const raw = JSON.parse((await AsyncStorage.getItem(NOTES)) || '[]');
    return Array.isArray(raw) ? raw.filter((n) => n && typeof n.text === 'string') : [];
  } catch { return []; }
}
export async function saveLocalNotes(notes: LocalNote[]): Promise<void> {
  try { await AsyncStorage.setItem(NOTES, JSON.stringify(notes)); } catch { /* 存不下就只留在内存里 */ }
}

/** 端侧推理运行时（llama.cpp / ExecuTorch 一类的原生模块）在原生构建里注入；没有注入就用本机规则。 */
export function setLocalModel(m: LocalModel | null): void { model = m; }
export function getLocalModel(): LocalModel | null { return model; }
