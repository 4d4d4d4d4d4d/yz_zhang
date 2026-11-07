// SCN-144（214 号 spec）服务对象是未成年人的单：详情上的一句话与发布页的请求体。两端共用。
import { describe, expect, it } from 'vitest';
import { minorPayload, minorTaskLine } from './minor';

describe('SCN-144 minorTaskLine', () => {
  it('写明安排方式与要求的证明；不涉及未成年人是空串', () => {
    expect(minorTaskLine({ minor_involved: true, guardian_mode: 'public_place' })).toBe('服务对象是未成年人 · 在公开场所 · 接单要有平台审核通过的无犯罪记录证明');
    expect(minorTaskLine({ minor_involved: true, guardian_mode: '' })).toBe('服务对象是未成年人 · 接单要有平台审核通过的无犯罪记录证明');
    expect(minorTaskLine({ minor_involved: false, guardian_mode: '' })).toBe('');
    expect(minorTaskLine(null)).toBe('');
  });
});

describe('SCN-144 minorPayload', () => {
  it('勾了才带，没勾一项都不带', () => {
    expect(minorPayload(true, 'guardian_present', true)).toEqual({ minor_involved: true, guardian_mode: 'guardian_present', guardian_consented: true });
    expect(minorPayload(false, 'guardian_present', true)).toEqual({});
  });
});
