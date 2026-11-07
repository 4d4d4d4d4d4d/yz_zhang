// OUT-050（443 号 spec）浮动对价的说法两端共用。
import { describe, expect, it } from 'vitest';
import { bonusLine } from './bonusTiers';

describe('bonusLine', () => {
  it('没分档或分档畸形：照旧「达标可加付至多」', () => {
    expect(bonusLine(5000, [])).toBe('达标可加付至多 ¥50.00（按验收指标判定）');
    expect(bonusLine(5000, undefined)).toBe('达标可加付至多 ¥50.00（按验收指标判定）');
    expect(bonusLine(5000, [{ min_passed: NaN, bonus_cents: 100 }, { min_passed: 1, bonus_cents: 0 }])).toContain('达标可加付至多');
  });

  it('分档：逐档写、按服务端给的顺序、说明不累加', () => {
    expect(bonusLine(9000, [{ min_passed: 1, bonus_cents: 2000 }, { min_passed: 2, bonus_cents: 5000 }, { min_passed: 3, bonus_cents: 9000 }]))
      .toBe('按通过的平台判定指标分档加付：过 1 条加付 ¥20.00，过 2 条加付 ¥50.00，过 3 条加付 ¥90.00（取最高一档，不累加）');
  });
});
