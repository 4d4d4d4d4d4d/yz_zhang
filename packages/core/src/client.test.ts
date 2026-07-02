import { describe, expect, it, vi } from 'vitest';
import { ApiError, PlatformClient, TASK_STATUS_LABEL, fmtYuan } from './client';

function mockFetch(status: number, body: unknown) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  })) as unknown as typeof fetch;
}

function makeClient(status: number, body: unknown, token: string | null = 'tok') {
  const fetchImpl = mockFetch(status, body);
  const client = new PlatformClient({ baseUrl: 'http://x', getToken: () => token, fetchImpl });
  return { client, fetchImpl: fetchImpl as ReturnType<typeof vi.fn> };
}

describe('PlatformClient', () => {
  it('携带 Bearer token 与 API 前缀', async () => {
    const { client, fetchImpl } = makeClient(200, { id: 1 });
    await client.me();
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://x/api/v1/users/me');
    expect(init.headers['Authorization']).toBe('Bearer tok');
  });

  it('未登录时不带 Authorization', async () => {
    const { client, fetchImpl } = makeClient(200, [], null);
    await client.listTasks();
    const [, init] = fetchImpl.mock.calls[0];
    expect(init.headers['Authorization']).toBeUndefined();
  });

  it('listTasks 序列化查询参数并跳过空值', async () => {
    const { client, fetchImpl } = makeClient(200, []);
    await client.listTasks({ category: '保洁', max_km: 5, q: undefined, city: '' });
    const [url] = fetchImpl.mock.calls[0];
    expect(url).toContain('category=%E4%BF%9D%E6%B4%81');
    expect(url).toContain('max_km=5');
    expect(url).not.toContain('q=');
    expect(url).not.toContain('city=');
  });

  it('后端结构化错误映射为 ApiError（统一错误码结构）', async () => {
    const { client } = makeClient(403, {
      detail: { code: 'verification_required', message: '需先完成实名认证' },
    });
    const err = await client.apply(1).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe('verification_required');
    expect(err.message).toBe('需先完成实名认证');
  });

  it('POST 请求体字段与后端 schema 对齐', async () => {
    const { client, fetchImpl } = makeClient(201, { id: 9 });
    await client.apply(7, '有经验', 5000);
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://x/api/v1/tasks/7/applications');
    expect(JSON.parse(init.body)).toEqual({ message: '有经验', bid_cents: 5000 });
  });
});

describe('helpers', () => {
  it('fmtYuan 分转元', () => {
    expect(fmtYuan(20000)).toBe('¥200.00');
    expect(fmtYuan(1)).toBe('¥0.01');
  });

  it('任务状态全部有中文标签（与后端状态机对齐）', () => {
    for (const s of ['draft', 'published', 'matched', 'in_progress', 'pending_acceptance', 'completed', 'cancelled', 'disputed']) {
      expect(TASK_STATUS_LABEL[s]).toBeTruthy();
    }
  });
});
