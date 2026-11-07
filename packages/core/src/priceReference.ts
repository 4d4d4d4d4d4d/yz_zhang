// KB-021 / KB-064（266、267 号 spec）发单页「查参考价」那一句：两端同一句话。
import type { PriceReference, TaskProfilePrice } from './types';

const yuan = (c: number) => `¥${(c / 100).toFixed(2)}`;

/** 有样本：「同类闭环任务 N 单：中位价 ¥X（¥min ~ ¥max）」；一位发布方占了大半样本时接上去重后的说明。
 *  没有样本：服务端的 message。形状不对（老服务端、畸形响应）给空串，不显示。 */
export function priceReferenceLine(ref: PriceReference | null | undefined): string {
  if (!ref || typeof ref.sample_size !== 'number') return '';
  if (ref.sample_size <= 0 || typeof ref.p50_cents !== 'number') return ref.message ?? '';
  const range = typeof ref.min_cents === 'number' && typeof ref.max_cents === 'number'
    ? `（${yuan(ref.min_cents)} ~ ${yuan(ref.max_cents)}）` : '';
  const base = `同类闭环任务 ${ref.sample_size} 单：中位价 ${yuan(ref.p50_cents)}${range}`;
  return ref.concentrated && ref.note ? `${base}。${ref.note}` : base;
}

/** KB-094（271 号 spec）任务画像里「预算比中位高 / 低」后面括号里的那个中位：样本集中时是按发布方去重后的。 */
export function profileMedianText(price: Pick<TaskProfilePrice, 'p50_cents' | 'concentrated' | 'reference_cents'>): string {
  if (price.concentrated && typeof price.reference_cents === 'number') return `按发布方去重后的中位 ${yuan(price.reference_cents)}`;
  return `中位 ${yuan(price.p50_cents ?? 0)}`;
}
