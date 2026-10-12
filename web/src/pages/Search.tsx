import { apiErrorText, fmtYuan } from '@platform/core';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

type Results = Awaited<ReturnType<ReturnType<typeof useApp>['client']['search']>>;

/** SRCH-001/003 全站搜索（V127，101 号 spec）。
 *
 * `search` / `searchSuggest` / `trendingTerms` 三个方法此前**三端零调用**。
 * 接之前先修了服务端两处：联想与热词原样公开任何人敲过的原始搜索串
 * （一次就够——有人搜过「张三 13800001234」，任何人打「张」都能看到它），
 * 以及用户搜索不看隐私设置。所以这里显示的热词，是**至少 3 个不同的人
 * 搜过、且过了内容审核**的词。
 *
 * 查询词放进 URL（`?q=`）：搜索结果要能分享、能后退回来。
 */
export default function Search() {
  const { client } = useApp();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const [suggest, setSuggest] = useState<string[]>([]);
  const [trending, setTrending] = useState<Array<{ term: string; count: number }>>([]);
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);
  const active = params.get('q') ?? '';

  useEffect(() => {
    void client.trendingTerms(8).then(setTrending).catch(() => setTrending([]));
  }, [client]);

  // 结果以 URL 为准：后退、刷新、分享出去的链接都得到同一份结果
  useEffect(() => {
    if (!active) { setResults(null); return; }
    let live = true;
    setBusy(true); setError('');
    client.search(active)
      .then((r) => { if (live) setResults(r); })
      .catch((e) => { if (live) { setError(apiErrorText(e)); setResults(null); } })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [client, active]);

  useEffect(() => {
    const term = q.trim();
    if (!term || term === active) { setSuggest([]); return; }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      void client.searchSuggest(term)
        .then((s) => { if (mine === seq.current) setSuggest(s.filter((x) => x !== term)); })
        .catch(() => { if (mine === seq.current) setSuggest([]); });
    }, 250);
    return () => clearTimeout(t);
  }, [client, q, active]);

  function go(term: string) {
    const t = term.trim();
    if (!t) return;
    setQ(t); setSuggest([]);
    setParams({ q: t });
  }

  const empty = results && !results.tasks.length && !results.users.length
    && !results.contents.length && !results.circles.length;

  return (
    <div className="page">
      <div className="card">
        <form className="row" onSubmit={(e: FormEvent) => { e.preventDefault(); go(q); }}>
          <input className="grow" aria-label="全站搜索" value={q}
                 onChange={(e) => setQ(e.target.value)} placeholder="搜任务、人、内容、圈层…" />
          <button type="submit">搜索</button>
        </form>
        {suggest.length > 0 && (
          <ul aria-label="搜索联想" className="suggest-list">
            {suggest.map((s) => (
              <li key={s}><button className="ghost" onClick={() => go(s)}>{s}</button></li>
            ))}
          </ul>
        )}
        {!active && trending.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <p className="muted">大家在搜</p>
            <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
              {trending.map((t) => (
                <button key={t.term} className="ghost" onClick={() => go(t.term)}>{t.term}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      {busy && <p className="muted" role="status">正在搜…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {empty && <p className="muted">没有找到「{active}」相关的结果，换个说法试试。</p>}

      {results && results.tasks.length > 0 && (
        <div className="card"><h3>任务</h3><ul>
          {results.tasks.map((t) => (
            <li key={t.id}><Link to={`/tasks/${t.id}`}>{t.title}</Link>
              <span className="muted"> · {t.category} · {t.city || '线上'} · {fmtYuan(t.budget_cents)}</span></li>
          ))}
        </ul></div>
      )}
      {results && results.users.length > 0 && (
        <div className="card"><h3>人</h3><ul>
          {results.users.map((u) => (
            <li key={u.id}><Link to={`/people/${u.id}`}>{u.nickname}</Link>
              <span className="muted"> · {u.skills.slice(0, 3).join(' · ') || '未填写技能'} · 信用 {u.credit_score}</span></li>
          ))}
        </ul></div>
      )}
      {results && results.contents.length > 0 && (
        <div className="card"><h3>内容</h3><ul>
          {results.contents.map((c) => (
            <li key={c.id}><strong>{c.title}</strong><p className="muted">{c.body}</p></li>
          ))}
        </ul></div>
      )}
      {results && results.circles.length > 0 && (
        <div className="card"><h3>圈层</h3><ul>
          {results.circles.map((c) => (
            <li key={c.id}><Link to="/circles">{c.name}</Link><span className="muted"> · {c.member_count} 人</span></li>
          ))}
        </ul></div>
      )}
    </div>
  );
}
