// APP-074（418 号 spec）券的写法与未读角标
import { describe, expect, it } from 'vitest';
import { COUPON_STATUS_LABEL, couponTermsText, couponValueText, unreadBadge } from './coupons';

describe('券的写法', () => {
  it('满减与折扣；畸形不写', () => {
    expect(couponValueText({ amount_cents: 2000, percent_bps: 0, max_discount_cents: 0 })).toBe('减 ¥20.00');
    expect(couponValueText({ amount_cents: 0, percent_bps: 850, max_discount_cents: 3000 })).toBe('8.5% 折，最高减 ¥30.00');
    expect(couponValueText({ amount_cents: 0, percent_bps: 900, max_discount_cents: 0 })).toBe('9.0% 折');
    expect(couponValueText({ amount_cents: 0, percent_bps: 0 })).toBe('');
    expect(couponValueText(null)).toBe('');
  });
  it('附加条件', () => {
    expect(couponTermsText({ min_order_cents: 10000, category: '保洁', newcomer_only: true })).toBe('满 ¥100.00 可用 · 限「保洁」 · 仅新用户');
    expect(couponTermsText({ min_order_cents: 0, category: '', newcomer_only: false })).toBe('');
    expect(COUPON_STATUS_LABEL.expired).toBe('已过期');
  });
});

describe('未读角标', () => {
  it('0 不显示，超过 99 写 99+，畸形当 0', () => {
    expect(unreadBadge(0)).toBe('');
    expect(unreadBadge(3)).toBe('3');
    expect(unreadBadge(120)).toBe('99+');
    expect(unreadBadge('5')).toBe('');
    expect(unreadBadge(undefined)).toBe('');
  });
});
