import {
  apiErrorText, formatDateTime,
  type InfluenceLatestSnapshot, type InfluenceLeaderboard, type InfluenceMine, type InfluenceProof, type InfluenceVouchRow,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../store';

/** INF-100 影响力与专家等级（127 号 spec）。
 *
 * 影响力只能靠在平台上做成事挣，不能转让、不能买；按半衰期衰减；纠纷败诉会被罚没。
 * 熟手以上可以拿自己的影响力为别人作保。每天的快照做成 Merkle 树，根写进存证链，每个人都能拿到自己那一条的证明。
 */
const KIND: Record<string, string> = {
  earn_task: '完成一单', earn_publish: '发的单做成了', earn_vouch: '担保的人做成了',
  slash_dispute: '纠纷败诉', slash_vouch: '担保罚没', restore: '申诉恢复',
};
const VOUCH_STATUS: Record<InfluenceVouchRow['status'], string> = {
  active: '担保中', released: '已释放', slashed: '已罚没', withdrawn: '已撤回',
};

export default function Influence() {
  const { client } = useApp();
  const [mine, setMine] = useState<InfluenceMine | null>(null);
  const [proof, setProof] = useState<InfluenceProof | null>(null);
  const [latest, setLatest] = useState<InfluenceLatestSnapshot | null>(null);
  const [cat, setCat] = useState('');
  const [board, setBoard] = useState<InfluenceLeaderboard | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const m = await client.myInfluence();
      setMine(m);
      setCat((c) => c || m.categories[0]?.category || '');
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { client.latestInfluenceSnapshot().then(setLatest).catch(() => setLatest(null)); }, [client]);
  useEffect(() => {
    if (!cat) { setBoard(null); return; }
    client.influenceLeaderboard(cat).then(setBoard).catch(() => setBoard(null));
  }, [client, cat]);

  async function withdraw(v: InfluenceVouchRow) {
    setError(''); setNotice('');
    try { await client.withdrawVouch(v.id); setNotice(`已撤回对 ${v.subject_nickname} 的担保`); await load(); }
    catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>影响力</h2>
        <p className="muted">{mine?.rules ?? '只能靠在平台上做成事挣；不能转让。'}</p>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}

      <div className="card" aria-label="我的等级">
        <h4>我在各类目的等级</h4>
        {mine && mine.categories.length === 0 && <p className="muted">还没有影响力：在平台上完成第一单就有了。</p>}
        <ul className="list">
          {mine?.categories.map((c) => (
            <li key={c.category}>
              <strong>{c.category} · {c.tier_name}</strong>
              <span className="muted"> · 影响力 {c.points} · 完成 {c.completed} 单{c.rating_avg !== null ? ` · 平均 ${c.rating_avg} 星` : ''}
                {c.locked > 0 ? ` · 担保占用 ${c.locked}` : ''}{c.tier !== 'newcomer' ? ` · 还能担保 ${c.available}` : ''}</span>
              {c.gaps.map((g) => <div key={g} className="muted">{g}</div>)}
            </li>
          ))}
        </ul>
      </div>

      <div className="card" aria-label="担保">
        <h4>担保</h4>
        <p className="muted">在别人的个人空间里可以为他作保（熟手以上）。为某一单作保的，对方开工后要等这一单结束才释放。</p>
        {mine && mine.vouches_given.length === 0 && mine.vouches_received.length === 0 && <p className="muted">还没有担保。</p>}
        <ul className="list">
          {mine?.vouches_given.map((v) => (
            <li key={`g${v.id}`}>我为 <Link to={`/people/${v.subject_id}`}>{v.subject_nickname}</Link> 担保 {v.stake} 点「{v.category}」
              {v.task_id ? <> · <Link to={`/tasks/${v.task_id}`}>任务 #{v.task_id}</Link></> : ' · 整个类目'} · {VOUCH_STATUS[v.status]}
              {v.status === 'active' && <> <button className="text-link" onClick={() => void withdraw(v)}>撤回</button></>}</li>
          ))}
          {mine?.vouches_received.map((v) => (
            <li key={`r${v.id}`}><Link to={`/people/${v.voucher_id}`}>{v.voucher_nickname}</Link> 为我担保 {v.stake} 点「{v.category}」 · {VOUCH_STATUS[v.status]}
              {v.note && <span className="muted"> · {v.note}</span>}</li>
          ))}
        </ul>
      </div>

      <div className="card" aria-label="排行">
        <h4>类目里的熟手与专家</h4>
        <div className="row">
          <input aria-label="类目" placeholder="类目，例如：保洁" value={cat} onChange={(e) => setCat(e.target.value.trim())} />
        </div>
        {board && (board.items.length === 0 ? <p className="muted">「{board.category}」还没有熟手以上的人（只列资料公开的）。</p> : (
          <ol>{board.items.map((r) => <li key={r.user_id}><Link to={`/people/${r.user_id}`}>{r.nickname}</Link> · {r.tier_name} · 影响力 {r.points} · 完成 {r.completed} 单</li>)}</ol>
        ))}
      </div>

      <div className="card" aria-label="明细">
        <h4>最近的变动</h4>
        {mine && mine.events.length === 0 && <p className="muted">还没有变动。</p>}
        <ul className="list">
          {mine?.events.map((e) => (
            <li key={e.id}><strong>{e.points > 0 ? '+' : ''}{e.points}</strong> {KIND[e.kind] ?? e.kind} · {e.category}
              <span className="muted"> · {e.reason} · {formatDateTime(e.created_at)}</span></li>
          ))}
        </ul>
      </div>

      <div className="card" aria-label="存证">
        <h4>快照与证明</h4>
        <p className="muted">每天给所有人的影响力做一次快照：做成 Merkle 树，树根写进平台的存证哈希链。拿着树根和你这一条的路径，任何人都能自己验算。</p>
        {latest?.snapshot && !proof && <p className="muted">最近一次快照：{formatDateTime(latest.snapshot.taken_at)} · {latest.snapshot.leaves} 条 · 存证序号 {latest.snapshot.anchor_seq ?? '—'}</p>}
        <button className="ghost" onClick={() => void client.myInfluenceProof().then(setProof).catch((e) => setError(apiErrorText(e)))}>查看我的证明</button>
        {proof && (proof.snapshot === null ? <p className="muted">还没有做过快照（每天一次）。</p> : (
          <div>
            <p>快照 #{proof.snapshot.id} · {formatDateTime(proof.snapshot.taken_at)} · {proof.snapshot.leaves} 条 · 存证序号 {proof.snapshot.anchor_seq ?? '—'}</p>
            <p className="muted" style={{ wordBreak: 'break-all' }}>树根 {proof.snapshot.merkle_root}</p>
            {proof.items.length === 0 ? <p className="muted">这次快照里还没有你。</p> : (
              <ul>{proof.items.map((i) => <li key={i.category}>{i.category}：{i.points} · {i.verified ? '验证通过' : '验证不通过'}（路径 {i.path.length} 层）</li>)}</ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
