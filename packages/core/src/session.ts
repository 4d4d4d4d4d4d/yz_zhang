import { ApiError } from './client';

/** REG-002（222 号 spec）这次失败是不是「服务端不认这个登录了」。只有这些才该清掉本地的登录态：
 *  断网、超时、页面跳走时被浏览器取消的请求（net::ERR_ABORTED）都不是——以前一律清掉，手机信号一抖、
 *  或者首页还没加载完就点去别的页，人就被登出了。两端同一条判断。 */
const AUTH_REJECTED = new Set(['unauthenticated', 'session_revoked', 'account_banned', 'account_deleted']);

export function isAuthRejection(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 401 || (e.status === 403 && AUTH_REJECTED.has(e.code)));
}
