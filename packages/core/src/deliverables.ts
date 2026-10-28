// SC-017（304 号 spec）交付文件挂到某一期：两端共用的文案。挂到某一期的原图，那一期放款后就能下载；
// 不挂期数的（V324 的行为）全部放款后才能下载，文案与以前一字不差。
import type { ContractDeliverable, ContractHandoverItem, ContractLicenseItem, HandoverKind, LicenseKind } from './types';

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

/** SCN-202（329 号 spec）授权清单的类别中文名。两端同一份。 */
export const LICENSE_KIND_LABEL: Record<LicenseKind, string> = {
  music: '音乐', footage: '视频素材', font: '字体', template: '模板', image: '图片', other: '其他',
};

/** 授权清单一项的一句话：「音乐：《某某》——某曲库商用授权（仅限抖音）」 */
export function licenseLine(i: Pick<ContractLicenseItem, 'kind' | 'title' | 'source' | 'scope'>): string {
  const scope = i.scope ? `（${i.scope}）` : '';
  return `${LICENSE_KIND_LABEL[i.kind] ?? '其他'}：${i.title}——${i.source}${scope}`;
}

/** SCN-205（330 号 spec）账号交接的类别中文名。两端同一份。 */
export const HANDOVER_KIND_LABEL: Record<HandoverKind, string> = {
  domain: '域名', miniapp: '小程序', server: '服务器', merchant: '支付商户号', other: '其他账号',
};

/** 交接进度一句话：全部确认、还差几项、或者一项都没登记（空串） */
export function handoverSummary(rows: Pick<ContractHandoverItem, 'confirmed_at'>[]): string {
  if (rows.length === 0) return '';
  const done = rows.filter((r) => r.confirmed_at).length;
  return done === rows.length ? `${rows.length} 项账号都已确认在发单人名下`
    : `${rows.length} 项账号里还有 ${rows.length - done} 项没确认在发单人名下`;
}
