// FIN-073 资金操作的幂等键（104 号 spec）。
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, PlatformClient } from './client';
import { OperationKey, isUncertainFailure, newIdempotencyKey } from './idempotency';

afterEach(() => vi.unstubAllGlobals());

describe('newIdempotencyKey', () => {
  it('32 位十六进制，且每次不同（服务端上限 80）', () => {
    const keys = new Set(Array.from({ length: 200 }, newIdempotencyKey));
    expect(keys.size).toBe(200);
    for (const k of keys) expect(k).toMatch(/^[0-9a-f]{32}$/);
  });

  it('没有 crypto.randomUUID（Hermes）时退回也能用', () => {
    vi.stubGlobal('crypto', undefined);
    const keys = new Set(Array.from({ length: 200 }, newIdempotencyKey));
    expect(keys.size).toBe(200);
    for (const k of keys) expect(k).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe('OperationKey：一次操作一个键', () => {
  it('结果不确定（网络断、5xx、还在处理）时保留——下一次点击是重试', () => {
    const op = new OperationKey();
    const k = op.for('topup:100');
    for (const err of [new TypeError('Failed to fetch'), new ApiError(502, 'error', 'x'),
      new ApiError(409, 'idempotency_in_progress', 'x')]) {
      expect(isUncertainFailure(err)).toBe(true);
      op.settle(err);
      expect(op.for('topup:100')).toBe(k);
    }
  });

  it('成功或服务端明确拒绝之后换新键——下一次是新操作', () => {
    const op = new OperationKey();
    const a = op.for('topup:100');
    op.settle();
    const b = op.for('topup:100');
    expect(b).not.toBe(a);
    op.settle(new ApiError(400, 'insufficient_balance', '可用余额不足'));
    expect(op.for('topup:100')).not.toBe(b);
  });

  it('金额改了就是另一件事——否则会撞上写给开发者看的 idempotency_key_conflict', () => {
    const op = new OperationKey();
    const a = op.for('withdraw:100');
    op.settle(new TypeError('network'));
    expect(op.for('withdraw:200')).not.toBe(a);
  });
});

describe('充值与提现带上 Idempotency-Key', () => {
  it('两个方法都把键放进请求头', async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200, text: async () => '{}' }));
    const client = new PlatformClient({ baseUrl: '', getToken: () => 't', fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.topup(100, 'k-topup');
    await client.withdraw(100, 'k-withdraw');
    const headers = fetchImpl.mock.calls.map((c) => (c as unknown as [string, { headers: Record<string, string> }])[1].headers);
    expect(headers[0]['Idempotency-Key']).toBe('k-topup');
    expect(headers[1]['Idempotency-Key']).toBe('k-withdraw');
    expect(headers[0]['Authorization']).toBe('Bearer t');
  });
});
