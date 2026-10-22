// KB-100 个人知识库（122 号 spec）——App 端。
//
// 手机上最常用的是：随手记一句、粘一个链接、会后把纪要里的待办抽进工作台、问一句「我以前记过什么」。
import {
  apiErrorText, fmtYuan, formatDateTime, methodVersionCompare, methodVersionLines,
  type NbAnswer, type NbMethod, type NbMethodDraft, type NbNote, type NbNoteBrief, type NbSummary, type NbTodoDraft, type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Tab = 'inbox' | 'all' | 'methods' | 'ask';
const KIND: Record<string, string> = { note: '笔记', link: '链接', minutes: '纪要' };

export function NotebookScreen({ client }: { client: PlatformClient }) {
  const [tab, setTab] = useState<Tab>('inbox');
  const [openId, setOpenId] = useState<number | null>(null);
  const [summary, setSummary] = useState<NbSummary | null>(null);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => { client.notebookSummary().then(setSummary).catch(() => setSummary(null)); }, [client, version]);

  if (openId) return <NoteDetail client={client} id={openId} onBack={() => { setOpenId(null); refresh(); }} />;
  return (
    <View style={s.box}>
      <Text style={s.muted}>只有你自己看得到：不公开、不进搜索、不进推荐。</Text>
      <View style={s.row}>
        {([['inbox', `收件箱${summary ? `（${summary.inbox}）` : ''}`], ['all', '全部'], ['methods', '我的方法'], ['ask', '问笔记']] as [Tab, string][]).map(([t, label]) => (
          <TouchableOpacity key={t} onPress={() => setTab(t)} accessibilityRole="tab" accessibilityState={{ selected: tab === t }}>
            <Text style={tab === t ? s.tabOn : s.tab}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {(tab === 'inbox' || tab === 'all') && <Capture client={client} onAdded={refresh} />}
      {(tab === 'inbox' || tab === 'all') && <Notes client={client} inbox={tab === 'inbox'} version={version} open={setOpenId}
        onDistilled={() => { refresh(); setTab('methods'); }} />}
      {tab === 'methods' && <Methods client={client} />}
      {tab === 'ask' && <Ask client={client} open={setOpenId} />}
    </View>
  );
}

function Capture({ client, onAdded }: { client: PlatformClient; onAdded: () => void }) {
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  async function save() {
    if (!body.trim()) return;
    setError('');
    try { await client.createNote({ body }); setBody(''); onAdded(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.box}>
      <TextInput style={[s.input, { minHeight: 60 }]} multiline placeholder="一句话、一段纪要，或者粘贴一个链接" value={body} onChangeText={setBody} />
      <Button title="记下" onPress={() => void save()} disabled={!body.trim()} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

function Notes({ client, inbox, version, open, onDistilled }: {
  client: PlatformClient; inbox: boolean; version: number; open: (id: number) => void; onDistilled: () => void;
}) {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<NbNoteBrief[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [draft, setDraft] = useState<NbMethodDraft | null>(null);
  const [error, setError] = useState('');
  async function distill() {
    setError('');
    try { setDraft(await client.distillMethod(picked)); } catch (e) { setError(apiErrorText(e)); }
  }
  async function save() {
    if (!draft) return;
    try {
      await client.createMethod({ name: draft.name, steps: draft.steps, source_note_ids: draft.source_note_ids });
      setDraft(null); setPicked([]); onDistilled();
    } catch (e) { setError(apiErrorText(e)); }
  }
  useEffect(() => {
    client.notebookNotes({ q, status: inbox ? 'inbox' : undefined }).then(setRows).catch((e) => setError(apiErrorText(e)));
  }, [client, q, inbox, version]);
  return (
    <View style={s.box}>
      <TextInput style={s.input} placeholder="搜索标题、正文、标签" value={q} onChangeText={setQ} />
      {!!error && <Text style={s.error}>{error}</Text>}
      {picked.length > 0 && <Button title={`把选中的 ${picked.length} 条蒸馏成方法`} onPress={() => void distill()} />}
      {draft && (
        <View style={s.card}>
          <Text style={s.muted}>{draft.found === 'none' ? '这几条笔记里没找到步骤列表（编号或圆点）' : '收出来的步骤草稿，确认后才会保存'}</Text>
          <Text style={s.itemTitle}>{draft.name}</Text>
          {draft.steps.map((st, n) => (
            <View key={n} style={s.row}>
              <Text style={{ flex: 1 }}>{n + 1}. {st.title}</Text>
              <TouchableOpacity onPress={() => setDraft({ ...draft, steps: draft.steps.filter((_, k) => k !== n) })}><Text style={s.link}>去掉</Text></TouchableOpacity>
            </View>
          ))}
          <Button title="保存为我的方法" disabled={!draft.steps.length} onPress={() => void save()} />
        </View>
      )}
      {!rows.length && <Text style={s.muted}>{inbox ? '收件箱是空的。' : '还没有笔记。'}</Text>}
      {rows.map((n) => (
        <TouchableOpacity key={n.id} style={s.card} onPress={() => open(n.id)}>
          <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: picked.includes(n.id) }}
            onPress={() => setPicked(picked.includes(n.id) ? picked.filter((x) => x !== n.id) : [...picked, n.id])}>
            <Text style={s.link}>{picked.includes(n.id) ? '☑ 已选' : '☐ 选中'}</Text>
          </TouchableOpacity>
          <Text style={s.itemTitle}>{n.pinned ? '📌 ' : ''}{n.title}</Text>
          <Text style={s.muted}>{KIND[n.kind]}{n.tags.length ? ` · ${n.tags.map((t) => `#${t}`).join(' ')}` : ''} · {formatDateTime(n.updated_at)}</Text>
          {!!n.excerpt && <Text style={s.muted}>{n.excerpt}</Text>}
        </TouchableOpacity>
      ))}
    </View>
  );
}

function NoteDetail({ client, id, onBack }: { client: PlatformClient; id: number; onBack: () => void }) {
  const [note, setNote] = useState<NbNote | null>(null);
  const [todos, setTodos] = useState<(NbTodoDraft & { keep: boolean })[] | null>(null);
  const [tags, setTags] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    client.note(id).then((n) => { setNote(n); setTags(n.tags.join(' ')); }).catch((e) => setError(apiErrorText(e)));
  }, [client, id]);
  async function patch(p: Parameters<PlatformClient['updateNote']>[1]) {
    if (!note) return;
    setError('');
    try { setNote(await client.updateNote(note.id, { ...p, revision: note.revision })); } catch (e) { setError(apiErrorText(e)); }
  }
  async function extract() {
    if (!note) return;
    setError(''); setNotice('');
    try { setTodos((await client.extractNoteTodos(note.id)).items.map((t) => ({ ...t, keep: true }))); } catch (e) { setError(apiErrorText(e)); }
  }
  async function confirmTodos() {
    if (!note || !todos) return;
    try {
      const made = await client.addNoteTodos(note.id, todos.filter((t) => t.keep).map((t) => ({ title: t.title, due_at: t.due_at })));
      setTodos(null); setNotice(`已放进工作台 ${made.length} 项`);
    } catch (e) { setError(apiErrorText(e)); }
  }
  if (!note) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  return (
    <View style={s.box}>
      <TouchableOpacity onPress={onBack}><Text style={s.link}>← 返回知识库</Text></TouchableOpacity>
      <Text style={s.h}>{note.title}</Text>
      {!!note.url && <Text style={s.link}>{note.url}</Text>}
      <Text>{note.body}</Text>
      <Text style={s.muted}>{KIND[note.kind]} · 记于 {formatDateTime(note.created_at)}</Text>
      <View style={s.row}>
        <TextInput style={[s.input, { flex: 1 }]} placeholder="标签（空格分开）" value={tags} onChangeText={setTags} accessibilityLabel="编辑标签" />
        <Button title="保存标签" onPress={() => void patch({ tags: tags.split(/[\s,，]+/).filter(Boolean) })} />
      </View>
      <View style={s.row}>
        {note.status !== 'archived'
          ? <Button title="归档" onPress={() => void patch({ status: 'archived' })} />
          : <Button title="取消归档" onPress={() => void patch({ status: 'filed' })} />}
        <Button title={note.pinned ? '取消置顶' : '置顶'} onPress={() => void patch({ pinned: !note.pinned })} />
        <Button title="抽出待办" onPress={() => void extract()} />
        <Button title="删除" color="#c0392b" onPress={() => void client.deleteNote(note.id).then(onBack).catch((e) => setError(apiErrorText(e)))} />
      </View>
      {todos && (
        <View style={s.card}>
          {!todos.length ? <Text style={s.muted}>没找到待办。写成「- [ ] 事情」「待办：事情」就能认出来。</Text> : (
            <>
              <Text style={s.muted}>助手认出的待办，确认后才会放进工作台</Text>
              {todos.map((t, n) => (
                <TouchableOpacity key={n} accessibilityRole="checkbox" accessibilityState={{ checked: t.keep }}
                  onPress={() => setTodos(todos.map((x, k) => (k === n ? { ...x, keep: !x.keep } : x)))}>
                  <Text>{t.keep ? '☑' : '☐'} {t.title}{t.due_at ? `（截止 ${formatDateTime(t.due_at)}）` : ''}</Text>
                </TouchableOpacity>
              ))}
              <Button title="放进工作台" disabled={!todos.some((t) => t.keep)} onPress={() => void confirmTodos()} />
            </>
          )}
        </View>
      )}
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

function Methods({ client }: { client: PlatformClient }) {
  const [rows, setRows] = useState<NbMethod[]>([]);
  const [error, setError] = useState('');
  useEffect(() => { client.notebookMethods().then(setRows).catch((e) => setError(apiErrorText(e))); }, [client]);
  return (
    <View style={s.box}>
      <Text style={s.muted}>从笔记里蒸馏出来、可以反复套用的步骤。在工作台任务里点「套用我的方法」，步骤就变成清单。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {!rows.length && <Text style={s.muted}>还没有方法。在笔记列表里选中几条写着步骤的笔记，点「蒸馏成方法」。</Text>}
      {rows.map((m) => (
        <View key={m.id} style={s.card}>
          <Text style={s.itemTitle}>{m.name}（用过 {m.uses} 次）</Text>
          {/* AGT-095（168 号 spec）按它拆过的编排做得怎么样 */}
          {m.missions_total > 0 && (
            <Text style={s.muted}>
              编排用过 {m.missions_total} 次：做成 {m.missions_succeeded}、没成 {m.missions_failed}，花了 {fmtYuan(m.missions_spent_cents)}；
              {m.success_rate === null ? '做完的还少，先不算成功率' : `成功率 ${Math.round(m.success_rate * 100)}%`}
            </Text>
          )}
          {/* AGT-097（239 号 spec）改过步骤的方法按版本分开看效果 */}
          {!!methodVersionCompare(m) && <Text>{methodVersionCompare(m)}</Text>}
          {methodVersionLines(m).map((l) => <Text key={l} style={s.muted}>{l}</Text>)}
          {m.steps.map((st, n) => <Text key={n}>{n + 1}. {st.title}{st.note ? ` · ${st.note}` : ''}</Text>)}
        </View>
      ))}
    </View>
  );
}

function Ask({ client, open }: { client: PlatformClient; open: (id: number) => void }) {
  const [q, setQ] = useState('');
  const [ans, setAns] = useState<NbAnswer | null>(null);
  const [error, setError] = useState('');
  async function ask() {
    if (!q.trim()) return;
    setError('');
    try { setAns(await client.askNotebook(q)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.box}>
      <TextInput style={s.input} placeholder="比如：给企业开专票要什么？" value={q} onChangeText={setQ} onSubmitEditing={() => void ask()} />
      <Button title="问" onPress={() => void ask()} />
      {!!error && <Text style={s.error}>{error}</Text>}
      {ans && (!ans.citations.length ? <Text>{ans.answer}</Text> : (
        <View style={s.box}>
          <Text style={s.muted}>只从你自己的笔记里摘录，每条都标了出处</Text>
          {ans.citations.map((c) => (
            <TouchableOpacity key={c.n} onPress={() => open(c.note_id)}>
              <Text><Text style={s.link}>[{c.n}] {c.title}</Text>：{c.snippet}</Text>
            </TouchableOpacity>
          ))}
        </View>
      ))}
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
  muted: { color: '#777' },
  error: { color: '#c0392b' },
  link: { color: '#b5532f' },
});
