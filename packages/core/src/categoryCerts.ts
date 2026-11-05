// SCN-181（307 号 spec）一个类目要的全部资质：required_cert 在前，再加 extra_certs（去空、去重）——与服务端 category_certs 一致。
import type { Category } from './types';

export function categoryCerts(c: Pick<Category, 'required_cert' | 'extra_certs'> | null | undefined): string[] {
  const out: string[] = [];
  for (const raw of [c?.required_cert ?? '', ...(c?.extra_certs ?? [])]) {
    const v = (raw ?? '').trim();
    if (v && !out.includes(v)) out.push(v);
  }
  return out;
}

/** 「健康证明」「无犯罪记录证明」这样的写法；不限时为空字符串 */
export const categoryCertsText = (c: Pick<Category, 'required_cert' | 'extra_certs'> | null | undefined) =>
  categoryCerts(c).map((x) => `「${x}」`).join('');

/** SCN-294b（407 号 spec）这个类目发单人可以加选的资质（去空、去重，类目本来就要的不再列） */
export function optionalCerts(c: Pick<Category, 'required_cert' | 'extra_certs' | 'optional_certs'> | null | undefined): string[] {
  const base = categoryCerts(c);
  const out: string[] = [];
  for (const raw of c?.optional_certs ?? []) {
    const v = (raw ?? '').trim();
    if (v && !base.includes(v) && !out.includes(v)) out.push(v);
  }
  return out;
}

/** 换了类目以后，已经勾的只留下新类目也能加的（别把上一个类目的资质带过去，服务端会拒） */
export function keepOfferedCerts(picked: string[], c: Parameters<typeof optionalCerts>[0]): string[] {
  const offered = optionalCerts(c);
  return picked.filter((x) => offered.includes(x));
}

/** 任务上的一句：「这一单另外要「高处作业操作证」」；没加就是空串 */
export function taskCertsLine(t: { task_certs?: unknown } | null | undefined): string {
  const list = Array.isArray(t?.task_certs) ? (t!.task_certs as unknown[]).filter((x): x is string => typeof x === 'string' && !!x) : [];
  return list.length ? `这一单另外要${list.map((x) => `「${x}」`).join('')}，报名的人要有审核通过的证件` : '';
}
