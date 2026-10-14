// SBX-100 端侧隐私沙箱（128 号 spec）与 INF-110 端上验算：参考值都由服务端的 Python 实现算出。
import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';
import { ApiError, PlatformClient } from './client';
import {
  CLOUD_AI_ENDPOINTS, LOCAL_REFUSAL, Sha256, base64ToBytes, askLocal, canRunModel, influenceLeaf, isCloudAiRequest, redact,
  routeInstruction, runLocal, sha256Hex, utf8, verifyInfluenceProof, verifyModelChunks, type LocalModel,
} from './sandbox';

describe('sha256（纯 TS）', () => {
  it('标准向量与中文', () => {
    expect(sha256Hex('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
    expect(sha256Hex('中文')).toBe('72726d8818f693066ceb69afa364218b692e62ea92b385782363780f47529c21');
    expect(sha256Hex('a'.repeat(1000))).toBe('41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3');
  });
  it('分块喂与一次喂结果一样（大模型文件分块校验）', () => {
    const data = utf8('a'.repeat(1000));
    const h = new Sha256();
    for (let i = 0; i < data.length; i += 37) h.update(data.subarray(i, i + 37));
    expect(h.hex()).toBe(sha256Hex(data));
    const chunks = [data.subarray(0, 63), data.subarray(63, 64), data.subarray(64)];
    expect(verifyModelChunks(chunks, '41EDECE42D63E8D9BF515A9BA6932E1C20CBC9F5A5D134645ADB5DB1B9737EA3').ok).toBe(true);
    expect(verifyModelChunks([data.subarray(1)], sha256Hex(data)).ok).toBe(false);
  });
});

describe('SBX-111 base64 分块读出的字节', () => {
  it('与原文一致，任意长度（含补位）', () => {
    for (const text of ['', 'a', 'ab', 'abc', '中文模型文件', 'x'.repeat(1001)]) {
      const b64 = Buffer.from(text, 'utf8').toString('base64');
      expect(Array.from(base64ToBytes(b64))).toEqual(Array.from(utf8(text)));
    }
    expect(sha256Hex(base64ToBytes(Buffer.from('abc').toString('base64')))).toBe(sha256Hex('abc'));
  });
});

describe('INF-110 影响力证明：端上独立验算', () => {
  const ROOT = '718822541a5ebd3b7c1edc780e87f7781418f735f682080886bcba71e0999fec';
  it('叶子与服务端逐字节一致（整数也写成 40.0）', () => {
    expect(influenceLeaf(1, '保洁', 40)).toBe('8ec26961732be44c1fcf731557b5992ed3734c757258ad8d91799b7b30d11b93');
    expect(influenceLeaf(2, '设计', 12.3)).toBe('52c901ddee33e895e231509c9dd61684dfd28d4a336e9c805afbf08453d0423f');
  });
  it('沿路径算到根；改了分数就对不上', () => {
    const path = ['517cb7e660ec3749ad7bfafe4d8b46b23bf5284561b820441270d9709d0b83f6',
      '9aeea9524a5f802870bef4fe57858f1d18db17f76c711c0ab7d92d54c4d1cf60'];
    expect(verifyInfluenceProof(influenceLeaf(2, '设计', 12.3), path, ROOT)).toBe(true);
    expect(verifyInfluenceProof(influenceLeaf(2, '设计', 99), path, ROOT)).toBe(false);
  });
});

describe('SBX-105 脱敏', () => {
  it('遮掉手机号、身份证、银行卡、邮箱、车牌，并说遮了什么', () => {
    const r = redact('联系 13812345678，身份证 110101199003071234，卡号 6222020200112233445，邮箱 lin@example.com，车牌沪A12345。');
    expect(r.text).not.toMatch(/13812345678|110101199003071234|6222020200112233445|lin@example\.com|沪A12345/);
    expect(r.text).toContain('138****5678');
    expect(r.hits.map((h) => h.kind).sort()).toEqual(['bank_card', 'email', 'id_card', 'phone', 'plate']);
    expect(redact('没有号码').hits).toEqual([]);
  });
});

describe('SBX-104 本机助手', () => {
  it('红线：要动钱、签署、发布、对外发送的不做', async () => {
    expect(routeInstruction('帮我把这笔钱转账给他')).toEqual({ refuse: LOCAL_REFUSAL });
    expect(await askLocal('直接发布这条', '内容')).toEqual({ refused: LOCAL_REFUSAL });
    expect(routeInstruction('拆成步骤')).toEqual({ skill: 'checklist' });
    expect(routeInstruction('有哪些待办')).toEqual({ skill: 'todos' });
    expect(routeInstruction('帮我回复一下')).toEqual({ skill: 'reply' });
    expect(routeInstruction('总结一下')).toEqual({ skill: 'summarize' });
  });
  it('规则引擎：抽待办、拆清单、摘要、改写、回复都给出结果，并写明不是模型', async () => {
    const memo = '周会纪要。客户希望下周三之前看到初稿。需要小王确认预算。会议气氛不错。记得把合同发给法务。';
    const todos = await runLocal('todos', memo);
    expect(todos.engine).toBe('rules');
    expect(todos.items).toEqual(['客户希望下周三之前看到初稿', '需要小王确认预算', '记得把合同发给法务']);
    expect(todos.notice).toContain('不是模型');
    const list = await runLocal('checklist', '- 买清洁剂\n- 预约上门时间\n- 验收');
    expect(list.items).toEqual(['买清洁剂', '预约上门时间', '验收']);
    const thin = await runLocal('checklist', '搬家');
    expect(thin.items.length).toBeGreaterThanOrEqual(3);
    const sum = await runLocal('summarize', '第一句讲背景。第二句讲预算是五千元。第三句讲预算的来源。第四句讲天气。第五句讲预算审批。');
    expect(sum.items.length).toBe(3);
    expect(sum.items[0]).toBe('第一句讲背景。');
    expect((await runLocal('rewrite', '这个啥时候能搞定呀！')).output).toBe('这个什么时候能完成。');
    expect((await runLocal('reply', '你好。周五能来吗？价格多少？')).items).toEqual(['周五能来吗', '价格多少']);
    expect((await runLocal('summarize', '   ')).notice).toContain('先写点内容');
  });
  it('有端侧模型就用模型；模型出错如实退回规则，不换成云端', async () => {
    const model: LocalModel = { id: 'qwen-0.5b-q4', generate: vi.fn(async () => '- 订场地\n- 发邀请') };
    const r = await runLocal('checklist', '办一场分享会', model);
    expect(r.engine).toBe('model');
    expect(r.items).toEqual(['订场地', '发邀请']);
    expect(r.notice).toContain('qwen-0.5b-q4');
    const broken: LocalModel = { id: 'x', generate: async () => { throw new Error('oom'); } };
    const f = await runLocal('todos', '需要买票。', broken);
    expect(f.engine).toBe('rules');
    expect(f.notice).toContain('没跑成');
  });
  it('设备跑不动就如实说', () => {
    expect(canRunModel({ min_ram_gb: 6, size_mb: 1000 }, { ram_gb: 4, free_disk_mb: 9000 }).reason).toContain('内存 4 GB');
    expect(canRunModel({ min_ram_gb: 3, size_mb: 1000 }, { ram_gb: 8, free_disk_mb: 500 }).reason).toContain('存储空间不够');
    expect(canRunModel({ min_ram_gb: 3, size_mb: 1000 }, { ram_gb: 8, free_disk_mb: 5000 }).ok).toBe(true);
  });
});

describe('SBX-102 云端 AI 守卫', () => {
  it('沙箱开着：云端 AI 请求不发出去；其他请求照常', async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, text: async () => '{"items":[]}' })) as unknown as typeof fetch;
    let on = true;
    const c = new PlatformClient({ baseUrl: '', getToken: () => 't', fetchImpl, sandbox: () => on });
    await expect(c.askNotebook('我的合同')).rejects.toMatchObject({ code: 'sandbox_cloud_ai_blocked' });
    await expect(c.workbenchBreakdown(3)).rejects.toBeInstanceOf(ApiError);
    expect(fetchImpl).not.toHaveBeenCalled();
    await c.sandboxModels();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    on = false;
    await c.askNotebook('我的合同');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
  it('清单覆盖带路径参数的接口', () => {
    expect(isCloudAiRequest('POST', '/packs/opc/assistants/finance/ask')).toBe(true);
    expect(isCloudAiRequest('GET', '/notebook/ask')).toBe(false);
    expect(isCloudAiRequest('POST', '/notebook/notes')).toBe(false);
    expect(CLOUD_AI_ENDPOINTS.length).toBeGreaterThanOrEqual(14);
  });
  it('本机助手这个文件不联网：不引用 client、不调 fetch、不发 XHR', () => {
    const src = readFileSync(new URL('./sandbox.ts', import.meta.url), 'utf8').replace(/\/\/.*$/gm, '');
    expect(src).not.toMatch(/from '\.\/client'|fetch\(|XMLHttpRequest|WebSocket|this\.request/);
  });
});
