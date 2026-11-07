// NTF-073（268 号 spec）点推送进来时报「从推送点开」：只认公告推送里的 announcement_id；报失败不抛。
import { PlatformClient } from '@platform/core';
import { reportPushOpened } from './pushOpen';

function makeClient(calls: Array<{ path: string; body: unknown }>, fail = false) {
  const fetchImpl = (async (url: string, init?: { body?: string }) => {
    calls.push({ path: String(url).replace(/^.*\/api\/v1/, ''), body: init?.body ? JSON.parse(init.body) : null });
    if (fail) return { ok: false, status: 404, text: async () => JSON.stringify({ detail: { code: 'not_found', message: '没有' } }) };
    return { ok: true, status: 200, text: async () => JSON.stringify({ notification_id: 3, recorded: true }) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

describe('NTF-073 点推送进来', () => {
  it('公告推送报 announcement_id', async () => {
    const calls: Array<{ path: string; body: unknown }> = [];
    expect(await reportPushOpened(makeClient(calls), { category: 'announcement', announcement_id: 7 })).toBe(true);
    expect(calls).toEqual([{ path: '/notifications/push-opened', body: { announcement_id: 7 } }]);
  });
  it('不是公告的推送、id 不对都不报；服务端报错也不抛', async () => {
    const calls: Array<{ path: string; body: unknown }> = [];
    const c = makeClient(calls);
    for (const d of [{ category: 'task' }, { announcement_id: '7' }, { announcement_id: 0 }, { announcement_id: 1.5 }, null, undefined]) {
      expect(await reportPushOpened(c, d)).toBe(false);
    }
    expect(calls).toEqual([]);
    expect(await reportPushOpened(makeClient([], true), { announcement_id: 7 })).toBe(false);
  });
});
