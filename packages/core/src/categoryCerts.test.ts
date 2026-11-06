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

describe('SCN-294e 推荐里因为没证被排除了几个人', () => {
  it('有人只差加选的那一张就说出来；没人能接时换个说法', async () => {
    const { certGapLine } = await import('./categoryCerts');
    const g = { required: ['高处作业操作证', '低压电工作业操作证'], task_certs: ['高处作业操作证', '低压电工作业操作证'], pool: 5, eligible: 1, excluded: 4,
      only_missing: [{ cert: '高处作业操作证', count: 1 }, { cert: '低压电工作业操作证', count: 2 }] };
    expect(certGapLine(g)).toBe('另有 4 个人因为没有「高处作业操作证」「低压电工作业操作证」没进推荐；其中 1 人只差你加选的「高处作业操作证」，2 人只差你加选的「低压电工作业操作证」。这张证真用不上的话，下次发单别勾');
    expect(certGapLine({ ...g, eligible: 0, only_missing: [] })).toBe('现在没有人同时有「高处作业操作证」「低压电工作业操作证」，4 个人因此没进推荐');
  });
  it('没人被排除、畸形响应：不画', async () => {
    const { certGapLine } = await import('./categoryCerts');
    expect(certGapLine({ required: [], excluded: 0, eligible: 3, pool: 3, task_certs: [], only_missing: [] })).toBe('');
    expect(certGapLine({ required: ['x'], excluded: 0 })).toBe('');
    expect(certGapLine({ required: 'x' as unknown as string[], excluded: 2 })).toBe('');
    expect(certGapLine({ required: ['x'], excluded: 2, eligible: 1, only_missing: 'bad' as unknown as [] })).toBe('另有 2 个人因为没有「x」没进推荐');
    expect(certGapLine(null)).toBe('');
    // 只差人数是 0、或条目畸形的，不写「其中 0 人只差……」
    expect(certGapLine({ required: ['x'], excluded: 2, eligible: 1,
      only_missing: [{ cert: 'x', count: 0 }, { cert: 'y' } as unknown as { cert: string; count: number }] })).toBe('另有 2 个人因为没有「x」没进推荐');
  });
});

describe('SCN-294c 发布后去掉加选资质', () => {
  it('只有确实是这一单加选、只差人数大于 0 的才能一键去掉', async () => {
    const { relaxableCerts } = await import('./categoryCerts');
    expect(relaxableCerts({ task_certs: ['高处作业操作证'], only_missing: [{ cert: '高处作业操作证', count: 2 }, { cert: '健康证明', count: 3 }] }))
      .toEqual(['高处作业操作证']);
    expect(relaxableCerts({ task_certs: ['高处作业操作证'], only_missing: [{ cert: '高处作业操作证', count: 0 }] })).toEqual([]);
    expect(relaxableCerts({ task_certs: 'x' as unknown as string[], only_missing: [{ cert: 'x', count: 1 }] })).toEqual([]);
    expect(relaxableCerts(null)).toEqual([]);
  });
  it('去掉一张，其余照留', async () => {
    const { dropCertPatch } = await import('./categoryCerts');
    expect(dropCertPatch({ task_certs: ['高处作业操作证', '低压电工作业操作证'] }, '高处作业操作证')).toEqual({ task_certs: ['低压电工作业操作证'] });
    expect(dropCertPatch({ task_certs: null }, 'x')).toEqual({ task_certs: [] });
  });
});
