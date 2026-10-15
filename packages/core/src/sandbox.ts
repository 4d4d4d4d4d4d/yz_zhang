// SBX-100 端侧隐私沙箱（128 号 spec）：在手机（或浏览器）本机完成的助手操作。
//
// 这个文件**不联网**：不 import client、不调 fetch——本机助手的输入与输出都只在这台设备上（闸门 sandbox.test.ts 钉住）。
// 推理引擎二选一：
// - `LocalModel`：端侧量化小模型（llama.cpp / ExecuTorch 一类运行时由 App 注入）；
// - 规则引擎：没有模型、或者手机跑不动时用，确定、可解释，结果上写明「本机规则，不是模型」。
// 要动钱、签署、发布、对外发送的一律不做：交给人在联网模式下确认（平台红线）。

// ------------------------------------------------------------------ 云端 AI 端点（SBX-102）
/** 把自由文本交给 AI 处理的接口：沙箱开着时，客户端在发请求之前就拦下。与服务端 `CLOUD_AI_ROUTES` 双向一致。 */
export const CLOUD_AI_ENDPOINTS: ReadonlyArray<readonly ['POST', string]> = [
  ['POST', '/workbench/items/{item_id}/breakdown'],
  ['POST', '/notebook/ask'],
  ['POST', '/notebook/notes/{note_id}/extract-todos'],
  ['POST', '/notebook/methods/distill'],
  ['POST', '/packs/{key}/assistants/{akey}/ask'],
  ['POST', '/opc/contract-review'],
  ['POST', '/tasks/{task_id}/decompositions'],
  ['POST', '/decompositions/{dec_id}/expand'],
  ['POST', '/ai/clarify'],
  ['POST', '/agent/tools/{unit_id}/invoke'],
  ['POST', '/support/ask'],
  ['POST', '/legal/ask'],
  ['POST', '/legal/documents'],
  ['POST', '/missions'],
  // AGT-093（154 号 spec）：蒸馏本身不调模型，但编排在沙箱里本来就建不了，同一类一起拦
  ['POST', '/missions/{mission_id}/summary/distill'],
];
const CLOUD_AI_RE = CLOUD_AI_ENDPOINTS.map(([m, p]) => [m, new RegExp(`^${p.replace(/\{[^}]+\}/g, '[^/]+')}$`)] as const);

export function isCloudAiRequest(method: string, path: string): boolean {
  const bare = path.split('?')[0];
  return CLOUD_AI_RE.some(([m, re]) => m === method.toUpperCase() && re.test(bare));
}

// ------------------------------------------------------------------ sha256（纯 TS，端上校验模型文件与 Merkle 证明）
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

/** 增量 sha256：大文件（几百 MB 的模型）可以分块喂，不用整个读进内存。 */
export class Sha256 {
  private h = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  private buf = new Uint8Array(64);
  private bufLen = 0;
  private total = 0;
  private w = new Uint32Array(64);

  update(data: Uint8Array): this {
    let i = 0;
    this.total += data.length;
    if (this.bufLen) {
      const take = Math.min(64 - this.bufLen, data.length);
      this.buf.set(data.subarray(0, take), this.bufLen);
      this.bufLen += take;
      i = take;
      if (this.bufLen === 64) { this.block(this.buf, 0); this.bufLen = 0; }
    }
    for (; i + 64 <= data.length; i += 64) this.block(data, i);
    if (i < data.length) { this.buf.set(data.subarray(i), 0); this.bufLen = data.length - i; }
    return this;
  }

  hex(): string {
    const bits = this.total * 8;
    const pad = new Uint8Array(((this.bufLen < 56 ? 56 : 120) - this.bufLen) + 8);
    pad[0] = 0x80;
    const hi = Math.floor(bits / 0x100000000);
    const lo = bits >>> 0;
    const n = pad.length;
    pad[n - 8] = hi >>> 24; pad[n - 7] = hi >>> 16; pad[n - 6] = hi >>> 8; pad[n - 5] = hi;
    pad[n - 4] = lo >>> 24; pad[n - 3] = lo >>> 16; pad[n - 2] = lo >>> 8; pad[n - 1] = lo;
    this.total -= pad.length;          // 补位不算进消息长度
    this.update(pad);
    return Array.from(this.h, (x) => x.toString(16).padStart(8, '0')).join('');
  }

