// SC-017（304 号 spec）交付文件挂到某一期：两端共用的文案。挂到某一期的原图，那一期放款后就能下载；
// 不挂期数的（V324 的行为）全部放款后才能下载，文案与以前一字不差。
import type { ContractDeliverable } from './types';

/** 原图锁着时说清每一张等哪一期 */
export function deliverableLockedText(locked: Pick<ContractDeliverable, 'milestone_idx'>[]): string {
  const staged = new Map<number, number>();
  for (const d of locked) if (d.milestone_idx) staged.set(d.milestone_idx, (staged.get(d.milestone_idx) ?? 0) + 1);
  if (staged.size === 0) return `原图 ${locked.length} 张：验收放款后可以下载`;
  const parts = [...staged.entries()].sort((a, b) => a[0] - b[0]).map(([i, n]) => `第 ${i} 期 ${n} 张在这一期放款后可以下载`);
  const whole = locked.length - [...staged.values()].reduce((a, b) => a + b, 0);
  if (whole > 0) parts.push(`其余 ${whole} 张全部放款后可以下载`);
  return `原图 ${locked.length} 张：${parts.join('；')}`;
}

/** 挂到某一期的文件在名字后面标「（第 N 期）」；整份合约的不标 */
export const deliverableStageTag = (d: Pick<ContractDeliverable, 'milestone_idx'>) =>
  (d.milestone_idx ? `（第 ${d.milestone_idx} 期）` : '');
