// KB-080~089 / AGT-080~083 经验变成能被调用的单元（109 号 spec）。
//
// 用户 2026-10-10：「攒经验完全可以作为检索数据库或者 skilltool 工具给后续复用」。
// 这里是两端里网页的那一半：子类详情下面列出从它蒸馏出来的单元（带排除条件与验证状态），
// 任务详情里给双方一个「用经验工具起草」的入口——产出**只是草稿**，可以丢掉。
import {
  apiErrorText, fmtYuan, type ExperienceToolDraft, type ReusableUnit, type ReusableUnitDetail,
  type ReusableUnitValidation, type Task,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { useApp } from './store';

const VALIDATION_LABEL: Record<ReusableUnitValidation['status'], string> = {
  unvalidated: '还没被验证过',
  validated: '用过、多数做成了',
  needs_review: '复核中',
};

function Validation({ v }: { v: ReusableUnitValidation }) {
  return (
    <span className="muted">
      {VALIDATION_LABEL[v.status] ?? v.status}
      {v.uses > 0 ? ` · 用过 ${v.uses} 次：做成 ${v.closed}、返工 ${v.reworked}、失败 ${v.failed}` : ''}
    </span>
  );
}

/** 单元详情里给人看的那部分内容：随类型不同。 */
function UnitContent({ unit }: { unit: ReusableUnitDetail }) {
  const c = unit.content ?? {};
  const steps = Array.isArray(c.steps) ? (c.steps as Array<{ title?: string; deliverable?: string }>) : [];
  const items = Array.isArray(c.items) ? (c.items as string[]) : Array.isArray(c.checklist) ? (c.checklist as string[]) : [];
  if (unit.kind === 'price_hint') {
    return (
      <p>
        中位 {typeof c.p50_cents === 'number' ? fmtYuan(c.p50_cents) : '—'}
        {typeof c.p90_cents === 'number' ? ` · 九成在 ${fmtYuan(c.p90_cents)} 以内` : ''}
        <span className="muted">（{unit.sample_count} 个样本）</span>
      </p>
    );
  }
  if (steps.length > 0) {
    return <ol>{steps.map((s, i) => <li key={i}>{s.title}{s.deliverable ? <em className="muted"> · 交付：{s.deliverable}</em> : null}</li>)}</ol>;
  }
  if (items.length > 0) return <ul>{items.map((t) => <li key={t}>☐ {t}</li>)}</ul>;
  return null;
}

/** 子类详情下面：从它蒸馏出来、可以直接拿去用的单元。 */
export function ClusterUnits({ clusterId }: { clusterId: number }) {
  const { client } = useApp();
  const [rows, setRows] = useState<ReusableUnit[]>([]);
  const [open, setOpen] = useState<ReusableUnitDetail | null>(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    client.knowledgeUnits({ cluster_id: clusterId })
      .then((r) => setRows(Array.isArray(r) ? r : []))
      .catch(() => setRows([]));
  }, [client, clusterId]);

  if (rows.length === 0) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <p><strong>可以直接拿去用的经验</strong></p>
      {err && <p className="error">{err}</p>}
      <ul className="list">
        {rows.map((u) => (
          <li key={u.id} className="task-item" data-unit={u.id}>
            <div>
              <button className="ghost" onClick={async () => {
                setErr('');
                try { setOpen(open?.id === u.id ? null : await client.knowledgeUnit(u.id)); } catch (e) { setErr(apiErrorText(e)); }
              }}>{u.kind_label} · {u.title}</button>
              <p><Validation v={u.validation} /></p>
              {/* 排除条件和单元一起出现，不藏在详情里：它就是这个单元最容易被用错的地方 */}
              <p className="muted">不适用：{u.applicability.exclusions.join('；')}</p>
            </div>
          </li>
        ))}
      </ul>
      {open && (
        <div className="card" style={{ marginTop: 6 }}>
          <h4>{open.title} <span className="muted">v{open.version}</span></h4>
          <UnitContent unit={open} />
          <p className="muted">
            来自 {open.sample_count} 个双方都同意复用的样本
            {open.contributors.length > 0 ? ` · 贡献者：${open.contributors.map((c) => c.nickname).join('、')}` : ''}
          </p>
        </div>
      )}
    </div>
  );
}

/** AGT-080~083 任务详情里的经验工具：只出草稿，带「未经人工确认」标签，可丢弃。 */
export function ExperienceTools({ task }: { task: Task }) {
  const { client } = useApp();
  const [tools, setTools] = useState<ReusableUnit[]>([]);
  const [draft, setDraft] = useState<ExperienceToolDraft | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    client.knowledgeUnits({ kind: 'skill_tool', category: task.category })
      .then((r) => setTools(Array.isArray(r) ? r : []))
      .catch(() => setTools([]));
  }, [client, task.category]);

  if (tools.length === 0) return null;
  return (
    <div className="card">
      <h3>用平台经验起草</h3>
      <p className="muted">这些工具来自同类任务里双方都同意复用的经验。它们只起草，不花钱、不签约、不替你发消息。</p>
      {err && <p className="error" role="alert">{err}</p>}
      {!draft && (
        <div className="row">
          {tools.map((t) => (
            <button key={t.id} disabled={busy} onClick={async () => {
              setErr('');
              setBusy(true);
              try { setDraft(await client.invokeExperienceTool(t.id, task.id)); } catch (e) { setErr(apiErrorText(e)); }
              setBusy(false);
            }}>{t.title}</button>
          ))}
        </div>
      )}
      {draft && (
        <div style={{ marginTop: 8 }}>
          <p className="badge warn">{draft.label}</p>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{draft.text}</pre>
          <p className="muted">来自 {draft.contributors} 位贡献者的经验。用之前逐条核对；不适用的情形：{draft.exclusions.join('；')}</p>
          <div className="row">
            <button className="ghost" onClick={() => void navigator.clipboard?.writeText(draft.text)}>复制草稿</button>
            <button className="ghost" onClick={async () => {
              try { await client.discardToolDraft(draft.invocation_id); setDraft(null); } catch (e) { setErr(apiErrorText(e)); }
            }}>丢弃草稿</button>
          </div>
        </div>
      )}
    </div>
  );
}
