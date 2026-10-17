// APP-077 App 上的逐层拆解（107 号 spec；规则见 96 / 106 号）。
//
// 用户复述的六条愿景里，「AI 协助任务拆解」是唯一一条手机上一个入口都没有的
// （propose / confirm / taskTree 三个方法 App 零调用）。这一页与 web 的拆解页同一套规则、
// 同一份文案（共享 SDK）：一层一层往下长、每层能改；每个叶子说清谁能做、依据是什么；
// 「判不了」的步骤就地给去处，没说清之前不让确认。
import {
  LEAF_CRITERION_LABEL, TASK_STATUS_LABEL, apiErrorText, childrenOf, daySummaryLine, daysStillShort, dayShiftChangeLine, shiftEditableDays, raiseToCents, REBOOST_INVITE_COUNT, reboostLine,
  decompositionSourceLabel, executorLabel, fmtYuan, isOpenEnd, type Decomposition, type DecompositionNode,
  type Cockpit, type DayApplicant, type DecompositionNodePatch, type PlatformClient, type Task, type TaskTree,
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

/** AI-DEC-021 子任务进度：确认之后，项目型任务的子步骤在这里看、点进去办；SCN-116 起多人、多天的名额也在这里。 */
export function TaskTreeBlock({ client, task, onOpenTask, meId = null }: {
  client: PlatformClient; task: Task; onOpenTask: (t: Task) => void;
  /** SCN-118 不是发单人时，多天的单上可以一次报多天 */
  meId?: number | null;
}) {
  const [tree, setTree] = useState<TaskTree | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [applyMsg, setApplyMsg] = useState('');
  // SCN-126 发单人按人选
  const [people, setPeople] = useState<DayApplicant[]>([]);
  const [pickMsg, setPickMsg] = useState('');
  // SCN-121 发单人补招缺人的那天
  const [boostDay, setBoostDay] = useState('');
  const [boostYuan, setBoostYuan] = useState('');
  const [boostMsg, setBoostMsg] = useState('');
  const [boostInvite, setBoostInvite] = useState(false);   // SCN-137 顺带邀请
  // SCN-138 发单人改某一天的时段
  const [shiftDay, setShiftDay] = useState('');
  const [shiftFrom, setShiftFrom] = useState('');
  const [shiftTo, setShiftTo] = useState('');
  const [shiftMsg, setShiftMsg] = useState('');
  const isPoster = meId !== null && meId === task.creator_id && (task.days ?? 1) > 1;
  const loadPeople = useCallback(() => {
    if (!isPoster) return;
    client.dayApplicants(task.id).then((r) => setPeople(Array.isArray(r) ? r : [])).catch(() => setPeople([]));
  }, [client, task.id, isPoster]);
  useEffect(() => { loadPeople(); }, [loadPeople]);
  useEffect(() => {
    void client.taskTree(task.id).then(setTree).catch(() => setTree(null));
  }, [client, task.id]);
  // 进度是详情页上的一个小角落：响应不像预期时不画，**不许把整页带崩**
  if (!tree || !Array.isArray(tree.children) || tree.children.length === 0) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.title}>子任务进度 {tree.progress_pct}%</Text>
      {/* SCN-116 多天名额按天汇总（174 号 spec）：哪天还缺几个人 */}
      {Array.isArray(tree.by_day) && tree.by_day.length > 0 && (
        <View accessibilityLabel="按天看名额">
          <Text style={daysStillShort(tree.by_day).length ? styles.warn : styles.muted}>
            {daysStillShort(tree.by_day).length ? `还有 ${daysStillShort(tree.by_day).length} 天缺人` : '每天的名额都招到人了'}
          </Text>
          {tree.by_day.map((d) => <Text key={d.date} style={styles.row}>{daySummaryLine(d)}</Text>)}
          {/* SCN-118 一个人一次报多天（177 号 spec）：勾还缺人的那几天 */}
          {meId !== null && meId !== task.creator_id && daysStillShort(tree.by_day).length > 0 && (
            <View accessibilityLabel="一次报多天">
              <Text style={styles.muted}>这几天你都能来？勾上一次报完（每天报一个名额，发单人逐天选人）：</Text>
              {daysStillShort(tree.by_day).map((d) => (
                <TouchableOpacity key={d.date} accessibilityRole="checkbox" accessibilityLabel={`报 ${d.date}`}
                                  accessibilityState={{ checked: picked.includes(d.date) }}
                                  onPress={() => setPicked((p) => p.includes(d.date) ? p.filter((x) => x !== d.date) : [...p, d.date])}>
                  <Text style={styles.row}>{picked.includes(d.date) ? '☑ ' : '☐ '}{d.date.slice(5)}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity disabled={picked.length === 0} onPress={() => {
                setApplyMsg('');
                void client.applyDays(task.id, picked).then((r) => {
                  setPicked([]);
                  setApplyMsg(`已报：${r.applied.map((a) => a.date.slice(5)).join('、') || '无'}`
                    + (r.skipped.length ? `；没报：${r.skipped.map((s) => `${s.date.slice(5)}（${s.reason}）`).join('、')}` : ''));
                }).catch((e) => setApplyMsg(apiErrorText(e)));
              }}>
                <Text style={styles.link}>报这几天</Text>
              </TouchableOpacity>
              {!!applyMsg && <Text style={styles.muted}>{applyMsg}</Text>}
            </View>
          )}
          {/* SCN-126 发单人按人选：一次选同一个人的多天（181 号 spec） */}
          {isPoster && (people.length > 0 || !!pickMsg) && (
            <View accessibilityLabel="按人选">
              <Text style={styles.muted}>谁报了哪几天：</Text>
              {people.map((p) => (
                <TouchableOpacity key={p.applicant_id} onPress={() => {
                  setPickMsg('');
                  void client.acceptPerson(task.id, p.applicant_id).then((r) => {
                    setPickMsg(`已选 ${p.nickname}：${r.accepted.map((a) => a.date.slice(5)).join('、')}（每天一份合约，去各名额签署、托管）`
                      + (r.skipped.length ? `；没选上：${r.skipped.map((s) => `${s.date.slice(5)}（${s.reason}）`).join('、')}` : ''));
                    loadPeople();
                  }).catch((e) => setPickMsg(apiErrorText(e)));
                }}>
                  <Text style={styles.link}>{p.nickname} · {p.days.map((d) => d.date.slice(5)).join('、')} → 选 TA 的这 {p.days.length} 天</Text>
                </TouchableOpacity>
              ))}
              {!!pickMsg && <Text style={styles.muted}>{pickMsg}</Text>}
            </View>
          )}
          {/* SCN-121 缺人的那天一键补招（196 号 spec）：再推一次，可选每个名额加价 */}
          {isPoster && daysStillShort(tree.by_day).length > 0 && (
            <View accessibilityLabel="补招">
              <Text style={styles.muted}>缺人的那天再推一次（推给附近有空、订阅了这个类目的人）：</Text>
              {daysStillShort(tree.by_day).map((d) => (
                <TouchableOpacity key={d.date} accessibilityRole="radio" accessibilityLabel={`补招 ${d.date}`}
                                  accessibilityState={{ selected: (boostDay || daysStillShort(tree.by_day)[0].date) === d.date }}
                                  onPress={() => setBoostDay(d.date)}>
                  <Text style={styles.row}>{(boostDay || daysStillShort(tree.by_day)[0].date) === d.date ? '◉ ' : '○ '}{d.date.slice(5)}</Text>
                </TouchableOpacity>
              ))}
              <TextInput style={styles.input} accessibilityLabel="每个名额加价（元）" placeholder="每个名额加价（元，可不填）"
                         keyboardType="decimal-pad" value={boostYuan} onChangeText={setBoostYuan} />
              <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: boostInvite }}
                                onPress={() => setBoostInvite(!boostInvite)}>
                <Text style={styles.row}>{boostInvite ? '☑ ' : '☐ '}顺带邀请 {REBOOST_INVITE_COUNT} 个做过这类活、那天有空的人</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => {
                const cents = raiseToCents(boostYuan);
                if (cents === null) { setBoostMsg('加价写一个正数（元），最多两位小数；不加价就空着'); return; }
                const target = boostDay || daysStillShort(tree.by_day)[0].date;
                setBoostMsg('');
                void client.reboostDay(task.id, target, cents, boostInvite ? REBOOST_INVITE_COUNT : 0).then((r) => {
                  setBoostMsg(reboostLine(r, boostInvite)); setBoostYuan('');
                  void client.taskTree(task.id).then(setTree).catch(() => {});
                }).catch((e) => setBoostMsg(apiErrorText(e)));
              }}>
                <Text style={styles.link}>补招这天</Text>
              </TouchableOpacity>
              {!!boostMsg && <Text style={styles.muted}>{boostMsg}</Text>}
            </View>
          )}
          {/* SCN-138 发布后改某一天的时段（202 号 spec）：只改还在招的名额 */}
          {isPoster && shiftEditableDays(tree.by_day).length > 0 && (
            <View accessibilityLabel="改某天的时段">
              <Text style={styles.muted}>某一天的时间变了？只改还在招的名额；已经有人接的要走合约变更单：</Text>
              {shiftEditableDays(tree.by_day).map((date, _i, all) => (
                <TouchableOpacity key={date} accessibilityRole="radio" accessibilityLabel={`改 ${date} 的时段`}
                                  accessibilityState={{ selected: (all.includes(shiftDay) ? shiftDay : all[0]) === date }}
                                  onPress={() => setShiftDay(date)}>
                  <Text style={styles.row}>{(all.includes(shiftDay) ? shiftDay : all[0]) === date ? '◉ ' : '○ '}{date.slice(5)}</Text>
                </TouchableOpacity>
              ))}
              <TextInput style={styles.input} accessibilityLabel="这天几点开始" placeholder="几点开始（如 10:00，都空 = 不限时段）"
                         value={shiftFrom} onChangeText={setShiftFrom} />
              <TextInput style={styles.input} accessibilityLabel="这天几点结束" placeholder="几点结束（如 16:00）"
                         value={shiftTo} onChangeText={setShiftTo} />
              <TouchableOpacity onPress={() => {
                setShiftMsg('');
                const all = shiftEditableDays(tree.by_day);
                void client.changeDayShift(task.id, all.includes(shiftDay) ? shiftDay : all[0], shiftFrom.trim(), shiftTo.trim()).then((r) => {
                  setShiftMsg(dayShiftChangeLine(r));
                  void client.taskTree(task.id).then(setTree).catch(() => {});
                }).catch((e) => setShiftMsg(apiErrorText(e)));
              }}>
                <Text style={styles.link}>改这天的时段</Text>
              </TouchableOpacity>
              {!!shiftMsg && <Text style={styles.muted}>{shiftMsg}</Text>}
            </View>
          )}
        </View>
      )}
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
  const [report, setReport] = useState<Awaited<ReturnType<PlatformClient['finalReport']>> | null>(null);
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
      {/* AGT-090 全部步骤完成后：结项报告（132 号 spec） */}
      {data.steps_total > 0 && data.steps_done === data.steps_total && (report ? (
        <View accessibilityLabel="结项报告">
          <Text style={styles.title}>结项报告</Text>
          <Text>{report.summary}</Text>
          <Text style={styles.muted}>实付（按合约放款）{fmtYuan(report.paid_cents)} · 计划 {fmtYuan(report.planned_budget_cents)}{report.duration_days !== null ? ` · 用时 ${report.duration_days} 天` : ''}</Text>
          {report.deliverables.map((d) => <Text key={d.task_id} style={styles.small}>• {d.title} · {fmtYuan(d.cost_cents)}</Text>)}
        </View>
      ) : (
        <TouchableOpacity style={styles.ghost} onPress={() => void client.finalReport(taskId).then(setReport).catch(() => setReport(null))}>
          <Text>看结项报告</Text>
        </TouchableOpacity>
      ))}
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
