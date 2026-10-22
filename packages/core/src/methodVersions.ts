// AGT-097（239 号 spec）方法按版本分开的效果：两端知识库「我的方法」同几句话。
import type { NbMethod, NbMethodVersionStats } from './types';

const yuan = (c: number) => `¥${(c / 100).toFixed(2)}`;
const pct = (r: number) => `${Math.round(r * 100)}%`;

type Versioned = Pick<NbMethod, 'version' | 'versions'>;

function label(v: NbMethodVersionStats['version']): string {
  return v === null ? '记版本之前' : `第 ${v} 版`;
}

/** 每一版一行；只用过当前这一版时不分（与总数那句一样，不重复） */
export function methodVersionLines(m: Versioned): string[] {
  const vs = Array.isArray(m.versions) ? m.versions : [];
  if (!vs.length || (vs.length === 1 && vs[0].version === m.version)) return [];
  return vs.map((v) => `${label(v.version)}：用过 ${v.missions_total} 次，做成 ${v.missions_succeeded}、没成 ${v.missions_failed}，花了 ${yuan(v.missions_spent_cents)}；`
    + (v.success_rate === null ? '做完的还少' : `成功率 ${pct(v.success_rate)}`));
}

/** 当前这版和上一版比：改了之后是变好还是变坏。做完的少于 3 个不比（小样本不下结论） */
export function methodVersionCompare(m: Versioned): string {
  const vs = Array.isArray(m.versions) ? m.versions : [];
  if (!vs.length) return '';
  const cur = vs.find((v) => v.version === m.version);
  const prev = vs.find((v) => v.version !== null && v.version < m.version) ?? vs.find((v) => v.version === null);
  if (!cur) return `第 ${m.version} 版还没用过：用过几次后才看得出改了有没有变好`;
  if (!prev) return '';
  if (cur.success_rate === null || prev.success_rate === null) return `做完的还少，先不比较${label(prev.version)}和第 ${m.version} 版`;
  const head = `${label(prev.version)}成功率 ${pct(prev.success_rate)} → 第 ${m.version} 版 ${pct(cur.success_rate)}`;
  if (cur.success_rate > prev.success_rate) return `${head}：改了之后变好了`;
  if (cur.success_rate < prev.success_rate) return `${head}：改了之后变差了，看看改了哪一步`;
  return `${head}：没有变化`;
}
