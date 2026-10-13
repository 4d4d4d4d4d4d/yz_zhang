// APP-077 App 上的逐层拆解（107 号 spec；规则见 96 / 106 号）。
//
// 用户复述的六条愿景里，「AI 协助任务拆解」是唯一一条手机上一个入口都没有的
// （propose / confirm / taskTree 三个方法 App 零调用）。这一页与 web 的拆解页同一套规则、
// 同一份文案（共享 SDK）：一层一层往下长、每层能改；每个叶子说清谁能做、依据是什么；
// 「判不了」的步骤就地给去处，没说清之前不让确认。
import {
  LEAF_CRITERION_LABEL, TASK_STATUS_LABEL, apiErrorText, childrenOf, decompositionSourceLabel,
  executorLabel, fmtYuan, isOpenEnd, type Decomposition, type DecompositionNode,
  type Cockpit, type DecompositionNodePatch, type PlatformClient, type Task, type TaskTree,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export function DecomposeScreen({ client, task, onBack, onConfirmed }: {
  client: PlatformClient; task: Task; onBack: () => void; onConfirmed: () => void;
}) {
  const [dec, setDec] = useState<Decomposition | null>(null);
  const [none, setNone] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [certCategories, setCertCategories] = useState<Array<{ name: string; required_cert: string }>>([]);

  const load = useCallback(async () => {
    setError('');
    try {
      setDec(await client.currentDecomposition(task.id));
    } catch (e) {
      if ((e as { code?: string }).code !== 'no_decomposition_in_progress') throw e;
      // 还没拆过的草稿项目：开始拆；已经确认过的不再拆
      const tree = await client.taskTree(task.id).catch(() => null);
      if (task.status === 'draft' && !(tree && tree.children.length)) setDec(await client.propose(task.id));
      else setNone(true);
    }
  }, [client, task]);

  useEffect(() => {
    void load().catch((e) => setError(apiErrorText(e)));
    void client.categories()
      .then((rows) => setCertCategories(rows.filter((c) => c.required_cert)))
      .catch(() => {});
  }, [load, client]);

  async function run(fn: () => Promise<Decomposition>) {
    setError('');
    setBusy(true);
    try {
      setDec(await fn());
    } catch (e) {
      setError(apiErrorText(e));
      if ((e as { code?: string }).code === 'decomposition_changed') {
        void client.currentDecomposition(task.id).then(setDec).catch(() => {});
      }
    } finally {
      setBusy(false);
    }
  }

  const back = (
    <TouchableOpacity onPress={onBack}><Text style={styles.link}>← 返回任务</Text></TouchableOpacity>
  );
  if (none) {
    return <View style={styles.page}>{back}<Text style={styles.muted}>这个任务没有进行中的拆解（已经确认过，或者它不是草稿了）。</Text></View>;
  }
  if (!dec) {
    return <View style={styles.page}>{back}{error ? <Text style={styles.error}>{error}</Text> : <Text style={styles.muted}>正在拆…</Text>}</View>;
  }

  const blocked = dec.unresolved.length > 0;
  return (
    <View style={styles.page}>
      {back}
      <Text style={styles.title}>拆解「{task.title}」</Text>
      <Text style={dec.fallback ? styles.error : styles.muted} accessibilityRole={dec.fallback ? 'alert' : undefined}>
        来源：{decompositionSourceLabel(dec)} · 总预算 {fmtYuan(task.budget_cents)}
      </Text>
      <Text style={styles.muted}>每一步要说得出交什么、怎么验、谁负责、钱够不够托管，四样齐了才算能开工。</Text>
      <Level client={client} dec={dec} parent={null} busy={busy} certCategories={certCategories}
             onEdit={(n, patch) => run(() => client.editDecompositionNode(dec.id, n.id, dec.revision, patch))}
             onSplit={(n) => run(() => client.expandDecomposition(dec.id, dec.revision, [n.id]))}
             onDelete={(n) => run(() => client.deleteDecompositionNode(dec.id, n.id, dec.revision))} />
      {blocked && (
        <View style={styles.card}>
          <Text style={styles.title}>还有 {dec.unresolved.length} 步没说清，补齐后才能确认：</Text>
          {dec.unresolved.map((u) => <Text key={u.id} style={styles.muted}>· {u.title}：{u.why}</Text>)}
        </View>
      )}
      {!!error && <Text style={styles.error}>{error}</Text>}
      {dec.can_expand && (
        <TouchableOpacity disabled={busy} style={styles.ghost}
                          onPress={() => void run(() => client.expandDecomposition(dec.id, dec.revision))}>
          <Text>继续拆下一层</Text>
        </TouchableOpacity>
      )}
      <TouchableOpacity disabled={busy || blocked} accessibilityState={{ disabled: busy || blocked }}
                        style={[styles.primary, (busy || blocked) && styles.disabled]}
                        onPress={async () => {
                          setError('');
                          setBusy(true);
                          try {
                            await client.confirmDecomposition(dec.id);
                            onConfirmed();
                          } catch (e) {
                            setError(apiErrorText(e));
                          } finally {
                            setBusy(false);
                          }
                        }}>
        <Text style={styles.primaryText}>确认并发布可开工的步骤</Text>
      </TouchableOpacity>
    </View>
  );
}

type LevelProps = {
  client: PlatformClient;
  dec: Decomposition;
  parent: number | null;
  busy: boolean;
  certCategories: Array<{ name: string; required_cert: string }>;
  onEdit: (n: DecompositionNode, patch: DecompositionNodePatch) => void;
  onSplit: (n: DecompositionNode) => void;
  onDelete: (n: DecompositionNode) => void;
};

function Level(props: LevelProps) {
  const kids = childrenOf(props.dec.nodes, props.parent);
  if (!kids.length) return null;
  return (
    <View style={props.parent === null ? undefined : styles.nested}>
      {/* node 放在展开之后（web 那一版吃过亏：被上一级的 node 盖掉、无限递归） */}
      {kids.map((n) => <Node key={n.id} {...props} node={n} />)}
    </View>
  );
}

function Node(props: LevelProps & { node: DecompositionNode }) {
  const { node: n, dec, busy } = props;
  const [editing, setEditing] = useState(false);
  const [deliverable, setDeliverable] = useState(n.deliverable);
  const [acceptance, setAcceptance] = useState(n.acceptance);
  const editable = dec.status === 'proposed';
  const openEnd = isOpenEnd(dec.nodes, n);
  const titleOf = (id: number) => dec.nodes.find((x) => x.id === id)?.title ?? `#${id}`;

  return (
    <View style={styles.card} testID={`node-${n.id}`}>
      <Text style={styles.title}>{n.title}  <Text style={styles.muted}>{fmtYuan(n.budget_cents)}</Text></Text>
      {openEnd && !!n.executor_kind && (
        <Text style={n.executor_kind === 'unknown' ? styles.warn : styles.badge}>{executorLabel(n)}</Text>
      )}
      {n.depends_on.length > 0 && <Text style={styles.muted}>前置：{n.depends_on.map(titleOf).join('、')}</Text>}
      {openEnd && n.leaf && <Text style={styles.muted}>交付物：{n.deliverable} · 验收：{n.acceptance}</Text>}
      {openEnd && !!n.executor_basis && <Text style={styles.small}>依据：{n.executor_basis}</Text>}
      {openEnd && !n.leaf && n.missing.length > 0 && (
        <Text style={styles.error}>还差：{n.missing.map((m) => LEAF_CRITERION_LABEL[m]).join('、')}</Text>
      )}
      {!!n.stop_note && n.stop_reason !== 'criteria_met' && <Text style={styles.muted}>⏸ {n.stop_note}</Text>}

      {editable && openEnd && n.executor_kind === 'unknown' && (
        <View style={styles.chips}>
          <TouchableOpacity disabled={busy} style={styles.chip} onPress={() => props.onEdit(n, { executor_hint: 'human' })}>
            <Text>交给人做</Text>
          </TouchableOpacity>
          {props.certCategories.map((c) => (
            <TouchableOpacity key={c.name} disabled={busy} style={styles.chip}
                              onPress={() => props.onEdit(n, { category: c.name })}>
              <Text>需要{c.required_cert}（{c.name}）</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      {editable && openEnd && (
        <View style={styles.chips}>
          <TouchableOpacity disabled={busy} style={styles.chip} onPress={() => setEditing((v) => !v)}>
            <Text>{editing ? '收起' : (n.leaf ? '编辑' : '补齐这一步')}</Text>
          </TouchableOpacity>
          <TouchableOpacity disabled={busy} style={styles.chip} onPress={() => props.onSplit(n)}>
            <Text>拆这一步</Text>
          </TouchableOpacity>
          <TouchableOpacity disabled={busy} style={styles.chip} onPress={() => props.onDelete(n)}>
            <Text>删除</Text>
          </TouchableOpacity>
        </View>
      )}
      {editing && (
        <View style={{ gap: 6 }}>
          <TextInput style={styles.input} placeholder="交付物（交出来的具体是什么）"
                     value={deliverable} onChangeText={setDeliverable} />
          <TextInput style={styles.input} placeholder="验收标准（不懂全局的人也能判断做没做完）"
                     value={acceptance} onChangeText={setAcceptance} />
          <TouchableOpacity disabled={busy} style={styles.primary}
                            onPress={() => { props.onEdit(n, { deliverable, acceptance }); setEditing(false); }}>
            <Text style={styles.primaryText}>保存这一步</Text>
          </TouchableOpacity>
        </View>
      )}
      <Level {...props} parent={n.id} />
    </View>
  );
}

/** AI-DEC-021 子任务进度：确认之后，项目型任务的子步骤在这里看、点进去办。 */
export function TaskTreeBlock({ client, task, onOpenTask }: {
  client: PlatformClient; task: Task; onOpenTask: (t: Task) => void;
}) {
  const [tree, setTree] = useState<TaskTree | null>(null);
  useEffect(() => {
    void client.taskTree(task.id).then(setTree).catch(() => setTree(null));
  }, [client, task.id]);
  // 进度是详情页上的一个小角落：响应不像预期时不画，**不许把整页带崩**
  if (!tree || !Array.isArray(tree.children) || tree.children.length === 0) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.title}>子任务进度 {tree.progress_pct}%</Text>
      {tree.children.map((c) => (
        <TouchableOpacity key={c.id} onPress={() => void client.getTask(c.id).then(onOpenTask).catch(() => {})}>
          <Text style={styles.row}>{c.title}  <Text style={styles.muted}>{fmtYuan(c.budget_cents)} · {TASK_STATUS_LABEL[c.status]}</Text></Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

/** SPACE-024 合作驾驶舱（APP-007 移动简化版）：进度、钱、要我出手的事、关键路径。 */
export function CockpitBlock({ client, taskId }: { client: PlatformClient; taskId: number }) {
  const [data, setData] = useState<Cockpit | null>(null);
  useEffect(() => { void client.cockpit(taskId).then(setData).catch(() => setData(null)); }, [client, taskId]);
  if (!data || !Array.isArray(data.nodes) || data.nodes.length === 0) return null;
  const title = (id: number) => data.nodes.find((n) => n.id === id)?.title ?? `#${id}`;
  const b = data.budget;
  return (
    <View style={styles.card} accessibilityLabel="合作驾驶舱">
      <Text style={styles.title}>合作驾驶舱 · {data.steps_done}/{data.steps_total} 步完成</Text>
      <Text style={styles.muted}>计划 {fmtYuan(b.planned_cents)} · 已托管 {fmtYuan(b.committed_cents)} · 已付 {fmtYuan(b.paid_cents)} · 还剩 {fmtYuan(b.remaining_cents)}</Text>
      {data.alerts.map((a, i) => (
        <Text key={i} style={a.kind === 'dispute' || a.kind === 'overdue' ? styles.warn : styles.row}>• {a.text}</Text>
      ))}
      {data.critical_path.length > 0 && (
        <Text style={styles.small}>关键路径：{data.critical_path.map(title).join(' → ')}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { gap: 10 },
  link: { color: '#275c52' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  nested: { marginLeft: 12, gap: 6 },
  title: { fontSize: 15, fontWeight: '600' },
  row: { fontSize: 15 },
  muted: { color: '#6b7280', fontSize: 13 },
  small: { color: '#6b7280', fontSize: 12 },
  error: { color: '#b91c1c', fontSize: 13 },
  warn: { color: '#92400e', fontSize: 13, fontWeight: '600' },
  badge: { color: '#166534', fontSize: 13, fontWeight: '600' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { backgroundColor: '#f1f5f2', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 6 },
  ghost: { borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#cbd5e1', alignItems: 'center' },
  primary: { backgroundColor: '#275c52', borderRadius: 10, padding: 12, alignItems: 'center' },
  primaryText: { color: '#fff', fontWeight: '600' },
  disabled: { opacity: 0.4 },
});
