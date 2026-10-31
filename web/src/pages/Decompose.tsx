// AI-DEC-040~048 逐层拆解（106 号 spec，设计见 96 号）。
//
// 用户 2026-10-10：「任务拆解借鉴 todolist 生成过程，生成树类脉络够细够具体的任务，
// 这样有些 AI 可以闭环，有些需要求助其他专家」。这一页是那棵树：
// 一层一层往下长、每层都能改；每个叶子说清谁能做、依据是什么；
// 「判不了」的步骤不让确认，而是给出能点的去处。
import {
  hasLists, MALFORMED_TEXT,
  LEAF_CRITERION_LABEL, apiErrorText, childrenOf, decompositionSourceLabel, executorLabel,
  fmtYuan, isOpenEnd, type Decomposition, type DecompositionNode, type DecompositionNodePatch,
  type Task,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useApp } from '../store';

export default function Decompose() {
  const { client } = useApp();
  const nav = useNavigate();
  const taskId = Number(useParams().id);
  const [task, setTask] = useState<Task | null>(null);
  const [dec, setDec] = useState<Decomposition | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [certCategories, setCertCategories] = useState<Array<{ name: string; required_cert: string }>>([]);

  // APP-093：拆解方案不像样（{}、没有 nodes）时说明原因，不把整页带崩
  const wellFormed = useCallback((d: Decomposition): Decomposition | null => {
    if (hasLists(d, 'nodes')) return d;
    setError(MALFORMED_TEXT);
    return null;
  }, []);

  const load = useCallback(async () => {
    setError('');
    const t = await client.getTask(taskId);
    setTask(t);
    try {
      setDec(wellFormed(await client.currentDecomposition(taskId)));
    } catch (e) {
      const code = (e as { code?: string }).code;
      if (code !== 'no_decomposition_in_progress') throw e;
      // 还没拆过：总任务还是草稿、也还没有子任务，就开始拆；已经确认过的回任务页
      const tree = await client.taskTree(taskId).catch(() => null);
      if (t.status === 'draft' && !(tree && tree.children.length)) {
        setDec(wellFormed(await client.propose(taskId)));
      } else {
        setDec(null);
      }
    }
  }, [client, taskId, wellFormed]);

  useEffect(() => {
    void load().catch((e) => setError(apiErrorText(e)));
    void client.categories()
      .then((rows) => setCertCategories(rows.filter((c) => c.required_cert)))
      .catch(() => {});
  }, [load, client]);

  async function run(fn: () => Promise<Decomposition>, okNote = '') {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const next = wellFormed(await fn());
      if (!next) return;
      setDec(next);
      if (okNote) setNotice(okNote);
    } catch (e) {
      setError(apiErrorText(e));
      // 别的窗口改过（decomposition_changed）：拿最新的那份，让用户在它上面再改
      if ((e as { code?: string }).code === 'decomposition_changed') {
        void client.currentDecomposition(taskId).then(setDec).catch(() => {});
      }
    } finally {
      setBusy(false);
    }
  }

  if (!task) return <div className="page">{error ? <p className="error">{error}</p> : <p className="muted">加载中…</p>}</div>;
  if (!dec) {
    return (
      <div className="page">
        <div className="card">
          <h3>{task.title}</h3>
          <p className="muted">这个任务没有进行中的拆解（已经确认过，或者它不是草稿了）。</p>
          <Link to={`/tasks/${taskId}`}>回到任务</Link>
        </div>
      </div>
    );
  }

  const edit = (node: DecompositionNode, patch: DecompositionNodePatch) =>
    run(() => client.editDecompositionNode(dec.id, node.id, dec.revision, patch));

  return (
    <div className="page">
      <div className="card">
        <h3>拆解「{task.title}」</h3>
        <p className={dec.fallback ? 'error' : 'muted'} role={dec.fallback ? 'alert' : undefined}>
          来源：{decompositionSourceLabel(dec)} · 总预算 {fmtYuan(task.budget_cents)}
        </p>
        <p className="muted">
          一层一层往下拆，每一层都能改。每一步要说得出交什么、怎么验、谁负责、钱够不够托管，
          四样齐了才算能开工的一步；确认后只有这些步骤会发布出去。
        </p>
        <TreeLevel nodes={dec.nodes} parent={null} busy={busy} editable={dec.status === 'proposed'}
                   certCategories={certCategories}
                   onEdit={edit}
                   onSplit={(n) => run(() => client.expandDecomposition(dec.id, dec.revision, [n.id]))}
                   onDelete={(n) => run(() => client.deleteDecompositionNode(dec.id, n.id, dec.revision))} />

        {dec.unresolved.length > 0 && (
          <div className="card" style={{ marginTop: 12 }}>
            <strong>还有 {dec.unresolved.length} 步没说清，补齐后才能确认：</strong>
            <ul>
              {dec.unresolved.map((u) => <li key={u.id}>{u.title}：{u.why}</li>)}
            </ul>
          </div>
        )}
        {notice && <p className="muted">{notice}</p>}
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ marginTop: 12 }}>
          {dec.can_expand && (
            <button className="ghost" disabled={busy}
                    onClick={() => void run(async () => {
                      const r = await client.expandDecomposition(dec.id, dec.revision);
                      return r;
                    }, '已往下拆了一层')}>
              继续拆下一层
            </button>
          )}
          <button disabled={busy || dec.unresolved.length > 0}
                  onClick={async () => {
                    setError('');
                    setBusy(true);
                    try {
                      await client.confirmDecomposition(dec.id);
                      nav(`/tasks/${taskId}`);
                    } catch (e) {
                      setError(apiErrorText(e));
                    } finally {
                      setBusy(false);
                    }
                  }}>
            确认并发布可开工的步骤
          </button>
          <Link to={`/tasks/${taskId}`}><button className="ghost" type="button">稍后再拆</button></Link>
        </div>
      </div>
    </div>
  );
}

