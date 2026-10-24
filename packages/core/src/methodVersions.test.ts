// AGT-097（239 号 spec）方法按版本分开的效果。
import { describe, expect, it } from 'vitest';
import { methodStepDiff, methodVersionCompare, methodVersionLines } from './methodVersions';

const v = (version: number | null, total: number, ok: number, bad: number, rate: number | null, spent = 0) =>
  ({ version, missions_total: total, missions_succeeded: ok, missions_failed: bad, missions_spent_cents: spent, success_rate: rate });

describe('AGT-097 methodVersionLines / methodVersionCompare', () => {
  it('只用过当前一版：不分版本、不比较', () => {
    const m = { version: 1, versions: [v(1, 4, 2, 1, 0.67)] };
    expect(methodVersionLines(m)).toEqual([]);
    expect(methodVersionCompare(m)).toBe('');
    expect(methodVersionLines({ version: 1, versions: [] })).toEqual([]);
    expect(methodVersionCompare({ version: 1, versions: [] })).toBe('');
  });

  it('改了还没用：写明新版还没用过，并列出旧版', () => {
    const m = { version: 2, versions: [v(1, 3, 1, 2, 0.33, 1500)] };
    expect(methodVersionLines(m)).toEqual(['第 1 版：用过 3 次，做成 1、没成 2，花了 ¥15.00；成功率 33%']);
    expect(methodVersionCompare(m)).toBe('第 2 版还没用过：用过几次后才看得出改了有没有变好');
  });

  it('两版都够样本：说清变好、变差还是没变；不够样本不比', () => {
    expect(methodVersionCompare({ version: 3, versions: [v(3, 4, 3, 1, 0.75), v(2, 3, 1, 2, 0.33)] }))
      .toBe('第 2 版成功率 33% → 第 3 版 75%：改了之后变好了');
    expect(methodVersionCompare({ version: 3, versions: [v(3, 3, 1, 2, 0.33), v(1, 4, 3, 1, 0.75)] }))
      .toBe('第 1 版成功率 75% → 第 3 版 33%：改了之后变差了，看看改了哪一步');
    expect(methodVersionCompare({ version: 2, versions: [v(2, 3, 2, 1, 0.67), v(1, 3, 2, 1, 0.67)] }))
      .toBe('第 1 版成功率 67% → 第 2 版 67%：没有变化');
    expect(methodVersionCompare({ version: 2, versions: [v(2, 1, 1, 0, null), v(1, 3, 2, 1, 0.67)] }))
      .toBe('做完的还少，先不比较第 1 版和第 2 版');
    expect(methodVersionCompare({ version: 2, versions: [v(2, 3, 2, 1, 0.67), v(1, 2, 0, 2, null)] }))
      .toBe('做完的还少，先不比较第 1 版和第 2 版');
  });

  it('记版本之前的编排单独一组，排在最后，也能作比较的对象', () => {
    const m = { version: 1, versions: [v(1, 3, 3, 0, 1), v(null, 5, 2, 3, 0.4)] };
    expect(methodVersionLines(m)[1]).toBe('记版本之前：用过 5 次，做成 2、没成 3，花了 ¥0.00；成功率 40%');
    expect(methodVersionCompare(m)).toBe('记版本之前成功率 40% → 第 1 版 100%：改了之后变好了');
  });
});

describe('AGT-098 methodStepDiff', () => {
  const st = (...t: string[]) => t.map((title) => ({ title, note: '' }));
  it('说清加了哪几步、去掉了哪几步；只改顺序或备注也说', () => {
    expect(methodStepDiff(st('打包', '搬运'), st('先列清单', '打包', '搬运'))).toBe('加了「先列清单」');
    expect(methodStepDiff(st('打包', '搬运', '验收'), st('打包'))).toBe('去掉了「搬运」「验收」');
    expect(methodStepDiff(st('打包', '搬运'), st('打包', '清点'))).toBe('加了「清点」；去掉了「搬运」');
    expect(methodStepDiff(st('打包', '搬运'), st('搬运', '打包'))).toBe('步骤一样，顺序改了');
    expect(methodStepDiff(st('打包'), [{ title: '打包', note: '用纸箱' }])).toBe('步骤一样，备注改了');
  });
});
