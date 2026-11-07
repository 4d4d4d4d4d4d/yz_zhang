// API-056（235 号 spec）开放 API 账号配额：平台单独调过的，两端用户页写明（同一句话）。
import { formatDate } from './time';
import type { ApiKeyUsageView, ApiQuotaRequest } from './types';

/** 「平台为你单独调过账号配额（到 2026-11-21）」；没调过、老服务端返回空串 */
export function accountQuotaNote(u: Pick<ApiKeyUsageView, 'account_quota_custom' | 'account_quota_expires_at'>): string {
  if (!u.account_quota_custom) return '';
  return u.account_quota_expires_at ? `平台为你单独调过账号配额（到 ${formatDate(u.account_quota_expires_at)}，之后恢复默认）` : '平台为你单独调过账号配额';
}

const REQ_STATUS: Record<string, string> = { pending: '待批', approved: '已批准', rejected: '没通过', withdrawn: '已撤回' };

/** API-057（241 号 spec）一条提额申请的一句话：两端开发者页与后台同一句 */
export function quotaRequestLine(r: Pick<ApiQuotaRequest, 'id' | 'daily_quota' | 'days' | 'purpose' | 'status' | 'decision_note'
  | 'granted_quota' | 'granted_days'>): string {
  const want = `#${r.id} 申请每天 ${r.daily_quota} 次${r.days ? `、${r.days} 天` : '、长期'}（${r.purpose}）`;
  const status = REQ_STATUS[r.status] ?? r.status;
  if (r.status === 'approved') {
    const same = r.granted_quota === r.daily_quota && r.granted_days === r.days;
    const granted = same ? '' : `：批了每天 ${r.granted_quota} 次${r.granted_days ? `、${r.granted_days} 天` : '、长期'}`;
    return `${want} · ${status}${granted}${r.decision_note ? `（${r.decision_note}）` : ''}`;
  }
  if (r.status === 'rejected') return `${want} · ${status}：${r.decision_note}`;
  return `${want} · ${status}`;
}
