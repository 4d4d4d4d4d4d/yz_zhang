import {
  apiErrorText, fmtYuan, formatDateTime,
  type Mission, type MissionEvent, type MissionStep, type MissionSummary,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../store';

/** ORC-066 / AGT-084 AI 编排（131 号 spec）：说一个目标，平台在预算上限内把它拆成任务、发出去、看结果、不达标就整改。
 *
 * 编排会用你的钱发任务，所以每一步都看得见：预算占用、每一步的状态与评审、时间线。
 * 授权后，分发时还会用平台经验工具给每一步生成草稿——只是草稿，挂在步骤上等你采用或丢弃，不会替你发给任何人。
 */
const STATUS: Record<string, string> = {
  planning: '待规划', running: '进行中', succeeded: '已达标', blocked: '卡住了', cancelled: '已取消', failed: '没完成',
};
const STEP: Record<string, string> = { pending: '待分发', dispatched: '已发布', done: '已验收', failed: '没通过', superseded: '已被整改替代' };
const DRAFT: Record<string, string> = { pending: '待你确认', adopted: '已采用', discarded: '已丢弃' };
type Detail = Mission & { steps: MissionStep[]; timeline: MissionEvent[] };

export default function Missions() {
  const { client } = useApp();
  const [params, setParams] = useSearchParams();
  const id = Number(params.get('id')) || null;
  const [list, setList] = useState<Mission[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [summary, setSummary] = useState<MissionSummary | null>(null);
  const [form, setForm] = useState({ goal: '', detail: '', category: '跑腿', budget: '300', iters: 3, acceptance: '', allow_agents: false, allow_tools: true });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setList(await client.myMissions());
      setDetail(id ? await client.getMission(id) : null);
      // AGT-091 复盘（133 号 spec）：取不到不影响详情
      setSummary(id ? await client.missionSummary(id).catch(() => null) : null);
    } catch (e) { setError(apiErrorText(e)); }
  }, [client, id]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  async function create() {
    setError(''); setNotice('');
    try {
      const m = await client.createMission({
        goal: form.goal.trim(), detail: form.detail.trim(), category: form.category.trim() || '跑腿',
        budget_cap_cents: Math.round(Number(form.budget) * 100), max_iterations: form.iters,
        acceptance_criteria: form.acceptance.split('\n').map((x) => x.trim()).filter(Boolean),
        allow_agents: form.allow_agents, allow_tools: form.allow_tools,
      });
      setNotice('已建好：点「推进一轮」开始规划和分发');
      setParams({ id: String(m.id) });
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <div className="page workbench">
      <div className="page-heading">
        <h2>AI 编排</h2>
        <p className="muted">说一个目标，平台在你给的预算上限内把它拆成任务发出去，看结果、不达标就整改。每一步都看得见；钱只在你给的上限内花。</p>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}

      {detail ? (
        <div className="card" aria-label="编排详情">
          <p><Link to="/missions">← 全部编排</Link></p>
          <h3>{detail.goal}</h3>
          <p className="muted">{STATUS[detail.status] ?? detail.status} · 第 {detail.iteration}/{detail.max_iterations} 轮 · 完成 {detail.completion_pct}% · 平均评审 {detail.quality_pct} 分
            {' · '}预算：已付 {fmtYuan(detail.spent_cents)}，占用 {fmtYuan(detail.committed_cents)}，上限 {fmtYuan(detail.budget_cap_cents)}</p>
          {detail.last_error && <p className="error">{detail.last_error}</p>}
          <div className="row">
            <button disabled={['succeeded', 'cancelled', 'failed'].includes(detail.status)}
              onClick={() => void act(async () => { const r = await client.tickMission(detail.id); setNotice(`这一轮：${r.action}`); }, '已推进一轮')}>推进一轮</button>
            <label><input type="checkbox" aria-label="允许用经验工具生成草稿" checked={detail.allow_tools}
              onChange={(e) => void act(() => client.setMissionTools(detail.id, e.target.checked), e.target.checked ? '已授权：之后分发的步骤会用经验工具生成草稿' : '已收回授权')} /> 允许用平台经验工具生成草稿（只出草稿，等你确认）</label>
            <button className="ghost" disabled={['succeeded', 'cancelled', 'failed'].includes(detail.status)} onClick={() => {
              if (window.confirm('取消后，还没人接的任务会关闭，已经在做的照常结算。确定取消？')) void act(() => client.cancelMission(detail.id), '已取消');
            }}>取消编排</button>
          </div>
          {summary && Array.isArray(summary.highlights) && (
            <div className="card" aria-label="复盘">
              <h4>复盘</h4>
              <p className="muted">{summary.rounds}/{summary.max_rounds} 轮 · 完成 {summary.steps_done}/{summary.steps_total} 步 · 整改 {summary.remedies} 次
                {summary.avg_review_score !== null ? ` · 平均评审 ${summary.avg_review_score} 分` : ''} · 实付 {fmtYuan(summary.spent_cents)} / 上限 {fmtYuan(summary.cap_cents)}
                {summary.duration_days !== null ? ` · 用时 ${summary.duration_days} 天` : ''}</p>
              {summary.highlights.length > 0 && <ul>{summary.highlights.map((h) => <li key={h}>{h}</li>)}</ul>}
              <p>下一步：{summary.next}</p>
            </div>
          )}
          <h4>步骤</h4>
          {detail.steps.length === 0 && <p className="muted">还没有规划：点「推进一轮」。</p>}
          <ul className="list">
            {detail.steps.map((s) => (
              <li key={s.id} aria-label={`步骤：${s.title}`}>
                <strong>{s.title}</strong> <span className="muted">· {STEP[s.status] ?? s.status}{s.attempt > 1 ? `（第 ${s.attempt} 次）` : ''}
                  {s.budget_cents ? ` · ${fmtYuan(s.budget_cents)}` : ''}{s.review_verdict ? ` · 评审 ${s.review_score} 分` : ''}</span>
                {s.task_id && <> <Link to={`/tasks/${s.task_id}`}>任务 #{s.task_id}</Link></>}
                {s.observation && <div className="muted">{s.observation}</div>}
                {s.tool_drafts.map((d) => (
                  <div key={d.invocation_id} className="card" aria-label="经验工具草稿">
                    <p className="muted">{d.label} · {DRAFT[d.status]}</p>
                    <pre style={{ whiteSpace: 'pre-wrap' }}>{d.text}</pre>
                    {d.status === 'pending' && (
                      <div className="row">
                        <button onClick={() => void act(() => client.adoptMissionDraft(detail.id, s.id, d.invocation_id), '已采用（只是标记，没有发给任何人）')}>采用</button>
                        <button className="ghost" onClick={() => void act(() => client.discardMissionDraft(detail.id, s.id, d.invocation_id), '已丢弃')}>丢弃</button>
                      </div>
                    )}
                  </div>
                ))}
              </li>
            ))}
          </ul>
          <h4>时间线</h4>
          <ol>{detail.timeline.map((e, n) => <li key={n}><span className="muted">{formatDateTime(e.at)} 第 {e.iteration} 轮</span> {e.summary}</li>)}</ol>
        </div>
      ) : (
        <>
          <div className="card" aria-label="我的编排">
            <h4>我的编排</h4>
            {list.length === 0 && <p className="muted">还没有。在下面说一个目标试试。</p>}
            <ul className="list">
              {list.map((m) => (
                <li key={m.id}><Link to={`/missions?id=${m.id}`}>{m.goal}</Link>
                  <span className="muted"> · {STATUS[m.status] ?? m.status} · 完成 {m.completion_pct}% · 上限 {fmtYuan(m.budget_cap_cents)}{m.allow_tools ? ' · 用经验工具' : ''}</span></li>
              ))}
            </ul>
          </div>
          <div className="card form" aria-label="新的编排">
            <h4>新的编排</h4>
            <input aria-label="目标" placeholder="目标，例如：周六搬家（打包、搬运、保洁）" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} />
            <textarea aria-label="说明" rows={3} placeholder="说明（可不填）" value={form.detail} onChange={(e) => setForm({ ...form, detail: e.target.value })} />
            <div className="row">
              <input aria-label="类目" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
              <label>预算上限（元） <input aria-label="预算上限" type="number" min={1} value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} /></label>
              <label>最多几轮 <select aria-label="最多几轮" value={form.iters} onChange={(e) => setForm({ ...form, iters: Number(e.target.value) })}>
                {[1, 2, 3, 5, 8].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
            </div>
            <textarea aria-label="验收要点" rows={2} placeholder="验收要点，一行一条（可不填）" value={form.acceptance} onChange={(e) => setForm({ ...form, acceptance: e.target.value })} />
            <label><input type="checkbox" aria-label="允许交给平台 AI 助理" checked={form.allow_agents} onChange={(e) => setForm({ ...form, allow_agents: e.target.checked })} /> 允许把步骤交给平台 AI 助理去做</label>
            <label><input type="checkbox" aria-label="新编排用经验工具" checked={form.allow_tools} onChange={(e) => setForm({ ...form, allow_tools: e.target.checked })} /> 允许用平台经验工具生成草稿（只出草稿，等你确认）</label>
            <button disabled={form.goal.trim().length < 2 || !(Number(form.budget) > 0)} onClick={() => void create()}>建好，先不花钱</button>
          </div>
        </>
      )}
    </div>
  );
}
