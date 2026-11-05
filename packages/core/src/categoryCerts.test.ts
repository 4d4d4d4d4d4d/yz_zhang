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

describe('SCN-294b 发单人按这一单加选资质（407 号 spec）', () => {
  it('可加选的去空去重、类目本来就要的不再列', async () => {
    const { optionalCerts } = await import('./categoryCerts');
    expect(optionalCerts({ required_cert: '甲', extra_certs: [], optional_certs: ['乙', ' ', '乙', '甲'] })).toEqual(['乙']);
    expect(optionalCerts({ required_cert: '' })).toEqual([]);
    expect(optionalCerts(null)).toEqual([]);
  });

  it('换类目时只留新类目也能加的', async () => {
    const { keepOfferedCerts } = await import('./categoryCerts');
    expect(keepOfferedCerts(['高处作业操作证', '民用无人机操控员执照'], { required_cert: '', optional_certs: ['高处作业操作证'] }))
      .toEqual(['高处作业操作证']);
    expect(keepOfferedCerts(['高处作业操作证'], { required_cert: '' })).toEqual([]);
  });

  it('任务上的一句：畸形不显示', async () => {
    const { taskCertsLine } = await import('./categoryCerts');
    expect(taskCertsLine({ task_certs: ['高处作业操作证'] })).toBe('这一单另外要「高处作业操作证」，报名的人要有审核通过的证件');
    expect(taskCertsLine({ task_certs: [] })).toBe('');
    expect(taskCertsLine({ task_certs: 'x' })).toBe('');
    expect(taskCertsLine(null)).toBe('');
  });
});
