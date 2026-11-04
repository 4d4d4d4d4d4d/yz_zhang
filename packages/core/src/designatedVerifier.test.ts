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

describe('VER-050c 从合作过的人里点名（376 号 spec）', () => {
  it('能点的写名字和合作次数；不能点的带上原因', async () => {
    const { verifierCandidateLine } = await import('./designatedVerifier');
    expect(verifierCandidateLine({ user_id: 5, nickname: '小林', times: 3, eligible: true, reason: '' })).toBe('小林 · 合作过 3 次');
    expect(verifierCandidateLine({ user_id: 6, nickname: '小白', times: 1, eligible: false, reason: '账号不可用' })).toBe('小白 · 合作过 1 次（现在不能点：账号不可用）');
    expect(verifierCandidateLine({ user_id: 7 })).toBe('#7');
  });
});