function TreeLevel(props: {
  nodes: DecompositionNode[];
  parent: number | null;
  busy: boolean;
  editable: boolean;
  certCategories: Array<{ name: string; required_cert: string }>;
  onEdit: (n: DecompositionNode, patch: DecompositionNodePatch) => void;
  onSplit: (n: DecompositionNode) => void;
  onDelete: (n: DecompositionNode) => void;
}) {
  const kids = childrenOf(props.nodes, props.parent);
  if (!kids.length) return null;
  return (
    <ul className="decompose-tree" style={{ listStyle: 'none', paddingLeft: props.parent === null ? 0 : 20 }}>
      {/* node 放在展开之后：props 里可能带着上一级的 node，放前面会被它盖掉、无限递归 */}
      {kids.map((n) => <TreeNode key={n.id} {...props} node={n} />)}
    </ul>
  );
}

function TreeNode(props: Parameters<typeof TreeLevel>[0] & { node: DecompositionNode }) {
  const { node: n, nodes, busy, editable } = props;
  const [editing, setEditing] = useState(false);
  const [deliverable, setDeliverable] = useState(n.deliverable);
  const [acceptance, setAcceptance] = useState(n.acceptance);
  const [budget, setBudget] = useState(String(n.budget_cents / 100));
  const openEnd = isOpenEnd(nodes, n);
  const byId = (id: number) => nodes.find((x) => x.id === id)?.title ?? `#${id}`;

  return (
    <li className="card" data-node={n.id} style={{ marginTop: 8 }}>
      <div className="row">
        <strong className="grow">{n.title}</strong>
        <span className="muted">{fmtYuan(n.budget_cents)}</span>
        {openEnd && n.executor_kind && (
          <span className={`badge ${n.executor_kind === 'unknown' ? '' : 'ok'}`}
                data-executor={n.executor_kind}>{executorLabel(n)}</span>
        )}
      </div>
      {n.depends_on.length > 0 && <p className="muted">前置：{n.depends_on.map(byId).join('、')}</p>}
      {openEnd && n.leaf && (
        <p className="muted">交付物：{n.deliverable} · 验收：{n.acceptance}</p>
      )}
      {openEnd && n.executor_basis && <p className="muted" style={{ fontSize: 12 }}>依据：{n.executor_basis}</p>}
      {openEnd && !n.leaf && n.missing.length > 0 && (
        <p className="error">还差：{n.missing.map((m) => LEAF_CRITERION_LABEL[m]).join('、')}</p>
      )}
      {n.stop_note && n.stop_reason !== 'criteria_met' && <p className="muted">⏸ {n.stop_note}</p>}

      {editable && openEnd && n.executor_kind === 'unknown' && (
        <div className="row" style={{ marginTop: 6 }}>
          <button className="ghost" disabled={busy} onClick={() => props.onEdit(n, { executor_hint: 'human' })}>
            交给人做
          </button>
          {props.certCategories.length > 0 && (
            <select aria-label={`「${n.title}」需要的资质类目`} defaultValue=""
                    onChange={(e) => e.target.value && props.onEdit(n, { category: e.target.value })}>
              <option value="">需要持证专家：选类目…</option>
              {props.certCategories.map((c) => (
                <option key={c.name} value={c.name}>{c.name}（{c.required_cert}）</option>
              ))}
            </select>
          )}
        </div>
      )}

      {editable && openEnd && (
        <div className="row" style={{ marginTop: 6 }}>
          <button className="ghost" disabled={busy} onClick={() => setEditing((v) => !v)}>
            {editing ? '收起' : (n.leaf ? '编辑' : '补齐这一步')}
          </button>
          <button className="ghost" disabled={busy} onClick={() => props.onSplit(n)}>拆这一步</button>
          <button className="ghost" disabled={busy} onClick={() => props.onDelete(n)}>删除</button>
        </div>
      )}
      {editing && (
        <form className="form" style={{ marginTop: 6 }} onSubmit={(e) => {
          e.preventDefault();
          props.onEdit(n, {
            deliverable, acceptance,
            budget_cents: Math.round(parseFloat(budget || '0') * 100),
          });
          setEditing(false);
        }}>
          <label>交付物（交出来的具体是什么）
            <input value={deliverable} onChange={(e) => setDeliverable(e.target.value)} />
          </label>
          <label>验收标准（不懂全局的人也能判断做没做完）
            <input value={acceptance} onChange={(e) => setAcceptance(e.target.value)} />
          </label>
          <label>预算（元）
            <input type="number" min={0.01} step={0.01} value={budget} onChange={(e) => setBudget(e.target.value)} />
          </label>
          <button type="submit" disabled={busy}>保存这一步</button>
        </form>
      )}
      <TreeLevel {...props} parent={n.id} />
    </li>
  );
}
