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

describe('V1 接口', () => {
  it('里程碑接口路径与动词正确', async () => {
    const { client, fetchImpl } = makeClient(200, {});
    await client.deliverMilestone(3, 2);
    await client.acceptMilestone(3, 2);
    const urls = fetchImpl.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([
      'http://x/api/v1/contracts/3/milestones/2/deliver',
      'http://x/api/v1/contracts/3/milestones/2/accept',
    ]);
  });

  it('变更单请求体字段对齐后端 schema', async () => {
    const { client, fetchImpl } = makeClient(201, { id: 1 });
    await client.proposeChange(5, 120000, '加需求');
    const [, init] = fetchImpl.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ new_amount_cents: 120000, reason: '加需求' });
  });

  it('feed scope 与筛选参数序列化', async () => {
    const { client, fetchImpl } = makeClient(200, []);
    await client.contentFeed('following', { tag: '保洁' });
    const [url] = fetchImpl.mock.calls[0];
    expect(url).toContain('scope=following');
    expect(url).toContain('tag=%E4%BF%9D%E6%B4%81');
  });

  it('圈层与邀约接口', async () => {
    const { client, fetchImpl } = makeClient(200, {});
    await client.joinCircle(7);
    await client.inviteToTask(9, 42, '来');
    const urls = fetchImpl.mock.calls.map((c) => c[0]);
    expect(urls[0]).toBe('http://x/api/v1/circles/7/join');
    expect(urls[1]).toBe('http://x/api/v1/tasks/9/invitations');
    const [, init] = fetchImpl.mock.calls[1];
    expect(JSON.parse(init.body)).toEqual({ user_id: 42, message: '来' });
  });

  it('黑名单/撤回/资质/存证接口路径', async () => {
    const { client, fetchImpl } = makeClient(200, {});
    await client.toggleBlock(9);
    await client.recallMessage(11);
    await client.addCertification('律师', 'A1234');
    await client.verifyAnchorChain();
    const urls = fetchImpl.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([
      'http://x/api/v1/users/9/block',
      'http://x/api/v1/messages/11/recall',
      'http://x/api/v1/users/me/certifications',
      'http://x/api/v1/anchors/verify',
    ]);
    const [, certInit] = fetchImpl.mock.calls[2];
    expect(JSON.parse(certInit.body)).toEqual({ name: '律师', license_no: 'A1234' });
  });

  it('澄清/模板/会话/导出接口（V3/V4）', async () => {
    const { client, fetchImpl } = makeClient(200, {});
    await client.clarify({ title: 'x', budget_cents: 100 });
    await client.taskTemplate('保洁');
    await client.mySessions();
    await client.exportContract(4);
    await client.createExperiencePost(7, '复盘内容复盘内容');
    const urls = fetchImpl.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([
      'http://x/api/v1/ai/clarify',
      'http://x/api/v1/task-templates?category=%E4%BF%9D%E6%B4%81',
      'http://x/api/v1/auth/sessions',
      'http://x/api/v1/contracts/4/export',
      'http://x/api/v1/tasks/7/experience-post',
    ]);
  });

  it('举报接口字段', async () => {
    const { client, fetchImpl } = makeClient(201, { id: 1, status: 'pending' });
    await client.report('content', 8, '违规');
    const [, init] = fetchImpl.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ target_type: 'content', target_id: 8, reason: '违规' });
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
