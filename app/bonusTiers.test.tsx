// OUT-050（443 号 spec）App 任务详情以前一个字都不显示浮动对价：执行方看不到「做到几条拿多少」。
import { readFileSync } from 'fs';
import { bonusLine } from '@platform/core';

describe('OUT-050 App 任务详情的浮动对价', () => {
  it('outcome 计价的单显示 SDK 的同一句话（与网页、合同条款一致）', () => {
    const src = readFileSync(`${__dirname}/App.tsx`, 'utf8');
    expect(src).toMatch(/task\.pricing === 'outcome' && \(\s*<Text style=\{styles\.mutedLeft\} accessibilityLabel="浮动对价">\{bonusLine\(task\.bonus_cents, task\.bonus_tiers\)\}<\/Text>/);
    expect(bonusLine(9000, [{ min_passed: 2, bonus_cents: 9000 }])).toContain('过 2 条加付 ¥90.00');
  });
});
