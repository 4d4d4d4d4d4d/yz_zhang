// AGT-073（224 号 spec）运营看板上的一句话：平台自费核验用了多少、快不快用完、用完后漏了几次。
import type { AutoVerifyUsage } from './types';

export type AutoVerifyLevel = 'ok' | 'near' | 'out';

/** 用到八成算「快用完」；用完了写明之后拿不准的交付不会自动请人看。 */
export function autoVerifyLevel(u: AutoVerifyUsage): AutoVerifyLevel {
  if (u.remaining <= 0) return 'out';   // 上限设成 0 时服务端给的 remaining 也是 0
  return u.used_24h * 10 >= u.daily_max * 8 ? 'near' : 'ok';
}

export function autoVerifyLine(u: AutoVerifyUsage): string {
  const head = `近 24 小时平台自费核验 ${u.used_24h} / ${u.daily_max} 张（¥${(u.fee_cents_24h / 100).toFixed(2)}）`;
  const level = autoVerifyLevel(u);
  if (level === 'out') {
    return `${head}：额度已用完，之后审核拿不准的 AI 交付不再自动请人看，只通知发布方`
      + (u.skipped_24h > 0 ? `（已有 ${u.skipped_24h} 次）` : '') + '；要放宽请调 PLATFORM_AUTO_VERIFY_DAILY_MAX';
  }
  if (level === 'near') return `${head}：快用完了，还剩 ${u.remaining} 张`;
  return head;
}
