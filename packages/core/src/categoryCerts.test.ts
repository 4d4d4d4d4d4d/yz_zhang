// SCN-181（307 号 spec）类目的全部资质
import { describe, expect, it } from 'vitest';
import { categoryCerts, categoryCertsText } from './categoryCerts';

describe('SCN-181 类目的全部资质', () => {
  it('主资质在前、再加其余的，去空去重；老服务端没有 extra_certs 照旧', () => {
    expect(categoryCerts({ required_cert: '健康证明', extra_certs: [' 无犯罪记录证明 ', '', '健康证明'] })).toEqual(['健康证明', '无犯罪记录证明']);
    expect(categoryCerts({ required_cert: '律师' })).toEqual(['律师']);
    expect(categoryCerts({ required_cert: '' })).toEqual([]);
    expect(categoryCerts(undefined)).toEqual([]);
  });
  it('写法', () => {
    expect(categoryCertsText({ required_cert: '健康证明', extra_certs: ['无犯罪记录证明'] })).toBe('「健康证明」「无犯罪记录证明」');
    expect(categoryCertsText({ required_cert: '' })).toBe('');
  });
});
