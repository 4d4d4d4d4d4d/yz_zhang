// REG-002（222 号 spec）什么失败才清掉登录态。两端共用。
import { describe, expect, it } from 'vitest';
import { ApiError } from './client';
import { isAuthRejection } from './session';

describe('REG-002 isAuthRejection', () => {
  it('服务端明确不认这个登录：清', () => {
    expect(isAuthRejection(new ApiError(401, 'x', ''))).toBe(true);
    for (const code of ['unauthenticated', 'session_revoked', 'account_banned', 'account_deleted']) {
      expect(isAuthRejection(new ApiError(403, code, ''))).toBe(true);
    }
  });
  it('断网、被取消、服务端出错、别的 403：不清', () => {
    expect(isAuthRejection(new TypeError('Failed to fetch'))).toBe(false);
    expect(isAuthRejection(new DOMException('aborted', 'AbortError'))).toBe(false);
    expect(isAuthRejection(new ApiError(500, 'internal', ''))).toBe(false);
    expect(isAuthRejection(new ApiError(403, 'forbidden', ''))).toBe(false);
    // 只认 SDK 从服务端响应里构造的错误：别处冒出来、恰好带个 status 的对象不算
    expect(isAuthRejection({ status: 401, code: 'unauthenticated' })).toBe(false);
  });
});
