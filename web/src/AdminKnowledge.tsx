// KB-070~076 经验子类的运营面（108 号 spec）。
//
// 归并的三条判定里，「像又不够像」那一段刻意不让机器自己定——它既可能是子类该分裂，
// 也可能是该放宽，两个方向的处置相反。这一块就是那一段的出口：待定区逐条判、
// 每个大类的阈值用人工标注标定（换 embedding 模型后必须重标）、风控事后标记的任务撤回、
// 子类合并与改名。
import {
  apiErrorText, fmtYuan, type KnowledgeAdminOverview, type KnowledgeCalibrationPair,
  type KnowledgeUndecidedRow, type ReusableUnit, type ReusableUnitKind,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

export function KnowledgeAdmin() {
  const { client } = useApp();
  const [view, setView] = useState<KnowledgeAdminOverview | null>(null);
  const [rows, setRows] = useState<KnowledgeUndecidedRow[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setView(await client.knowledgeAdminOverview().catch(() => null));
    const r = await client.knowledgeUndecided().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setError('');
    setNotice('');
    try {
      await fn();
      setNotice(ok);
      await load();
    } catch (e) {
      setError(apiErrorText(e));
    }
  }

  // 运营台上的一块：响应不像预期（旧服务端没有这个接口、或返回了别的东西）时不画，
  // **不许把整个运营台带崩**——V133 的子任务进度块是同一条教训
  if (!view || !Array.isArray(view.thresholds) || !view.states) return null;
  const stale = view.thresholds.filter((t) => t.stale);
  return (
    <section className="card">
      <h3>经验子类（待定 {view.states.undecided} · 等待标定 {view.states.held}）</h3>
      <p className="muted">
        当前向量模型 {view.model}{view.semantic ? '' : '（不是语义模型：不会自动新建子类，只并进运营建的子类）'}
        · 活跃子类 {view.active_clusters} 个 · 已归并样本 {view.states.assigned} · 风控排除 {view.states.excluded}
      </p>
      {stale.length > 0 && (
        <p className="error" role="alert">
          这些大类的阈值是用旧模型标定的，归并会被拒：{stale.map((t) => t.category).join('、')}——请重新标定
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {notice && <p className="muted">{notice}</p>}

      {rows.length > 0 && (
        <div className="list" style={{ marginTop: 8 }}>
          {rows.map((r) => (
            <div className="task-item" key={r.card_id} data-card={r.card_id}>
              <div>
                <strong>{r.title}</strong> · {r.category} · {r.outcome}
                <p className="muted">
                  {r.state === 'held' ? `等待标定：${r.hint.note ?? ''}` : (r.hint.why ?? '')}
                  {r.hint.nearest_id ? ` · 最像「${r.hint.nearest_label}」（相似度 ${r.hint.similarity}）` : ''}
                </p>
              </div>
              {r.state === 'undecided' && (
                <span className="row">
                  {r.hint.nearest_id ? (
                    <button className="ghost" onClick={() => act(
                      () => client.assignKnowledgeCard(r.card_id, r.hint.nearest_id ?? null),
                      `已并入「${r.hint.nearest_label}」`)}>
                      并入「{r.hint.nearest_label}」
                    </button>
                  ) : null}
                  <button onClick={() => {
                    const label = prompt('新子类的名字（如：跑腿·同城代取快递）：')?.trim();
                    if (label) void act(() => client.assignKnowledgeCard(r.card_id, null, label), `已新建「${label}」`);
                  }}>新建子类</button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      <Calibrate onDone={(msg) => { setNotice(msg); void load(); }} categories={[
        ...new Set([...rows.filter((r) => r.state === 'held').map((r) => r.category), ...view.thresholds.map((t) => t.category)]),
      ]} />

      <div className="row" style={{ marginTop: 12 }}>
        <button className="ghost" onClick={() => {
          const id = Number(prompt('从子类里撤回哪个任务的经验？任务 ID：'));
          const reason = prompt('撤回理由（记入审计）：')?.trim() ?? '';
          if (id && reason) void act(() => client.retractKnowledgeTask(id, reason), `任务 #${id} 的经验已撤回，受影响的子类已重算`);
        }}>撤回某个任务的经验</button>
        <button className="ghost" onClick={() => {
          const from = Number(prompt('把哪个子类并掉？子类 ID：'));
          const to = Number(prompt('并进哪个子类？子类 ID：'));
          if (from && to) void act(() => client.mergeKnowledgeCluster(from, to), `子类 #${from} 已并入 #${to}`);
        }}>合并子类</button>
        <button className="ghost" onClick={() => {
          const id = Number(prompt('改哪个子类的名字？子类 ID：'));
          const label = prompt('新名字：')?.trim() ?? '';
          if (id && label) void act(() => client.renameKnowledgeCluster(id, label), `子类 #${id} 已改名`);
        }}>子类改名</button>
      </div>

      <Units />
    </section>
  );
}

/** KB-071 阈值标定：逐对判「是不是一回事」，服务端扫出误判最少的阈值。 */
function Calibrate({ categories, onDone }: { categories: string[]; onDone: (msg: string) => void }) {
  const { client } = useApp();
  const [category, setCategory] = useState('');
  const [pairs, setPairs] = useState<KnowledgeCalibrationPair[]>([]);
  const [labels, setLabels] = useState<Record<number, boolean>>({});
  const [error, setError] = useState('');

  async function start() {
    setError('');
    setLabels({});
    try {
      setPairs(await client.knowledgeCalibrationPairs(category));
    } catch (e) {
      setError(apiErrorText(e));
    }
  }

  const done = pairs.length > 0 && pairs.every((_, i) => i in labels);
  return (
    <div style={{ marginTop: 12 }}>
      <strong>标定归并阈值</strong>
      <div className="row" style={{ marginTop: 6 }}>
        <input list="kb-categories" value={category} onChange={(e) => setCategory(e.target.value)}
               placeholder="大类，例如：跑腿" aria-label="要标定的大类" />
        <datalist id="kb-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
        <button className="ghost" disabled={!category.trim()} onClick={() => void start()}>取一组样本对</button>
      </div>
      {error && <p className="error">{error}</p>}
      {pairs.length > 0 && (
        <div className="list" style={{ marginTop: 6 }}>
          {pairs.map((p, i) => (
            <div className="task-item" key={i} data-pair={i}>
              <span className="muted">
                {p.a.title}（{fmtYuan(p.a.price_actual_cents)}）vs {p.b.title}（{fmtYuan(p.b.price_actual_cents)}）
              </span>
              <span className="row">
                <button className={labels[i] === true ? '' : 'ghost'} onClick={() => setLabels({ ...labels, [i]: true })}>是一回事</button>
                <button className={labels[i] === false ? '' : 'ghost'} onClick={() => setLabels({ ...labels, [i]: false })}>不是</button>
              </span>
            </div>
          ))}
          <button disabled={!done} onClick={async () => {
            setError('');
            try {
              const t = await client.calibrateKnowledge(category, pairs.map((p, i) => ({
                a: p.a.card_id, b: p.b.card_id, same: labels[i],
              })));
              setPairs([]);
              onDone(`「${t.category}」已标定：并入 ≥ ${t.tau_merge}，新建 < ${t.tau_near}（${t.labeled_pairs} 对，误判 ${t.errors}）`);
            } catch (e) {
              setError(apiErrorText(e));
            }
          }}>用这些标注标定</button>
        </div>
      )}
    </div>
  );
}

const KIND_OPTIONS: Array<[ReusableUnitKind, string]> = [
  ['procedure', '分解流程'], ['checklist', '验收清单'], ['price_hint', '报价提示'], ['skill_tool', '可执行工具'],
];

/** KB-080~084 可复用单元：从子类蒸馏（排除条件与两个授权位必须明说），以及结果回流后的复核。 */
function Units() {
  const { client } = useApp();
  const [review, setReview] = useState<ReusableUnit[]>([]);
  const [clusterId, setClusterId] = useState('');
  const [kind, setKind] = useState<ReusableUnitKind>('procedure');
  const [exclusions, setExclusions] = useState('');
  const [reuse, setReuse] = useState(true);
  const [train, setTrain] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    const r = await client.adminKnowledgeUnits('needs_review').catch(() => []);
    setReview(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    setError('');
    setNotice('');
    try {
      await fn();
      setNotice(ok);
      await load();
    } catch (e) {
      setError(apiErrorText(e));
    }
  }

  const excl = exclusions.split(/[\n；;]/).map((x) => x.trim()).filter(Boolean);
  return (
    <div style={{ marginTop: 16 }}>
      <strong>可复用单元</strong>
      <p className="muted">只从双方都同意经验复用的样本里提炼。排除条件必填——只说「适用于什么」的单元，会在不适用的场合被照样调用。</p>
      {error && <p className="error">{error}</p>}
      {notice && <p className="muted">{notice}</p>}
      <div className="row" style={{ marginTop: 6, flexWrap: 'wrap' }}>
        <input value={clusterId} onChange={(e) => setClusterId(e.target.value)} placeholder="子类 ID" aria-label="从哪个子类蒸馏" />
        <select value={kind} onChange={(e) => setKind(e.target.value as ReusableUnitKind)} aria-label="单元类型">
          {KIND_OPTIONS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <label><input type="checkbox" checked={reuse} onChange={(e) => setReuse(e.target.checked)} /> 允许复用</label>
        <label><input type="checkbox" checked={train} onChange={(e) => setTrain(e.target.checked)} /> 允许训练</label>
      </div>
      <textarea value={exclusions} onChange={(e) => setExclusions(e.target.value)} rows={2} style={{ width: '100%', marginTop: 6 }}
                placeholder="排除条件，一行一条：什么情况下不该用这个单元" aria-label="排除条件" />
      <button disabled={!Number(clusterId) || excl.length === 0} onClick={() => void act(
        () => client.distillKnowledgeUnit(Number(clusterId), {
          kind, exclusions: excl, reuse_license: reuse, train_license: train,
          ...(kind === 'skill_tool' ? { tool: 'acceptance_report_draft' } : {}),
        }),
        `已从子类 #${clusterId} 蒸馏出一个单元`)}>蒸馏单元</button>

      {review.length > 0 && (
        <div className="list" style={{ marginTop: 8 }}>
          <p><strong>待复核（{review.length}）</strong>：返工与失败过半，或有贡献者撤回了复用授权</p>
          {review.map((u) => (
            <div className="task-item" key={u.id} data-unit={u.id}>
              <div>
                <strong>{u.kind_label} · {u.title}</strong> v{u.version}
                <p className="muted">
                  用过 {u.validation.uses} 次：做成 {u.validation.closed}、返工 {u.validation.reworked}、失败 {u.validation.failed}
                  · 剩余来源样本 {u.sample_count}
                </p>
              </div>
              <span className="row">
                <button className="ghost" onClick={() => {
                  const note = prompt('改了什么？（重新启用会升版本、验证从头算）')?.trim() ?? '';
                  if (note.length >= 4) void act(() => client.setKnowledgeUnitStatus(u.id, 'active', note), `单元 #${u.id} 已重新启用`);
                }}>重新启用</button>
                <button className="ghost" onClick={() => {
                  const note = prompt('下线理由（记入审计）：')?.trim() ?? '';
                  if (note.length >= 4) void act(() => client.setKnowledgeUnitStatus(u.id, 'retired', note), `单元 #${u.id} 已下线`);
                }}>下线</button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