  private block(d: Uint8Array, o: number): void {
    const w = this.w;
    for (let t = 0; t < 16; t++) w[t] = (d[o + 4 * t] << 24) | (d[o + 4 * t + 1] << 16) | (d[o + 4 * t + 2] << 8) | d[o + 4 * t + 3];
    for (let t = 16; t < 64; t++) {
      const a = w[t - 15], b = w[t - 2];
      const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
      const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
    }
    let [a, b, c, e, f, g, hh, dd] = [this.h[0], this.h[1], this.h[2], this.h[4], this.h[5], this.h[6], this.h[7], this.h[3]];
    for (let t = 0; t < 64; t++) {
      const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + S1 + ch + K[t] + w[t]) | 0;
      const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) | 0;
      hh = g; g = f; f = e; e = (dd + t1) | 0; dd = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    this.h[0] += a; this.h[1] += b; this.h[2] += c; this.h[3] += dd;
    this.h[4] += e; this.h[5] += f; this.h[6] += g; this.h[7] += hh;
  }
}

export function utf8(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}
export function sha256Hex(data: Uint8Array | string): string {
  return new Sha256().update(typeof data === 'string' ? utf8(data) : data).hex();
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const B64_INDEX = (() => { const t = new Int16Array(128).fill(-1); for (let i = 0; i < 64; i++) t[B64.charCodeAt(i)] = i; return t; })();
/** SBX-111 手机上按块读文件拿到的是 base64：解成字节再喂给 sha256（不依赖 atob / Buffer，Hermes 上也能用）。 */
export function base64ToBytes(b64: string): Uint8Array {
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, '');
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4));
  let o = 0;
  for (let i = 0; i + 1 < clean.length; i += 4) {
    const a = B64_INDEX[clean.charCodeAt(i)], b = B64_INDEX[clean.charCodeAt(i + 1)];
    const c = i + 2 < clean.length ? B64_INDEX[clean.charCodeAt(i + 2)] : -1;
    const d = i + 3 < clean.length ? B64_INDEX[clean.charCodeAt(i + 3)] : -1;
    out[o++] = (a << 2) | (b >> 4);
    if (c >= 0) out[o++] = ((b & 15) << 4) | (c >> 2);
    if (d >= 0) out[o++] = ((c & 3) << 6) | d;
  }
  return out.subarray(0, o);
}

/** SBX-106 下载完的模型文件：按目录登记的 sha256 校验，对不上就不要用（App 会删掉重下）。 */
export function verifyModelChunks(chunks: Iterable<Uint8Array>, expected: string): { ok: boolean; actual: string } {
  const h = new Sha256();
  for (const c of chunks) h.update(c);
  const actual = h.hex();
  return { ok: actual === expected.toLowerCase(), actual };
}

// ------------------------------------------------------------------ INF-110 影响力 Merkle 证明：端上独立验算（127 号 spec）
/** Python `json.dumps(float)` 的写法：整数也带「.0」。 */
function pyFloat(x: number): string {
  return Number.isInteger(x) ? `${x}.0` : String(x);
}
/** 与服务端 `influence.service.leaf` 逐字节一致：sha256(json.dumps([user_id, 类目, 影响力], ensure_ascii=False))。 */
export function influenceLeaf(userId: number, category: string, points: number): string {
  return sha256Hex(`[${userId}, ${JSON.stringify(category)}, ${pyFloat(points)}]`);
}
/** 不信服务端给的 `verified`：自己从叶子沿路径算到根。 */
export function verifyInfluenceProof(leaf: string, path: string[], root: string): boolean {
  let h = leaf;
  for (const sib of path) {
    const [lo, hi] = h < sib ? [h, sib] : [sib, h];
    h = sha256Hex(lo + hi);
  }
  return h === root;
}

// ------------------------------------------------------------------ 脱敏（SBX-105）
export type RedactKind = 'phone' | 'id_card' | 'bank_card' | 'email' | 'plate';
const REDACT_RULES: Array<[RedactKind, RegExp, (m: string) => string]> = [
  ['id_card', /(?<!\d)\d{17}[\dXx](?!\d)/g, (m) => `${m.slice(0, 3)}***********${m.slice(-4)}`],
  ['bank_card', /(?<!\d)\d{16,19}(?!\d)/g, (m) => `****${m.slice(-4)}`],
  ['phone', /(?<!\d)1[3-9]\d{9}(?!\d)/g, (m) => `${m.slice(0, 3)}****${m.slice(-4)}`],
  ['email', /[\w.+-]+@[\w-]+(\.[\w-]+)+/g, (m) => `${m[0]}***@${m.split('@')[1]}`],
  ['plate', /[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,6}/g, (m) => `${m.slice(0, 2)}***${m.slice(-1)}`],
];
export const REDACT_NAMES: Record<RedactKind, string> = {
  phone: '手机号', id_card: '身份证号', bank_card: '银行卡号', email: '邮箱', plate: '车牌',
};

