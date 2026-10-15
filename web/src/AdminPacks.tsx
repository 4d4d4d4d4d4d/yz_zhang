import {
  apiErrorText, formatDateTime,
  type PackValidation, type RadarSignal, type ScenarioPackAdminListRow,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** PACK-102/103/107 场景包运营（123 号 spec）：定义 → 校验 → 提交 → 另一位管理员上线 → 指标 → 复核或下线；场景雷达。 */
const STATUS: Record<string, string> = {
  draft: '草稿', review: '待审核', published: '已上线', superseded: '旧版本', retired: '已下线',
};
// SCN-108（153 号 spec）起多两路：法律问答答不上的主题、客服没接住的工单主题
const SOURCE: Record<string, string> = { search_gap: '搜了没有', stuck_demand: '有需求没人接', pack_gap: '服务包要复核', legal_gap: '法律问答答不上', support_gap: '客服没接住' };

export function PacksAdmin() {
  const { client, me } = useApp();
  const [rows, setRows] = useState<ScenarioPackAdminListRow[]>([]);
  const [radar, setRadar] = useState<RadarSignal[]>([]);
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
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
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
      <table>
        <thead><tr><th>来源</th><th>信号</th><th>依据</th></tr></thead>
        <tbody>
          {radar.length === 0 && <tr><td colSpan={3} className="muted">暂时没有信号</td></tr>}
          {radar.map((x) => (
            <tr key={`${x.source}:${x.key}`}><td>{SOURCE[x.source]}</td><td>{x.title}</td><td className="muted">{x.evidence}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
