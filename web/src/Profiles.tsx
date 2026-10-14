import {
  apiErrorText, fmtYuan,
  type CapabilityProfile, type TaskDraftInput, type TaskProfile, type TaskProfileView,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { useApp } from './store';

/** PROF-100 任务画像与能力画像（126 号 spec）的两端展示件。 */
const POSITION: Record<string, string> = {
  below_min: '低于近期同类最低成交价', below_median: '低于同类成交中位', around_median: '与同类成交中位相当',
  above_median: '高于同类成交中位', unknown: '同类成交数据不足',
};

/** 发布页：边写边提示还缺什么。输入停下半秒再算，不每个字都请求。 */
export function DraftHints({ draft }: { draft: TaskDraftInput }) {
  const { client } = useApp();
  const [p, setP] = useState<TaskProfile | null>(null);
  const key = JSON.stringify(draft);
  useEffect(() => {
    const timer = setTimeout(() => {
      client.taskDraftProfile(JSON.parse(key) as TaskDraftInput).then((x) => setP(Array.isArray(x?.checks) ? x : null)).catch(() => setP(null));
    }, 500);
    return () => clearTimeout(timer);
  }, [client, key]);
  if (!p) return null;
  const missing = p.checks.filter((c) => !c.ok);
  return (
    <div className="card" aria-label="说明完整度">
      <p><strong>说明完整度 {Math.round(p.completeness * 100)}%</strong>
        {p.price.sample_size > 0 && <span className="muted"> · 预算{POSITION[p.price.position]}（中位 {fmtYuan(p.price.p50_cents ?? 0)}）</span>}</p>
      {missing.length > 0 && <ul>{missing.map((c) => <li key={c.key}>{c.hint}</li>)}</ul>}
      {p.inferred_skills.length > 0 && <p className="muted">从说明里认出的技能：{p.inferred_skills.join('、')}（会用来推荐合适的人）</p>}
      {p.risks.length > 0 && <ul className="muted">{p.risks.map((r) => <li key={r.kind}>⚠ {r.text}</li>)}</ul>}
    </div>
  );
}

/** 任务详情：报名前看一眼这单的画像（风险、技能、价格位置）。 */
export function TaskProfilePanel({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [p, setP] = useState<TaskProfileView | null>(null);
  // 画像是附加信息：取不到（或老服务端没有这个接口）就不显示，不影响任务详情本身
  useEffect(() => { client.taskProfile(taskId).then((x) => setP(Array.isArray(x?.risks) ? x : null)).catch(() => setP(null)); }, [client, taskId]);
  if (!p) return null;
  const skills = [...p.declared_skills, ...p.inferred_skills];
  return (
    <div className="card" aria-label="任务画像">
      <h4>这单的画像</h4>
      <p className="muted">{p.mode === 'remote' ? '线上' : '线下'} · {p.category || '未分类'}{skills.length ? ` · 技能：${skills.join('、')}` : ''}
        {p.price.sample_size > 0 ? ` · 预算${POSITION[p.price.position]}` : ''} · 说明完整度 {Math.round(p.completeness * 100)}%</p>
      {p.risks.length > 0 && <ul>{p.risks.map((r) => <li key={r.kind}>⚠ {r.text}</li>)}</ul>}
    </div>
  );
}

/** 能力画像：被证明过的能力。自述与佐证分开写——画像不是简历。 */
export function CapabilityCard({ userId }: { userId?: number }) {
  const { client } = useApp();
  const [c, setC] = useState<CapabilityProfile | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    // 能力画像是附加信息：任何失败（包括同步抛错）都只是不显示，不能把整个空间页带崩
    Promise.resolve().then(() => (userId === undefined ? client.myCapability() : client.userCapability(userId)))
      .then((x) => setC(Array.isArray(x?.categories) ? x : null)).catch((e) => setError(apiErrorText(e)));
  }, [client, userId]);
  if (!c) return error && userId === undefined ? <p className="error">{error}</p> : null;
  const pct = (x: number | null) => (x === null ? '样本不足' : `${Math.round(x * 100)}%`);
  return (
    <section className="card" aria-label="能力画像">
      <h4>能力画像</h4>
      {c.tasks_completed === 0 ? <p className="muted">还没有在平台上完成过合作。</p> : (
        <ul>{c.categories.map((x) => <li key={x.category}>{x.category}：完成 {x.completed} 单{x.rating_avg !== null ? `，平均 ${x.rating_avg} 星` : ''}</li>)}</ul>
      )}
      {c.skills.length > 0 && <p>技能：{c.skills.map((s) => (s.evidenced ? `${s.skill}（有成交佐证）` : `${s.skill}（自述）`)).join('、')}</p>}
      {c.certifications.length > 0 && <p>已核验资质：{c.certifications.join('、')}</p>}
      <p className="muted">准时交付 {pct(c.on_time_rate)} · 返工 {pct(c.rework_rate)}
        {c.reply_hours_median !== null ? ` · 回复邀约中位 ${c.reply_hours_median} 小时` : ''}
        {c.disputes !== null ? ` · 纠纷 ${c.disputes} 次（只有你看得到）` : ''}</p>
      <p className="muted">{c.note}</p>
    </section>
  );
}
