// PWB 个人工作台（116 号 spec）：我的任务、进度与助手——App 端。
//
// 个人门户不只对外展示，也要能管自己的事。手机上这一页最常用的是：
// 看今天要做什么、勾掉一项清单、记一笔进展、让助手把一件事拆开。
import {
  apiErrorText, formatDateTime, millisUntil,
  type PlatformClient, type WbItem, type WbItemDetail, type WbLog, type WbMemory, type WbOverview,
  type WbRoutine, type WbRoutineHealth, type WbRunStatus, type WbStatus, type WbStep, type NbMethod, type NbReference,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

// REL-101 新建的例行任务默认带运行合同：失败重试 2 次（1 分钟、5 分钟后），用尽时降级交付（130 号 spec）
const CONTRACT = { max_retries: 2, degrade: true, timeout_ms: 10000 };
const RUN_STATUS: Record<WbRunStatus, string> = { ok: '成功', failed: '失败', retrying: '失败，等待重试', skipped: '跳过（数据没就绪）', degraded: '降级送达' };

const STATUS: [WbStatus, string][] = [['todo', '待办'], ['doing', '进行中'], ['blocked', '卡住'], ['done', '完成']];
const SOURCE: Record<string, string> = { manual: '手填', children: '按清单', platform: '跟平台任务' };
type Tab = 'today' | 'all' | 'assistant';

export function WorkbenchScreen({ client }: { client: PlatformClient }) {
  const [tab, setTab] = useState<Tab>('today');
  const [openId, setOpenId] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  if (openId) {
    return <ItemDetail client={client} id={openId} onBack={() => { setOpenId(null); refresh(); }} />;
  }
  return (
    <View style={s.box}>
      <View style={s.row}>
        {([['today', '今天'], ['all', '全部'], ['assistant', '助手']] as [Tab, string][]).map(([t, label]) => (
          <TouchableOpacity key={t} onPress={() => setTab(t)} accessibilityRole="tab" accessibilityState={{ selected: tab === t }}>
            <Text style={tab === t ? s.tabOn : s.tab}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {tab !== 'assistant' && <QuickAdd client={client} onAdded={refresh} />}
      {tab === 'today' && <Today client={client} version={version} open={setOpenId} />}
      {tab === 'all' && <AllItems client={client} version={version} open={setOpenId} />}
      {tab === 'assistant' && <Assistant client={client} />}
    </View>
  );
}

function QuickAdd({ client, onAdded }: { client: PlatformClient; onAdded: () => void }) {
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  async function add() {
    if (!title.trim()) return;
    setError('');
    try { await client.createWorkbenchItem({ title }); setTitle(''); onAdded(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.row}>
      <TextInput style={[s.input, { flex: 1 }]} placeholder="要做的事" value={title} onChangeText={setTitle} onSubmitEditing={() => void add()} />
      <Button title="添加" onPress={() => void add()} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

function Row({ item, open }: { item: WbItem; open: (id: number) => void }) {
  const overdue = !!item.due_at && item.status !== 'done' && millisUntil(item.due_at) < 0;
  return (
    <TouchableOpacity onPress={() => open(item.id)} style={s.card}>
      <Text style={s.itemTitle}>{item.title}</Text>
      <Text style={overdue ? s.error : s.muted}>
        {item.status_name}{item.due_at ? ` · ${overdue ? '已逾期 ' : '截止 '}${formatDateTime(item.due_at)}` : ''}
        {item.children_total ? ` · 清单 ${item.children_done}/${item.children_total}` : ''} · {item.progress}%
      </Text>
    </TouchableOpacity>
  );
}

function Today({ client, version, open }: { client: PlatformClient; version: number; open: (id: number) => void }) {
  const [ov, setOv] = useState<WbOverview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { client.workbenchOverview().then(setOv).catch((e) => setError(apiErrorText(e))); }, [client, version]);
  if (error) return <Text style={s.error}>{error}</Text>;
  if (!ov) return <Text style={s.muted}>正在加载…</Text>;
  const p = ov.platform;
  const sections: [string, WbItem[]][] = [['已逾期', ov.overdue], ['今天到期', ov.today], ['进行中', ov.doing], ['卡住了', ov.blocked]];
  return (
    <View style={s.box}>
      <Text style={s.summary}>{ov.summary}</Text>
      {p.to_choose.map((t) => <Text key={`c${t.task_id}`} style={s.muted}>平台：「{t.title}」{t.applicants} 人报名，等你选人</Text>)}
      {p.to_accept.map((t) => <Text key={`a${t.task_id}`} style={s.muted}>平台：「{t.title}」等你验收</Text>)}
      {p.executing.map((t) => <Text key={`e${t.task_id}`} style={s.muted}>平台：我在执行「{t.title}」（{t.status_name}）</Text>)}
      {sections.filter(([, rows]) => rows.length).map(([label, rows]) => (
        <View key={label} style={s.box}>
          <Text style={s.h}>{label}（{rows.length}）</Text>
          {rows.map((i) => <Row key={i.id} item={i} open={open} />)}
        </View>
      ))}
      {ov.counts.open === 0 && <Text style={s.muted}>手上没有未完成的事。</Text>}
    </View>
  );
}

function AllItems({ client, version, open }: { client: PlatformClient; version: number; open: (id: number) => void }) {
  const [items, setItems] = useState<WbItem[]>([]);
  const [q, setQ] = useState('');
  useEffect(() => { client.workbenchItems({ q: q || undefined }).then(setItems).catch(() => setItems([])); }, [client, version, q]);
  return (
    <View style={s.box}>
      <TextInput style={s.input} placeholder="搜索我的任务" value={q} onChangeText={setQ} />
      {items.map((i) => <Row key={i.id} item={i} open={open} />)}
      {!items.length && <Text style={s.muted}>还没有任务。</Text>}
    </View>
  );
}

function ItemDetail({ client, id, onBack }: { client: PlatformClient; id: number; onBack: () => void }) {
  const [item, setItem] = useState<WbItemDetail | null>(null);
  const [logs, setLogs] = useState<WbLog[]>([]);
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState<WbStep[] | null>(null);
  const [refs, setRefs] = useState<NbReference[]>([]);
  const [methods, setMethods] = useState<NbMethod[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setItem(await client.workbenchItem(id)); setLogs(await client.workbenchLogs(id)); } catch (e) { setError(apiErrorText(e)); }
  }, [client, id]);
  useEffect(() => { void load(); }, [load]);
  // KB-104 相关笔记与我的方法：拿不到不影响任务本身
  useEffect(() => {
    client.relatedNotes(id).then(setRefs).catch(() => setRefs([]));
    client.notebookMethods().then(setMethods).catch(() => setMethods([]));
  }, [client, id]);
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  if (!item) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  return (
    <View style={s.box}>
      <TouchableOpacity onPress={onBack}><Text style={s.link}>← 返回工作台</Text></TouchableOpacity>
      <Text style={s.h}>{item.title}</Text>
      <Text style={s.muted}>进度 {item.progress}%（{SOURCE[item.progress_source]}）{item.linked_task ? ` · 平台任务：${item.linked_task.status_name}` : ''}</Text>
      <View style={s.row}>
        {STATUS.map(([st, label]) => (
          <TouchableOpacity key={st} onPress={() => void act(() => client.updateWorkbenchItem(item.id, { status: st, revision: item.revision }))}
            accessibilityState={{ selected: item.status === st }}>
            <Text style={item.status === st ? s.tabOn : s.tab}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {item.progress_source === 'manual' && item.status !== 'done' && (
        <View style={s.row}>
          {[25, 50, 75].map((n) => (
            <TouchableOpacity key={n} onPress={() => void act(() => client.updateWorkbenchItem(item.id, { progress: n, revision: item.revision }))}>
              <Text style={s.tab}>进度 {n}%</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      <Text style={s.h}>清单</Text>
      {item.children.map((c) => (
        <TouchableOpacity key={c.id} accessibilityRole="checkbox" accessibilityState={{ checked: c.status === 'done' }}
          onPress={() => void act(() => client.updateWorkbenchItem(c.id, { status: c.status === 'done' ? 'todo' : 'done' }))}>
          <Text>{c.status === 'done' ? '☑' : '☐'} {c.title}</Text>
        </TouchableOpacity>
      ))}
      <Button title="让助手拆一下" onPress={() => void act(async () => {
        const res = await client.workbenchBreakdown(item.id);
        setDraft(res.steps);
        if (res.references?.length) setRefs(res.references);
      })} />
      {item.parent_id === null && methods.map((m) => (
        <TouchableOpacity key={m.id} onPress={() => void act(() => client.applyMethod(m.id, item.id))}>
          <Text style={s.link}>套用我的方法：{m.name}（{m.steps.length} 步）</Text>
        </TouchableOpacity>
      ))}
      {refs.length > 0 && (
        <View style={s.card}>
          <Text style={s.muted}>你以前记过的相关内容：</Text>
          {refs.map((r) => <Text key={r.note_id}>· {r.title}：{r.snippet}</Text>)}
        </View>
      )}
      {draft && (
        <View style={s.card}>
          <Text style={s.muted}>助手给的草稿，确认后才会加进清单</Text>
          {draft.map((st, n) => (
            <View key={n} style={s.row}>
              <Text style={{ flex: 1 }}>{st.title}</Text>
              <TouchableOpacity onPress={() => setDraft(draft.filter((_, k) => k !== n))}><Text style={s.link}>去掉</Text></TouchableOpacity>
            </View>
          ))}
          <Button title="确认加入清单" disabled={!draft.length}
            onPress={() => void act(async () => { await client.addWorkbenchChildren(item.id, draft); setDraft(null); })} />
        </View>
      )}
      <Text style={s.h}>进展记录</Text>
      <View style={s.row}>
        <TextInput style={[s.input, { flex: 1 }]} placeholder="今天做到哪了？" value={note} onChangeText={setNote} />
        <Button title="记一笔" onPress={() => note.trim() && void act(async () => { await client.addWorkbenchLog(item.id, note); setNote(''); })} />
      </View>
      {logs.map((g) => <Text key={g.id} style={s.muted}>{formatDateTime(g.created_at)} {g.body}</Text>)}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

function Assistant({ client }: { client: PlatformClient }) {
  const [mem, setMem] = useState<WbMemory[]>([]);
  const [routines, setRoutines] = useState<WbRoutine[]>([]);
  const [health, setHealth] = useState<Record<number, WbRoutineHealth>>({});
  const [content, setContent] = useState('');
  const [time, setTime] = useState('08:30');
  const [output, setOutput] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setMem((await client.workbenchMemories()).items); setRoutines(await client.workbenchRoutines()); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.box}>
      <Text style={s.h}>助手记得的事（{mem.length}/20）</Text>
      {mem.map((m) => (
        <View key={m.id} style={s.row}>
          <Text style={{ flex: 1 }}>{m.content}</Text>
          <TouchableOpacity onPress={() => void act(() => client.deleteWorkbenchMemory(m.id))}><Text style={s.link}>忘掉</Text></TouchableOpacity>
        </View>
      ))}
      <View style={s.row}>
        <TextInput style={[s.input, { flex: 1 }]} placeholder="让助手记住一件事" maxLength={200} value={content} onChangeText={setContent} />
        <Button title="记住" onPress={() => content.trim() && void act(async () => { await client.addWorkbenchMemory(content); setContent(''); })} />
      </View>
      <Text style={s.h}>例行任务</Text>
      <Text style={s.muted}>到点由平台运行，结果发到通知里，不用开着 App。连续失败 3 次会自动暂停。</Text>
      {routines.map((r) => (
        <View key={r.id} style={s.card}>
          <Text>{r.name} · {r.enabled ? `下次 ${formatDateTime(r.next_run_at)}` : '已暂停'}{r.last_status === 'failed' ? ' · 上次失败' : ''}
            {r.last_status && r.last_status !== 'failed' && r.last_status !== 'ok' ? ` · 上次${RUN_STATUS[r.last_status]}` : ''}</Text>
          <Text style={s.muted}>失败重试 {r.max_retries} 次{r.degrade ? '，用尽后降级交付' : ''}</Text>
          {health[r.id] && (
            <Text style={s.muted} accessibilityLabel={`健康度：${r.name}`}>最近 {health[r.id].runs} 次：成功率 {health[r.id].success_rate === null ? '—' : `${Math.round(health[r.id].success_rate! * 100)}%`} · 降级 {health[r.id].degraded} · 重试 {health[r.id].retries} · 跳过 {health[r.id].skipped}</Text>
          )}
          <View style={s.row}>
            <TouchableOpacity onPress={() => void act(async () => setOutput((await client.runWorkbenchRoutine(r.id)).output))}><Text style={s.link}>现在运行</Text></TouchableOpacity>
            <TouchableOpacity onPress={() => void act(() => client.updateWorkbenchRoutine(r.id, { enabled: !r.enabled }))}><Text style={s.link}>{r.enabled ? '暂停' : '开启'}</Text></TouchableOpacity>
            <TouchableOpacity onPress={() => void client.workbenchRoutineHealth(r.id).then((x) => setHealth((h) => ({ ...h, [r.id]: x }))).catch((e) => setError(apiErrorText(e)))}><Text style={s.link}>健康度</Text></TouchableOpacity>
            <TouchableOpacity onPress={() => void act(() => client.deleteWorkbenchRoutine(r.id))}><Text style={s.link}>删除</Text></TouchableOpacity>
          </View>
        </View>
      ))}
      {!!output && <Text style={s.summary}>{output}</Text>}
      <View style={s.row}>
        <TextInput style={[s.input, { width: 80 }]} placeholder="08:30" value={time} onChangeText={setTime} accessibilityLabel="几点" />
        <Button title="每天早上的概览" onPress={() => void act(() => client.createWorkbenchRoutine({ name: '每天早上的概览', kind: 'digest', freq: 'daily', time_of_day: time, ...CONTRACT }))} />
      </View>
      <Button title="每周五回顾" onPress={() => void act(() => client.createWorkbenchRoutine({ name: '每周五回顾', kind: 'review', freq: 'weekly', weekday: 4, time_of_day: '18:00', ...CONTRACT }))} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  tab: { paddingVertical: 6, paddingHorizontal: 10, color: '#666' },
  tabOn: { paddingVertical: 6, paddingHorizontal: 10, color: '#b5532f', fontWeight: '600' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 8 },
  card: { borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4 },
  itemTitle: { fontSize: 15, fontWeight: '600' },
  h: { fontSize: 16, fontWeight: '600', marginTop: 6 },
  summary: { fontSize: 14, lineHeight: 20 },
  muted: { color: '#777' },
  error: { color: '#c0392b' },
  link: { color: '#b5532f' },
});
