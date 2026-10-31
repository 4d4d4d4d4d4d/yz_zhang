/** CERT-053（348 号 spec）资质审核抽检：核准后抽到的交另一位审核员复看，维持或推翻（推翻即撤销资质）。 */
import { apiErrorText, type CertSpotCheckList } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

const REASON: Record<string, string> = { high_risk: '高风险资质全抽', random: '按比例抽到' };

export function CertSpotChecks() {
  const { client, me } = useApp();
  const [view, setView] = useState<CertSpotCheckList | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const v = await client.certSpotChecks().catch(() => null);
    setView(v && Array.isArray(v.items) ? v : null);
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  if (!view) return null;
  const reviewers = Array.isArray(view.reviewers) ? view.reviewers : [];
  return (
    <div className="card" aria-label="资质抽检">
      <h3>资质抽检（{view.items.length} 条待复看）</h3>
      <p className="muted">资质核准即生效；这里是第二双眼。不能复看自己审的；推翻要写理由，资质立刻撤销并通知持证人。</p>
      {reviewers.length > 0 && (
        <p className="muted">审核员被抽检：{reviewers.map((r) => `${r.nickname || `#${r.reviewer_id}`} 抽 ${r.sampled} 推翻 ${r.overturned}`).join('；')}</p>
      )}
      <ul>
        {view.items.map((s) => (
          <li key={s.id}>
            <strong>{s.name}</strong> <span className="muted">申请 #{s.application_id} · {REASON[s.reason] ?? s.reason} · 原审核 {s.reviewer_nickname || `#${s.reviewer_id}`}</span>
            {s.reviewer_id === me?.id ? <span className="muted"> · 自己审的，请另一位复看</span> : (
              <span className="row" style={{ gap: 6 }}>
                <input aria-label={`抽检 ${s.id} 的说明`} placeholder="说明（推翻时必填，持证人会看到）" value={notes[s.id] ?? ''}
                       onChange={(e) => setNotes({ ...notes, [s.id]: e.target.value })} />
                <button onClick={() => void act(() => client.confirmCertSpotCheck(s.id, (notes[s.id] ?? '').trim()))}>维持</button>
                <button className="danger" disabled={(notes[s.id] ?? '').trim().length < 4}
                        onClick={() => void act(() => client.overturnCertSpotCheck(s.id, (notes[s.id] ?? '').trim()))}>推翻并撤销</button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
