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
    await client.submitCertification({
      name: '律师', holderName: '张三', certNumber: 'A1234',
      issuer: '司法局', expiresAt: '2030-01-01T00:00:00', images: ['f1.png'],
    });
    await client.verifyAnchorChain();
    const urls = fetchImpl.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([
      'http://x/api/v1/users/9/block',
      'http://x/api/v1/messages/11/recall',
      'http://x/api/v1/users/me/certifications',
      'http://x/api/v1/anchors/verify',
    ]);
    // CERT-060 这里原本断言的是 `{name, license_no}`——**服务端在 V76 就不收这个形状了**，
    // 而这条测试照样绿，因为它打的是 mock fetch：只验证「我发出的请求长这样」，
    // 从不验证「服务端认不认」。断言一个错的契约比不断言更糟，它会让人以为已经验过了。
    const [, certInit] = fetchImpl.mock.calls[2];
    expect(JSON.parse(certInit.body)).toEqual({
      name: '律师', holder_name: '张三', cert_number: 'A1234',
      issuer: '司法局', expires_at: '2030-01-01T00:00:00', images: ['f1.png'],
    });
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

  it('LAW-031 同意/撤回打到各自 scope 的路径（撤回不能误发成授权）', async () => {
    const { client, fetchImpl } = makeClient(200, { scope: 'location', revoked: true });
    await client.revokeConsent('location');
    await client.grantConsent('payment');
    expect(fetchImpl.mock.calls.map((c: unknown[]) => c[0])).toEqual([
      'http://x/api/v1/legal/consents/location/revoke',
      'http://x/api/v1/legal/consents/payment/grant',
    ]);
    expect(fetchImpl.mock.calls[0][1].method).toBe('POST');
  });

  it('CAP-031 login 确实把验证码令牌发出去了', async () => {
    // UI 做了而 SDK 不传，等于没做——V56 就是这么留下缺口的
    const { client, fetchImpl } = makeClient(200, { token: 't', user: {} });
    await client.login('13800000000', 'pw', 'the-token');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      phone: '13800000000', password: 'pw', captcha_token: 'the-token',
    });
  });

  it('CAP-010 不传令牌时仍是合法请求（老调用方不被破坏）', async () => {
    const { client, fetchImpl } = makeClient(200, { token: 't', user: {} });
    await client.login('13800000000', 'pw');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body).captcha_token).toBe('');
  });

  it('CAP-002 验证码配置走公开端点', async () => {
    const { client, fetchImpl } = makeClient(200, { provider: 'none', enforcing: false });
    await client.captchaConfig();
    expect(fetchImpl.mock.calls[0][0]).toBe('http://x/api/v1/auth/captcha-config');
  });

  it('DSPC-020 被诉方能按任务找到纠纷（他只知道任务 id）', async () => {
    // 发起方能从 openDispute() 的返回值拿到 dispute_id，被诉方拿不到——
    // 他收到的通知就只说「任务 #N 有纠纷」。没有这条路，他连程序在哪都找不到。
    const { client, fetchImpl } = makeClient(200, { id: 7, task_id: 17 });
    await client.disputeByTask(17);
    expect(fetchImpl.mock.calls[0][0]).toBe('http://x/api/v1/tasks/17/dispute');
    expect(fetchImpl.mock.calls[0][1].method).toBe('GET');
  });

  it('DSPC-001 答辩真的发得出去', async () => {
    // 服务端把两造兼听当作裁决的硬性前置，而在此之前没有任何客户端能写入
    // 这张表——那道前置永远只能靠等答辩期超时满足，等于每份决定都是缺席裁决。
    const { client, fetchImpl } = makeClient(201, { id: 1, role: 'respondent' });
    await client.addDisputeStatement(7, '已按约定完成，附现场照片。', ['u1']);
    expect(fetchImpl.mock.calls[0][0]).toBe('http://x/api/v1/disputes/7/statements');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      content: '已按约定完成，附现场照片。', attachments: ['u1'],
    });
  });

  it('DSPC-020 陈述列表与申诉各有其方法', async () => {
    const { client, fetchImpl } = makeClient(200, []);
    await client.disputeStatements(7);
    await client.appealDispute(7);
    expect(fetchImpl.mock.calls.map((c: unknown[]) => c[0])).toEqual([
      'http://x/api/v1/disputes/7/statements',
      'http://x/api/v1/disputes/7/appeal',
    ]);
    expect(fetchImpl.mock.calls[1][1].method).toBe('POST');
  });

  it('TAX-021 代扣明细走 finance 前缀', async () => {
    const { client, fetchImpl } = makeClient(200, { mode: 'withholding', items: [] });
    await client.myTax();
    expect(fetchImpl.mock.calls[0][0]).toBe('http://x/api/v1/finance/my-tax');
  });

  it('LAW-030 协议更新被后端拒绝时，错误码原样透出给页面', async () => {
    const { client } = makeClient(409, {
      detail: { code: 'agreement_update_required', message: '《隐私政策》已更新' },
    });
    const err = await client.apply(1).catch((e) => e);
    expect(err.status).toBe(409);
    expect(err.code).toBe('agreement_update_required');
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

// =====================================================================
// CLI-062 V73~V79 六条线的客户端入口。改造前它们在 SDK 里**一个方法都没有**：
// 服务端完整、测试全绿、文档齐备，而用户点不到（57 号 spec）。
// =====================================================================
describe('六条线的客户端入口', () => {
  it('AGT 邀请助理把 agent_user_id 放在查询串上（服务端就是这么收的）', async () => {
    const { client, fetchImpl } = makeClient(201, { id: 1, status: 'pending', agent_user_id: 9 });
    await client.inviteAgent(3, 9);
    expect(fetchImpl.mock.calls[0][0]).toBe('http://x/api/v1/tasks/3/agent-apply?agent_user_id=9');
  });

  it('AGT 可用助理返回里带不可用的理由——界面要显示的是它，不是空列表', async () => {
    const { client } = makeClient(200, [
      { user_id: 9, name: '开发助理', domains: ['软件开发'], eligible: false,
        reason: '需到场完成的任务不能由 AI 助理执行',
        max_task_budget_cents: 50000, runs_total: 0, runs_succeeded: 0, is_active: true },
    ]);
    const rows = await client.eligibleAgents(3);
    expect(rows[0].eligible).toBe(false);
    expect(rows[0].reason).toContain('到场');
  });

  it('VER 提交结论三个字段都带上（revised 时修正稿是交付物）', async () => {
    const { client, fetchImpl } = makeClient(200, { outcome: 'revised', unblocked: true, delivered: true });
    await client.submitVerificationOutcome(5, 'revised', '补齐了缺的一节', '修正稿正文');
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://x/api/v1/verification-orders/5/outcome');
    expect(JSON.parse(init.body)).toEqual({
      outcome: 'revised', comment: '补齐了缺的一节', revised_output: '修正稿正文',
    });
  });

  it('COOP 加入合作体必须自己带风险揭示书版本（代签的知情同意不是知情同意）', async () => {
    const { client, fetchImpl } = makeClient(201, { venture_id: 2, user_id: 7, role: 'member' });
    await client.joinVenture(2, 'v1');
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://x/api/v1/ventures/2/members');
    expect(JSON.parse(init.body)).toEqual({ risk_disclosure_version: 'v1' });
  });

  it('TEAM 支出申请把 task_id 显式置 null，而不是漏掉这个键', async () => {
    const { client, fetchImpl } = makeClient(201, { id: 1, status: 'pending', needed_approval: false, reason: '' });
    await client.requestTeamSpend(4, 5000, '买素材');
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      amount_cents: 5000, purpose: '买素材', task_id: null,
    });
  });

  it('OAPI 轮换密钥是 POST，吊销是 DELETE——两个动作语义不同', async () => {
    const { client, fetchImpl } = makeClient(200, {});
    await client.rotateApiKey(3);
    await client.revokeApiKey(3);
    expect(fetchImpl.mock.calls[0][0]).toBe('http://x/api/v1/developer/api-keys/3/rotate');
    expect(fetchImpl.mock.calls[0][1].method).toBe('POST');
    expect(fetchImpl.mock.calls[1][1].method).toBe('DELETE');
  });

  it('CERT 提交资质带影像与持证人姓名（V76 的真实契约）', async () => {
    const { client, fetchImpl } = makeClient(201, { id: 1, name: '电工', status: 'pending', certifications: [] });
    await client.submitCertification({
      name: '电工', holderName: '李四', certNumber: 'E-9', images: ['a.png'],
    });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({
      name: '电工', holder_name: '李四', cert_number: 'E-9',
      issuer: '', expires_at: null, images: ['a.png'],
    });
  });
});
