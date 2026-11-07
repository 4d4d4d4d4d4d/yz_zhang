// APP-093（V213）畸形响应：列表接口在 SDK 里收成空表；对象响应由 hasLists 判断像不像样。两端共用。
import { describe, expect, it } from 'vitest';
import { PlatformClient } from './client';
import { MALFORMED_TEXT, hasLists } from './decompose';

function clientReturning(body: unknown) {
  const fetchImpl = (async () => ({ ok: true, status: 200, text: async () => JSON.stringify(body) })) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('APP-093 列表接口的畸形响应收成空表', () => {
  for (const [label, body] of [['{}', {}], ['null', null], ['"x"', 'x'], ['{items:[]}', { items: [] }]] as Array<[string, unknown]>) {
    it(`响应 ${label} → []`, async () => {
      const c = clientReturning(body);
      expect(await c.workbenchItems()).toEqual([]);
      expect(await c.notifications()).toEqual([]);
      expect(await c.categories()).toEqual([]);
    });
  }

  it('数组原样返回，不拷贝不改', async () => {
    const rows = [{ id: 1, name: '跑腿', required_cert: '' }];
    expect(await clientReturning(rows).categories()).toEqual(rows);
  });

  it('对象接口不受影响：照旧原样给页面判断', async () => {
    expect(await clientReturning({}).workbenchOverview()).toEqual({});
  });
});

describe('APP-093 hasLists：对象响应像不像样', () => {
  it.each([
    [{ items: [] }, ['items'], true],
    [{ items: [], tags: [1] }, ['items', 'tags'], true],
    [{ items: [] }, ['items', 'tags'], false],
    [{ items: {} }, ['items'], false],
    [{}, ['items'], false],
    [null, ['items'], false],
    [[], ['items'], false],
    [[], [], false],                     // 数组不是对象响应，哪怕不点名字段
    ['x', ['items'], false],
    [{ anything: 1 }, [], true],
  ] as Array<[unknown, string[], boolean]>)('%j 的 %j → %s', (x, keys, want) => {
    expect(hasLists(x, ...keys)).toBe(want);
  });

  it('说明文字说清为什么、怎么办', () => {
    expect(MALFORMED_TEXT).toContain('格式不对');
    expect(MALFORMED_TEXT).toContain('刷新');
  });
});
