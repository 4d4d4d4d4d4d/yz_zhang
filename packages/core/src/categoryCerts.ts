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
