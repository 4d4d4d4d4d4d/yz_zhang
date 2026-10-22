// API-056（235 号 spec）后台「开放 API 配额」：给某个接入方单独调账号每日总配额（写理由、可设天数），改回默认。
import { apiErrorText, formatDate, type ApiAccountQuotaRow } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

export function ApiQuotasAdmin() {
  const { client } = useApp();
  const [rows, setRows] = useState<ApiAccountQuotaRow[]>([]);
  const [userId, setUserId] = useState('');
  const [quota, setQuota] = useState('');
  const [days, setDays] = useState('');
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const r = await client.apiAccountQuotas().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function run(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div className="card" aria-label="开放 API 配额">
      <h3>开放 API 配额</h3>
      <p className="muted">默认每个账号所有 Key 合计有每日上限。签了接入合同、压测等情况可以给单个账号调高（或调低），写理由、可设天数，过期自动恢复默认；对方会收到通知。</p>
      <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
        <input aria-label="用户编号" placeholder="用户编号" value={userId} onChange={(e) => setUserId(e.target.value)} style={{ width: 100 }} />
        <input aria-label="每日配额" placeholder="每日配额（次）" type="number" min={1} value={quota} onChange={(e) => setQuota(e.target.value)} style={{ width: 130 }} />
        <input aria-label="有效天数" placeholder="有效天数（空 = 一直）" type="number" min={1} max={366} value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 150 }} />
        <input aria-label="调整理由" className="grow" placeholder="理由（至少 4 个字，进审计）" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button disabled={!userId || !quota || reason.trim().length < 4} onClick={() => void run(() => client.setApiAccountQuota(Number(userId),
          { daily_quota: Number(quota), reason: reason.trim(), ...(days ? { days: Number(days) } : {}) }), `已调整 #${userId} 的账号配额`)}>调整</button>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {rows.length === 0 && <p className="muted">还没有单独调过配额的账号。</p>}
      <ul>
        {rows.map((r) => (
          <li key={r.user_id} data-testid={`api-quota-${r.user_id}`}>
            {r.nickname || `#${r.user_id}`}：每天 {r.daily_quota} 次（默认 {r.default_quota}）· 今天用了 {r.today_used}
            {r.expires_at ? ` · ${r.active ? '到' : '已于'} ${formatDate(r.expires_at)}${r.active ? '' : ' 过期，已按默认'}` : ' · 一直有效'} · {r.reason}
            {' '}<button className="text-link" onClick={() => {
              const why = window.prompt('改回默认的理由（至少 4 个字）：') ?? '';
              if (why.trim().length >= 4) void run(() => client.resetApiAccountQuota(r.user_id, why.trim()), `已把 #${r.user_id} 改回默认配额`);
            }}>改回默认</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
