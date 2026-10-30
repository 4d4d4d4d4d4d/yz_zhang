/** SCN-219（336 号 spec）被发单拦截挡下时申请人工复核：发布页的申请框 + 后台的复核队列。 */
import { apiErrorText, ERRAND_REVIEW_MIN_EXPLANATION, errandReviewLine, type ErrandReviewAdminItem, type ErrandReviewItem } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** 发布页：被拦下时出现。原样带上标题和说明（一字不差才认），加一句「我要办的到底是什么」。 */
export function ErrandReviewRequest({ title, description }: { title: string; description: string }) {
  const { client } = useApp();
  const [open, setOpen] = useState(false);
  const [explanation, setExplanation] = useState('');
  const [done, setDone] = useState<ErrandReviewItem | null>(null);
  const [error, setError] = useState('');
  if (done) return <p className="muted" role="status">已申请复核：{errandReviewLine(done)}</p>;
  if (!open) {
    return <button type="button" className="text-link" onClick={() => setOpen(true)}>觉得拦错了？申请人工复核</button>;
  }
  return (
    <div aria-label="申请人工复核" className="card" style={{ marginTop: 6 }}>
      <p className="muted">运营会看你的标题、说明和下面这句话。通过后这段文字可以发一单；改了文字要重新判断。</p>
      <textarea aria-label="复核说明" placeholder="你要办的到底是什么事、为什么不是被拦的那一类" value={explanation}
                onChange={(e) => setExplanation(e.target.value)} maxLength={300} />
      <button type="button" disabled={explanation.trim().length < ERRAND_REVIEW_MIN_EXPLANATION}
              onClick={() => {
                setError('');
                client.requestErrandReview(title, description, explanation.trim()).then(setDone).catch((e) => setError(apiErrorText(e)));
              }}>提交复核</button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** 后台：在等的发单复核。看原文和说明，通过（放行一单）或维持（写理由，对方会看到）。 */
export function ErrandReviews() {
  const { client, me } = useApp();
  const [rows, setRows] = useState<ErrandReviewAdminItem[] | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const v = await client.errandReviews().catch(() => null);
    setRows(Array.isArray(v) ? v : null);
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  if (!rows) return null;
  return (
    <div aria-label="发单复核" style={{ marginTop: 12 }}>
      <h4>发单复核（{rows.length} 条在等）</h4>
      <p className="muted">发单拦截只看文字、会误拦。看原文和对方的说明：通过放行这段文字发一单；维持要写理由。</p>
      {rows.length === 0 && <p className="muted">没有在等的。</p>}
      <ul>
        {rows.map((r) => (
          <li key={r.id}>
            <strong>{r.title}</strong> <span className="muted">（{r.kind_label} · {r.nickname || `用户 ${r.user_id}`} · 等了 {r.waited_hours} 小时）</span>
            <div className="muted">{r.description}</div>
            <div>说明：{r.explanation}</div>
            {r.user_id === me?.id ? <span className="muted">自己提出的，请另一位运营处理</span> : (
              <div className="row" style={{ gap: 6 }}>
                <input aria-label={`复核 ${r.id} 的说明`} placeholder="说明（维持时必填，对方会看到）" value={notes[r.id] ?? ''}
                       onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} />
                <button onClick={() => void act(() => client.approveErrandReview(r.id, (notes[r.id] ?? '').trim()))}>通过</button>
                <button disabled={(notes[r.id] ?? '').trim().length < 4}
                        onClick={() => void act(() => client.rejectErrandReview(r.id, (notes[r.id] ?? '').trim()))}>维持拦截</button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