/** 同步到云端之前：把可直接识别个人的号码遮掉。返回遮了什么，界面上逐项给人看、由人确认。 */
export function redact(text: string): { text: string; hits: Array<{ kind: RedactKind; count: number }> } {
  let out = text;
  const hits: Array<{ kind: RedactKind; count: number }> = [];
  for (const [kind, re, mask] of REDACT_RULES) {
    let n = 0;
    out = out.replace(re, (m) => { n += 1; return mask(m); });
    if (n) hits.push({ kind, count: n });
  }
  return { text: out, hits };
}

// ------------------------------------------------------------------ 本机助手（SBX-104）
export type LocalSkill = 'summarize' | 'checklist' | 'todos' | 'rewrite' | 'reply';
export const LOCAL_SKILL_NAMES: Record<LocalSkill, string> = {
  summarize: '摘要', checklist: '拆成清单', todos: '抽出待办', rewrite: '改写得正式一点', reply: '起草回复',
};

/** 端侧模型运行时的最小接口：App 用 llama.cpp / ExecuTorch 一类运行时实现并注入。 */
export interface LocalModel {
  id: string;
  generate(prompt: string, opts?: { maxTokens?: number; stop?: string[] }): Promise<string>;
}

export interface LocalResult {
  skill: LocalSkill;
  /** model：端侧模型；rules：本机规则（没有模型或模型出错时） */
  engine: 'model' | 'rules';
  output: string;
  items: string[];
  notice: string;
}

const RED_LINE = /付款|转账|打款|支付|提现|签署|签合同|签字|盖章|发布|上架|提交申报|报税|申报|发给|发送给|群发|发邮件|下单/;
export const LOCAL_REFUSAL = '要动钱、签署、发布或对外发送的，沙箱里不做：这些要你本人在联网模式下确认';

/** 一句话指令 → 本机技能；碰到红线返回拒绝理由。 */
export function routeInstruction(instruction: string): { skill: LocalSkill } | { refuse: string } {
  const s = instruction.trim();
  if (RED_LINE.test(s)) return { refuse: LOCAL_REFUSAL };
  if (/待办|要做的|todo|任务/i.test(s)) return { skill: 'todos' };
  if (/清单|步骤|拆|计划|怎么做/.test(s)) return { skill: 'checklist' };
  if (/回复|回信|答复|回一下/.test(s)) return { skill: 'reply' };
  if (/改写|润色|正式|书面|改一下/.test(s)) return { skill: 'rewrite' };
  return { skill: 'summarize' };
}

const SENT = /[^。！？!?\n；;]+[。！？!?；;]?/g;
function sentences(text: string): string[] {
  return (text.match(SENT) ?? []).map((x) => x.trim()).filter((x) => x.length > 1);
}
function bigrams(s: string): string[] {
  const t = s.replace(/[\s，,。！？!?；;：:、“”"'（）()]/g, '');
  const out: string[] = [];
  for (let i = 0; i + 1 < t.length; i++) out.push(t.slice(i, i + 2));
  return out;
}

const RULES: Record<LocalSkill, (text: string) => { output: string; items: string[] }> = {
  summarize(text) {
    const ss = sentences(text);
    if (ss.length <= 3) return { output: ss.join(''), items: ss };
    const freq = new Map<string, number>();
    for (const b of bigrams(text)) freq.set(b, (freq.get(b) ?? 0) + 1);
    const scored = ss.map((s, i) => {
      const bs = bigrams(s);
      return { s, i, score: bs.reduce((a, b) => a + (freq.get(b) ?? 0), 0) / Math.max(4, bs.length) + (i === 0 ? 0.5 : 0) };
    });
    const top = scored.sort((a, b) => b.score - a.score).slice(0, 3).sort((a, b) => a.i - b.i).map((x) => x.s);
    return { output: top.join(''), items: top };
  },
  checklist(text) {
    const bullets = text.split('\n').map((l) => l.replace(/^\s*(?:[-*•·]|\d+[.、)）])\s*/, '').trim())
      .filter((l, i, all) => l && all.length > 1 && /^\s*(?:[-*•·]|\d+[.、)）])/.test(text.split('\n')[i] ?? ''));
    const steps = bullets.length >= 2 ? bullets : sentences(text).map((s) => s.replace(/[。！？!?；;]$/, ''));
    const items = (steps.length >= 2 ? steps : ['想清楚要做到什么程度（验收标准）', ...steps, '列出要用的东西和要找的人', '定一个截止时间，留出检查的时间'])
      .slice(0, 12);
    return { output: items.map((x, i) => `${i + 1}. ${x}`).join('\n'), items };
  },
  todos(text) {
    const cue = /需要|(?<![纪摘提概主重])要|请|记得|别忘|截止|之前|前完成|下周|明天|今天|跟进|确认|TODO|待办/i;
    const items = sentences(text).filter((s) => cue.test(s)).map((s) => s.replace(/[。！？!?；;]$/, '')).slice(0, 12);
    return { output: items.length ? items.map((x) => `- ${x}`).join('\n') : '没有找到明确的待办（试试写上「需要…」「…之前」）', items };
  },
  rewrite(text) {
    const pairs: Array<[RegExp, string]> = [
      [/啥/g, '什么'], [/咋/g, '怎么'], [/搞定/g, '完成'], [/弄/g, '处理'], [/挺好的?/g, '较好'], [/没问题/g, '可以'],
      [/麻烦你?/g, '烦请'], [/哈|啦|呀|嘛|呗|哦/g, ''], [/！+/g, '。'], [/～|~/g, ''],
    ];
    let out = text.trim();
    for (const [re, to] of pairs) out = out.replace(re, to);
    out = out.replace(/。{2,}/g, '。');
    return { output: out, items: [] };
  },
  reply(text) {
    const first = sentences(text)[0]?.replace(/[。！？!?；;]$/, '') ?? '';
    const asks = sentences(text).filter((s) => /[?？吗呢]$|[?？]/.test(s)).map((s) => s.replace(/[?？]$/, ''));
    const body = asks.length
      ? asks.map((q, i) => `${i + 1}. 关于「${q.slice(0, 30)}」：（在这里写你的答复）`).join('\n')
      : `关于「${first.slice(0, 30)}」：（在这里写你的答复）`;
    const output = `您好，收到您的消息。\n${body}\n如有其他需要，随时告诉我。`;
    return { output, items: asks };
  },
};

