// API-056（235 号 spec）开放 API 账号配额：平台单独调过的，两端用户页写明（同一句话）。
import { formatDate } from './time';
import type { ApiKeyUsageView } from './types';

/** 「平台为你单独调过账号配额（到 2026-11-21）」；没调过、老服务端返回空串 */
export function accountQuotaNote(u: Pick<ApiKeyUsageView, 'account_quota_custom' | 'account_quota_expires_at'>): string {
  if (!u.account_quota_custom) return '';
  return u.account_quota_expires_at ? `平台为你单独调过账号配额（到 ${formatDate(u.account_quota_expires_at)}，之后恢复默认）` : '平台为你单独调过账号配额';
}
