// FIN-073 资金操作的幂等键（104 号 spec）。
//
// 服务端从 V1 起就支持 `Idempotency-Key`，14.6 写着「资金类强制」——而两端的
// SDK 从来没有发过这个头，服务端又把空键当成「不要幂等」。于是这条保护对真实用户
// **一次都没有生效过**：网络超时后再点一次「提现」，就是第二笔提现。
//
// 键代表「一次操作」，不是「一次请求」：
// - 同一次操作的重试（网络断了、5xx、服务端说还在处理）必须用**同一个**键，
//   服务端才会回放第一次的结果而不是再做一遍；
// - 有了确定结果（成功，或服务端明确拒绝）之后，下一次就是新操作，换新键；
// - 用户改了金额就是另一件事了，也换新键——否则会撞上
//   `idempotency_key_conflict`，那句话是写给开发者的，不是给用户看的。
import { ApiError } from './client';

/** 32 位十六进制。有 `crypto.randomUUID` 就用它（浏览器与新版 Node）；
 *  React Native 的 Hermes 上可能没有，退回 Math.random——键按用户隔离，
 *  它要的是不撞，不是不可猜。 */
export function newIdempotencyKey(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c?.randomUUID) return c.randomUUID().replace(/-/g, '');
  let out = '';
  while (out.length < 32) out += Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0');
  return out.slice(0, 32);
}

/** 结果不确定的失败：重试时必须带同一个键。 */
export function isUncertainFailure(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true; // 网络错误、超时：请求可能已经到了
  return err.status >= 500 || err.code === 'idempotency_in_progress';
}

/** 一个按钮背后的「当前这次操作」的键。 */
export class OperationKey {
  private key = newIdempotencyKey();
  private intent: string | null = null;

  /** 取这次操作的键。`intent` 变了（比如金额改了）就是另一次操作。 */
  for(intent: string): string {
    if (this.intent !== null && this.intent !== intent) this.key = newIdempotencyKey();
    this.intent = intent;
    return this.key;
  }

  /** SC-016（225 号 spec）取键 → 执行 → 按结果决定换不换键，一步做完（两端的按钮都这样用）。 */
  async run<T>(intent: string, fn: (key: string) => Promise<T>): Promise<T> {
    const key = this.for(intent);
    try {
      const out = await fn(key);
      this.settle();
      return out;
    } catch (err) {
      this.settle(err);
      throw err;
    }
  }

  /** 操作有了结果之后调用：确定的结果换新键，不确定的保留（下次点击是重试）。 */
  settle(err?: unknown): void {
    if (err === undefined || !isUncertainFailure(err)) {
      this.key = newIdempotencyKey();
      this.intent = null;
    }
  }
}