const PROMPTS: Record<LocalSkill, string> = {
  summarize: '用三句话以内概括下面的内容，只保留关键事实，不要编造：',
  checklist: '把下面的事情拆成可以逐项完成的清单，每行一项，以「- 」开头，不超过 12 项：',
  todos: '从下面的内容里找出需要去做的事，每行一项，以「- 」开头；没有就回答「无」：',
  rewrite: '把下面的文字改写得正式、简洁，意思不变，不要添加新信息：',
  reply: '为下面的消息起草一封礼貌的回复草稿，需要本人补充的地方用（）标出：',
};

function listItems(out: string): string[] {
  return out.split('\n').map((l) => l.replace(/^\s*(?:[-*•·]|\d+[.、)）])\s*/, '').trim()).filter((l) => l && l !== '无');
}

/** 在本机跑一个技能。模型出错（或没有模型）时退回规则引擎，结果里写清楚用的是哪个。 */
export async function runLocal(skill: LocalSkill, text: string, model?: LocalModel | null): Promise<LocalResult> {
  const input = text.trim().slice(0, 8000);
  if (!input) {
    return { skill, engine: 'rules', output: '', items: [], notice: '先写点内容再让助手处理' };
  }
  if (model) {
    try {
      const raw = (await model.generate(`${PROMPTS[skill]}\n\n${input}\n`, { maxTokens: 512 })).trim();
      if (raw) {
        const listy = skill === 'checklist' || skill === 'todos';
        return { skill, engine: 'model', output: raw, items: listy ? listItems(raw) : [],
          notice: `本机模型「${model.id}」生成，内容没有离开这台设备` };
      }
    } catch {
      // 模型跑不动（内存不够、被系统杀掉）：如实退回规则，不悄悄换成云端
    }
  }
  const r = RULES[skill](input);
  return { skill, engine: 'rules', ...r,
    notice: model ? '本机模型这次没跑成，用的是本机规则（不是模型），内容没有离开这台设备' : '用的是本机规则（不是模型），内容没有离开这台设备' };
}

/** 一句话指令直接跑：先过红线，再路由到技能。 */
export async function askLocal(instruction: string, text: string, model?: LocalModel | null): Promise<LocalResult | { refused: string }> {
  const r = routeInstruction(instruction);
  if ('refuse' in r) return { refused: r.refuse };
  return runLocal(r.skill, text, model);
}

/** 设备能不能跑这个模型：内存不够就如实说，不悄悄退回云端。 */
export function canRunModel(model: { min_ram_gb: number; size_mb: number }, device: { ram_gb: number; free_disk_mb: number }):
  { ok: boolean; reason: string } {
  if (device.ram_gb < model.min_ram_gb) return { ok: false, reason: `这台设备内存 ${device.ram_gb} GB，这个模型至少要 ${model.min_ram_gb} GB：换更小的模型，或者用本机规则` };
  if (device.free_disk_mb < model.size_mb * 1.1) return { ok: false, reason: `存储空间不够：要 ${Math.ceil(model.size_mb * 1.1)} MB，还剩 ${device.free_disk_mb} MB` };
  return { ok: true, reason: '' };
}
