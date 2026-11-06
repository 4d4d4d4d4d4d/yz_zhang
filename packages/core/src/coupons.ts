// APP-074（418 号 spec）券的写法：网页「领券中心」与 App 钱包共用一份，不各写各的。
import type { CouponTemplate, MyCoupon } from './types';
import { fmtYuan } from './client';

type CouponValue = Pick<CouponTemplate, 'amount_cents' | 'percent_bps' | 'max_discount_cents'>;

/** 「减 ¥20.00」或「8.5% 折，最高减 ¥30.00」；畸形时空串 */
export function couponValueText(c: Partial<CouponValue> | null | undefined): string {
  if (!c) return '';
  if (typeof c.amount_cents === 'number' && c.amount_cents > 0) return `减 ${fmtYuan(c.amount_cents)}`;
  if (typeof c.percent_bps === 'number' && c.percent_bps > 0) {
    const cap = typeof c.max_discount_cents === 'number' && c.max_discount_cents > 0 ? `，最高减 ${fmtYuan(c.max_discount_cents)}` : '';
    return `${(c.percent_bps / 100).toFixed(1)}% 折${cap}`;
  }
  return '';
}

/** 可领的券那一行的附加条件：满多少可用、限哪个类目、仅新用户 */
export function couponTermsText(c: Partial<Pick<CouponTemplate, 'min_order_cents' | 'category' | 'newcomer_only'>> | null | undefined): string {
  if (!c) return '';
  const out: string[] = [];
  if (typeof c.min_order_cents === 'number' && c.min_order_cents > 0) out.push(`满 ${fmtYuan(c.min_order_cents)} 可用`);
  if (c.category) out.push(`限「${c.category}」`);
  if (c.newcomer_only) out.push('仅新用户');
  return out.join(' · ');
}

export const COUPON_STATUS_LABEL: Record<MyCoupon['status'], string> = { unused: '可用', used: '已使用', expired: '已过期' };

/** 未读数在入口上的写法：0 不显示，超过 99 写 99+ */
export function unreadBadge(n: unknown): string {
  const v = typeof n === 'number' && Number.isFinite(n) ? Math.floor(n) : 0;
  if (v <= 0) return '';
  return v > 99 ? '99+' : String(v);
}
