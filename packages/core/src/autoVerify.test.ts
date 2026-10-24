// AGT-073（224 号 spec）自费核验用量的一句话。
import { describe, expect, it } from 'vitest';
import { autoVerifyLevel, autoVerifyLine } from './autoVerify';

const U = (used: number, max = 50, skipped = 0) => ({ used_24h: used, daily_max: max, remaining: Math.max(0, max - used),
  fee_cents_24h: used * 500, skipped_24h: skipped });

describe('AGT-073 autoVerifyLine', () => {
  it('没到八成只报数；到八成说快用完、还剩几张', () => {
    expect(autoVerifyLevel(U(39))).toBe('ok');
    expect(autoVerifyLine(U(39))).toBe('近 24 小时平台自费核验 39 / 50 张（¥195.00）');
    expect(autoVerifyLevel(U(40))).toBe('near');
    expect(autoVerifyLine(U(40))).toBe('近 24 小时平台自费核验 40 / 50 张（¥200.00）：快用完了，还剩 10 张');
  });
  it('用完了说清后果、漏了几次、怎么放宽；上限设成 0 也算用完', () => {
    const line = autoVerifyLine(U(50, 50, 3));
    expect(autoVerifyLevel(U(50))).toBe('out');
    expect(line).toContain('额度已用完，之后审核拿不准的 AI 交付不再自动请人看，只通知发布方（已有 3 次）');
    expect(line).toContain('PLATFORM_AUTO_VERIFY_DAILY_MAX');
    expect(autoVerifyLine(U(50))).not.toContain('已有');
    expect(autoVerifyLevel(U(0, 0))).toBe('out');
  });
});
