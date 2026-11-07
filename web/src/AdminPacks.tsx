import {
  apiErrorText, formatDateTime,
  type PackSynonymList, type PackValidation, type RadarSignal, type ScenarioPackAdminListRow,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** PACK-102/103/107 场景包运营（123 号 spec）：定义 → 校验 → 提交 → 另一位管理员上线 → 指标 → 复核或下线；场景雷达。 */
const STATUS: Record<string, string> = {
  draft: '草稿', review: '待审核', published: '已上线', superseded: '旧版本', retired: '已下线',
};
// SCN-108（153 号 spec）起多两路：法律问答答不上的主题、客服没接住的工单主题
const SOURCE: Record<string, string> = { search_gap: '搜了没有', stuck_demand: '有需求没人接', pack_gap: '服务包要复核', legal_gap: '法律问答答不上', support_gap: '客服没接住',
  errand_gap: '发单拦截可能误拦' };

export function PacksAdmin() {
  const { client, me } = useApp();
  const [rows, setRows] = useState<ScenarioPackAdminListRow[]>([]);
  const [radar, setRadar] = useState<RadarSignal[]>([]);
  const [target, setTarget] = useState('');
  const [text, setText] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [check, setCheck] = useState<PackValidation | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setRows(await client.adminPacks()); setRadar(await client.adminPackRadar()); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  function parsed(): Record<string, unknown> | null {
    try { return JSON.parse(text) as Record<string, unknown>; } catch { setCheck({ ok: false, problems: ['不是合法的 JSON'], score: null }); return null; }
  }
  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); if (done) setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const keys = [...new Set(rows.map((r) => r.key))];
  async function validate() {
    const d = parsed();
    if (d) { try { setCheck(await client.adminValidatePack(d)); } catch (e) { setError(apiErrorText(e)); } }
  }
  async function save() {
    const d = parsed();
    if (!d) return;
    await act(() => (editing ? client.adminUpdatePack(editing, d) : client.adminCreatePack(d)), editing ? '草稿已更新' : '已存为草稿');
    setEditing(null);
  }

  return (
    <div className="card" aria-label="服务包运营">
      <div className="row">
        <h3 className="grow">服务包（场景包）</h3>
        <button className="ghost" onClick={() => void act(async () => {
          const r = await client.adminImportPackSeeds();
          setNotice(`导入草稿 ${r.created.length} 个，跳过 ${r.skipped.length} 个${r.invalid.length ? `，${r.invalid.length} 个不合格` : ''}`);
        }, '')}>导入仓库里的种子包</button>
      </div>
      <p className="muted">上线要另一位管理员审核（写它的人不能自己批）；已上线的版本不可变，改动建新版本；下线要写理由。</p>
      <table>
        <thead><tr><th>包</th><th>版本</th><th>状态</th><th>分</th><th>在用 / 答不上 / 有用</th><th></th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={6} className="muted">还没有服务包</td></tr>}
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.title}<div className="muted">{r.key}</div></td>
              <td>v{r.version}</td>
              <td>{STATUS[r.status]}{r.retired_reason && <div className="muted">{r.retired_reason}</div>}
                {r.published_at && <div className="muted">{formatDateTime(r.published_at)}</div>}</td>
              <td>{r.score}</td>
              <td>{r.metrics.active} / {r.metrics.unanswered_rate === null ? '—' : `${Math.round(r.metrics.unanswered_rate * 100)}%`} / {r.metrics.helpful_rate === null ? '—' : `${Math.round(r.metrics.helpful_rate * 100)}%`}</td>
              <td className="row">
                {r.status === 'draft' && <>
                  <button className="ghost" onClick={() => { setEditing(r.id); setText(JSON.stringify(r.definition, null, 2)); setCheck(null); }}>编辑</button>
                  <button onClick={() => void act(() => client.adminSubmitPack(r.id), '已提交审核')}>提交审核</button>
                </>}
                {r.status === 'review' && <>
                  <button disabled={r.created_by === me?.id} title={r.created_by === me?.id ? '写它的人不能自己批' : ''}
                    onClick={() => void act(() => client.adminApprovePack(r.id), '已上线')}>上线</button>
                  <button className="ghost" onClick={() => void act(() => client.adminRejectPack(r.id), '已退回草稿')}>退回</button>
                </>}
                {(r.status === 'published' || r.status === 'draft' || r.status === 'review') && (
                  <button className="danger" onClick={() => {
                    const reason = window.prompt('下线理由（会留在记录里）');
                    if (reason && reason.trim().length >= 2) void act(() => client.adminRetirePack(r.id, reason.trim()), '已下线');
                  }}>下线</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>{editing ? `编辑草稿 #${editing}` : '新建服务包（JSON 定义）'}</h4>
      <textarea aria-label="服务包定义" rows={10} value={text} onChange={(e) => setText(e.target.value)}
        placeholder='{"key": "...", "title": "...", "segment": "opc", "pains": [...], "score": {...}, "assistants": [...]}' />
      <div className="row">
        <button className="ghost" disabled={!text.trim()} onClick={() => void validate()}>校验</button>
        <button disabled={!text.trim()} onClick={() => void save()}>{editing ? '保存草稿' : '存为草稿'}</button>
        {editing && <button className="ghost" onClick={() => { setEditing(null); setText(''); }}>取消编辑</button>}
      </div>
      {check && (check.ok
        ? <p role="status">校验通过，打分 {check.score}</p>
        : <ul className="error" aria-label="校验问题">{check.problems.map((p) => <li key={p}>{p}</li>)}</ul>)}
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}

      <h4>场景雷达</h4>
      <p className="muted">只看聚合信号：每条至少 3 个不同的人；不读任何人的笔记、私聊或提问原文。</p>
      {/* SCN-112（162 号 spec）：一键起草知识条目进场景包草稿；回答与出处留「【待填写】」，填完才能提交审核 */}
      <label className="row">起草进哪个服务包
        <select aria-label="起草进哪个服务包" value={target || keys[0] || ''} onChange={(e) => setTarget(e.target.value)}>
          {keys.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
      </label>
      <table>
        <thead><tr><th>来源</th><th>信号</th><th>依据</th><th></th></tr></thead>
        <tbody>
          {radar.length === 0 && <tr><td colSpan={4} className="muted">暂时没有信号</td></tr>}
          {radar.map((x) => (
            <tr key={`${x.source}:${x.key}`}><td>{SOURCE[x.source]}</td><td>{x.title}</td><td className="muted">{x.evidence}</td>
              <td>{keys.length > 0 && (
                <button className="ghost" onClick={() => void act(async () => {
                  const r = await client.adminDraftKnowledgeFromRadar({ source: x.source, key: x.key, pack_key: target || keys[0] });
                  setEditing(r.pack.id); setText(JSON.stringify(r.pack.definition, null, 2)); setCheck(null);
                  setNotice(`已起草进「${r.pack.key}」v${r.pack.version} 的草稿（${r.knowledge_key}）：把「【待填写】」的回答与出处写完再提交审核`);
                }, '')}>起草知识条目</button>
              )}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <PackSynonyms />
    </div>
  );
}

/** PACK-092c（436 号 spec）近义说法：一位管理员提出给一组加写法，另一位确认才生效；随时可以收回。仓库里写死的收不回。 */
export function PackSynonyms() {
  const { client, me } = useApp();
  const [view, setView] = useState<PackSynonymList | null>(null);
  const [name, setName] = useState('');
  const [words, setWords] = useState('');
  const [includes, setIncludes] = useState('');
  const [reason, setReason] = useState('');
  const [probe, setProbe] = useState('');
  const [probed, setProbed] = useState<string[] | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const v = await client.packSynonyms().catch(() => null);
    setView(v && Array.isArray(v.items) && Array.isArray(v.effective) ? v : null);
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const split = (s: string) => s.split(/[\s,，、]+/).map((x) => x.trim()).filter(Boolean);
  if (!view) return null;
  const label = { pending: '待另一位确认', active: '已生效', revoked: '已收回' } as const;
  return (
    <div aria-label="近义说法" style={{ marginTop: 12 }}>
      <h4>近义说法（助手检索时一起找）</h4>
      <p className="muted">问「天气不好还走吗」也能找到写着「下雨」的知识。配错会让助手引用不相干的内容：一位提出、另一位确认才生效；只能加写法，仓库里写死的收不回。</p>
      <ul aria-label="生效的近义表">
        {view.effective.map((g) => (
          <li key={g.name}><b>{g.name}</b>：{g.words.join('、')}{g.includes.length > 0 && <span className="muted">（还包含 {g.includes.join('、')}）</span>}</li>
        ))}
      </ul>
      <ul aria-label="后台提出的近义说法">
        {view.items.map((r) => (
          <li key={r.id}>{r.name} + {r.words.join('、')}{r.includes.length > 0 && `；包含 ${r.includes.join('、')}`} <span className="muted">（{r.reason}）{label[r.status] ?? r.status}</span>
            {r.status === 'pending' && me?.id !== r.proposed_by && (
              <button className="text-link" onClick={() => void act(() => client.approvePackSynonym(r.id))}>确认</button>
            )}
            {r.status !== 'revoked' && <button className="text-link" onClick={() => void act(() => client.revokePackSynonym(r.id))}>收回</button>}
          </li>
        ))}
      </ul>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <input aria-label="组名" placeholder="组名（已有的组就并进去，如 大风）" value={name} onChange={(e) => setName(e.target.value)} />
        <input aria-label="要加的写法" placeholder="要加的写法，用逗号隔开（如 风力）" value={words} onChange={(e) => setWords(e.target.value)} />
        <input aria-label="包含的组" placeholder="单向包含的组（可不填）" value={includes} onChange={(e) => setIncludes(e.target.value)} />
        <input aria-label="理由" placeholder="为什么是一回事" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button disabled={!name.trim() || (!split(words).length && !split(includes).length) || reason.trim().length < 4}
          onClick={() => void act(async () => {
            await client.proposePackSynonym(name.trim(), split(words), reason.trim(), split(includes));
            setName(''); setWords(''); setIncludes(''); setReason('');
          })}>提出</button>
      </div>
      <div className="row" style={{ gap: 6 }}>
        <input aria-label="试一句" placeholder="试一句问话" value={probe} onChange={(e) => setProbe(e.target.value)} />
        <button className="ghost" disabled={!probe.trim()} onClick={() => void act(async () => {
          const r = await client.expandPackSynonyms(probe.trim());
          setProbed(Array.isArray(r.words) ? r.words : []);
        })}>试</button>
        {probed && <span role="status">{probed.length ? `会一起找：${probed.join('、')}` : '这句不会多带上别的写法'}</span>}
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
