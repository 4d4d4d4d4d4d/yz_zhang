import { describe, expect, it } from 'vitest';
import { parseVerifierId, verifyTriggerLabel } from './designatedVerifier';

describe('VER-050 点名核验人（372 号 spec）', () => {
  it('空着就是不点名；正整数是编号；其他算填错', () => {
    expect(parseVerifierId('')).toBeUndefined();
    expect(parseVerifierId('   ')).toBeUndefined();
    expect(parseVerifierId('42')).toBe(42);
    expect(parseVerifierId(' 7 ')).toBe(7);
    for (const bad of ['0', '-3', '4.2', 'abc', '老周', '12345678901']) expect(parseVerifierId(bad)).toBeNull();
  });

  it('三种来路说清谁付费', () => {
    expect(verifyTriggerLabel('designated')).toBe('发布方点名请你核验（发布方付费）');
    expect(verifyTriggerLabel('escalation')).toContain('平台付费');
    expect(verifyTriggerLabel('requested')).toBe('发布方主动申请核验');
    expect(verifyTriggerLabel(undefined)).toBe('核验单');
  });
});
