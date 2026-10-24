// SBX-101/104 浏览器里的隐私沙箱状态与本机笔记（128 号 spec）。
// 本机笔记只存在这台设备的浏览器里（localStorage），不发到服务端；同步要人确认、先脱敏。
export interface LocalNote { id: string; text: string; updated_at: number }

const FLAG = 'sandbox';
const NOTES = 'sandbox.notes';

export function readSandbox(): boolean {
  try { return localStorage.getItem(FLAG) === '1'; } catch { return false; }
}
export function writeSandbox(on: boolean): void {
  try { if (on) localStorage.setItem(FLAG, '1'); else localStorage.removeItem(FLAG); } catch { /* 无痕模式：开关只在这次会话里有效 */ }
}
export function loadLocalNotes(): LocalNote[] {
  try {
    const raw = JSON.parse(localStorage.getItem(NOTES) || '[]');
    return Array.isArray(raw) ? raw.filter((n) => n && typeof n.text === 'string') : [];
  } catch { return []; }
}
export function saveLocalNotes(notes: LocalNote[]): void {
  try { localStorage.setItem(NOTES, JSON.stringify(notes)); } catch { /* 存不下就只留在内存里 */ }
}

/** SBX-112 这个浏览器有没有 WebGPU（只用来如实告诉人「浏览器里为什么只用本机规则」）。 */
export function hasWebGpu(): boolean {
  try { return typeof navigator !== 'undefined' && 'gpu' in navigator && !!(navigator as unknown as { gpu?: unknown }).gpu; } catch { return false; }
}
