// ORC-066 / AGT-084 AI 编排（131 号 spec）——App 端：说一个目标，平台在预算上限内拆成任务发出去、看结果、不达标就整改；
// 授权后分发时用平台经验工具生成草稿，挂在步骤上等你「采用 / 丢弃」，不会替你发给任何人。
import {
  apiErrorText, fmtYuan, type Mission, type MissionEvent, type MissionMethodDraft, type MissionMethodSuggestions, type MissionStep, type MissionSummary, type PlatformClient, type NbMethod
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';

const STATUS: Record<string, string> = {
  planning: '待规划', running: '进行中', succeeded: '已达标', blocked: '卡住了', cancelled: '已取消', failed: '没完成',
};
const STEP: Record<string, string> = { pending: '待分发', dispatched: '已发布', done: '已验收', failed: '没通过', superseded: '已被整改替代' };
const DRAFT: Record<string, string> = { pending: '待你确认', adopted: '已采用', discarded: '已丢弃' };
type Detail = Mission & { steps: MissionStep[]; timeline: MissionEvent[] };
const ENDED = ['succeeded', 'cancelled', 'failed'];

export function MissionsScreen({ client }: { client: PlatformClient }) {
  const [list, setList] = useState<Mission[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [summary, setSummary] = useState<MissionSummary | null>(null);
  // AGT-093 复盘蒸馏出的方法草稿（154 号 spec）
  const [draft, setDraft] = useState<MissionMethodDraft | null>(null);
  const [goal, setGoal] = useState('');
  const [budget, setBudget] = useState('300');
  const [tools, setTools] = useState(true);
  // AGT-094（164 号 spec）第一轮可以按自己的「我的方法」拆
  const [methods, setMethods] = useState<NbMethod[]>([]);
  const [methodId, setMethodId] = useState<number | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setList(await client.myMissions());
      setDetail(openId ? await client.getMission(openId) : null);
      setSummary(openId ? await client.missionSummary(openId).catch(() => null) : null);
    } catch (e) { setError(apiErrorText(e)); }
  }, [client, openId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { client.notebookMethods().then(setMethods).catch(() => setMethods([])); }, [client]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); if (done) setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }

  if (detail) {
    const d = detail;
    return (
      <View style={s.box} accessibilityLabel="编排详情">
        <TouchableOpacity onPress={() => setOpenId(null)}><Text style={s.link}>← 全部编排</Text></TouchableOpacity>
        <Text style={s.title}>{d.goal}</Text>
        <Text style={s.muted}>{STATUS[d.status] ?? d.status} · 第 {d.iteration}/{d.max_iterations} 轮 · 完成 {d.completion_pct}%</Text>
        <Text style={s.muted}>预算：已付 {fmtYuan(d.spent_cents)}，占用 {fmtYuan(d.committed_cents)}，上限 {fmtYuan(d.budget_cap_cents)}</Text>
        {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
        {!!error && <Text style={s.error}>{error}</Text>}
        <View style={s.row}>
          <Switch accessibilityLabel="允许用经验工具生成草稿" value={d.allow_tools}
            onValueChange={(v) => void act(() => client.setMissionTools(d.id, v), v ? '已授权：之后分发的步骤会用经验工具生成草稿' : '已收回授权')} />
          <Text style={{ flex: 1 }}>允许用平台经验工具生成草稿（只出草稿，等你确认）</Text>
        </View>
        <Button title="推进一轮" disabled={ENDED.includes(d.status)} onPress={() => void act(() => client.tickMission(d.id), '已推进一轮')} />
        <Button title="取消编排" disabled={ENDED.includes(d.status)} onPress={() => Alert.alert('取消编排', '还没人接的任务会关闭，已经在做的照常结算。', [
          { text: '不取消', style: 'cancel' },
          { text: '取消', style: 'destructive', onPress: () => void act(() => client.cancelMission(d.id), '已取消') },
        ])} />
        {summary && Array.isArray(summary.highlights) && (
          <View style={s.card} accessibilityLabel="复盘">
            <Text style={s.title}>复盘</Text>
            <Text style={s.muted}>{summary.rounds}/{summary.max_rounds} 轮 · 完成 {summary.steps_done}/{summary.steps_total} 步 · 整改 {summary.remedies} 次 · 实付 {fmtYuan(summary.spent_cents)}</Text>
            {summary.highlights.map((h) => <Text key={h}>• {h}</Text>)}
            <Text>下一步：{summary.next}</Text>
            <Button title="存进我的知识库" onPress={() => void act(async () => {
              const r = await client.saveMissionSummary(d.id);
              setNotice(r.created ? `已存进你的知识库：「${r.title}」` : `已更新知识库里的「${r.title}」`);
            }, '')} />
            <Button title="蒸馏成我的方法" onPress={() => void act(async () => { setDraft(await client.distillMissionMethod(d.id)); }, '')} />
            {/* AGT-100（251 号 spec）按方法拆的编排：整改过的步骤起草成方法备注的修改建议 */}
            {!!d.method_id && <MethodSuggestionsBlock client={client} missionId={d.id} />}
            {draft && (
              <View style={s.card} accessibilityLabel="方法草稿">
                {draft.steps.length === 0
                  ? <Text style={s.muted}>还没有做成的步骤，等有步骤完成后再蒸馏。复盘已存进知识库。</Text>
                  : (<>
                      <Text>{draft.name}（{draft.steps.length} 步{draft.skipped_steps ? `；${draft.skipped_steps} 步没做成，没收进来` : ''}）</Text>
                      {draft.steps.map((x, i) => <Text key={x.title}>{i + 1}. {x.title}{x.note ? `：${x.note}` : ''}</Text>)}
                      <Button title="保存为我的方法" onPress={() => void act(async () => {
                        await client.createMethod({ name: draft.name, steps: draft.steps, source_note_ids: draft.source_note_ids });
                        setDraft(null);
                      }, '已保存为你的方法，在「我的知识库 → 我的方法」里可以修改和套用')} />
                    </>)}
              </View>
            )}
          </View>
        )}
        {d.steps.map((st) => (
          <View key={st.id} style={s.card} accessibilityLabel={`步骤：${st.title}`}>
            <Text>{st.title} · {STEP[st.status] ?? st.status}{st.budget_cents ? ` · ${fmtYuan(st.budget_cents)}` : ''}</Text>
            {!!st.observation && <Text style={s.muted}>{st.observation}</Text>}
            {st.tool_drafts.map((dr) => (
              <View key={dr.invocation_id} style={s.card} accessibilityLabel="经验工具草稿">
                <Text style={s.muted}>{dr.label} · {DRAFT[dr.status]}</Text>
                <Text>{dr.text}</Text>
                {dr.status === 'pending' && (
                  <View style={s.row}>
                    <Button title="采用" onPress={() => void act(() => client.adoptMissionDraft(d.id, st.id, dr.invocation_id), '已采用（只是标记，没有发给任何人）')} />
                    <Button title="丢弃" onPress={() => void act(() => client.discardMissionDraft(d.id, st.id, dr.invocation_id), '已丢弃')} />
                  </View>
                )}
              </View>
            ))}
          </View>
        ))}
        {d.timeline.slice(-5).map((e, n) => <Text key={n} style={s.muted}>第 {e.iteration} 轮：{e.summary}</Text>)}
      </View>
    );
  }

  return (
    <View style={s.box}>
      <Text style={s.muted}>说一个目标，平台在你给的预算上限内把它拆成任务发出去，看结果、不达标就整改。每一步都看得见。</Text>
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {list.length === 0 && <Text style={s.muted}>还没有编排。</Text>}
      {list.map((m) => (
        <TouchableOpacity key={m.id} style={s.card} onPress={() => setOpenId(m.id)}>
          <Text>{m.goal}</Text>
          <Text style={s.muted}>{STATUS[m.status] ?? m.status} · 完成 {m.completion_pct}% · 上限 {fmtYuan(m.budget_cap_cents)}</Text>
        </TouchableOpacity>
      ))}
      <View style={s.card} accessibilityLabel="新的编排">
        <TextInput style={s.input} accessibilityLabel="目标" placeholder="目标，例如：周六搬家（打包、搬运、保洁）" value={goal} onChangeText={setGoal} />
        <TextInput style={s.input} accessibilityLabel="预算上限" keyboardType="numeric" value={budget} onChangeText={setBudget} />
        <View style={s.row}>
          <Switch accessibilityLabel="新编排用经验工具" value={tools} onValueChange={setTools} />
          <Text style={{ flex: 1 }}>允许用平台经验工具生成草稿（只出草稿，等你确认）</Text>
        </View>
        {methods.length > 0 && <Text>第一轮怎么拆：{methodId ? `按我的方法「${methods.find((x) => x.id === methodId)?.name ?? ''}」` : '让 AI 拆'}</Text>}
        {methods.map((x) => (
          <Button key={x.id} title={methodId === x.id ? `不用「${x.name}」了` : `按「${x.name}」拆（${x.steps.length} 步）`}
                  onPress={() => setMethodId(methodId === x.id ? null : x.id)} />
        ))}
        <Button title="建好，先不花钱" disabled={goal.trim().length < 2 || !(Number(budget) > 0)} onPress={() => void act(async () => {
          const m = await client.createMission({ goal: goal.trim(), budget_cap_cents: Math.round(Number(budget) * 100), allow_tools: tools,
            ...(methodId ? { method_id: methodId } : {}) });
          setGoal(''); setOpenId(m.id);
        }, '已建好：点「推进一轮」开始规划和分发')} />
      </View>
    </View>
  );
}

/** AGT-100（251 号 spec）方法备注的修改建议：只出草稿，勾选后才写回方法 */
function MethodSuggestionsBlock({ client, missionId }: { client: PlatformClient; missionId: number }) {
  const [sg, setSg] = useState<MissionMethodSuggestions | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [msg, setMsg] = useState('');
  if (!sg) {
    return (
      <View>
        {!!msg && <Text>{msg}</Text>}
        <Button title="用这次的问题改进我的方法" onPress={() => void client.missionMethodSuggestions(missionId)
          .then((r) => { setSg(r); setPicked(Array.isArray(r.suggestions) ? r.suggestions.map((x) => x.title) : []); }, (e) => setMsg(apiErrorText(e)))} />
      </View>
    );
  }
  const items = Array.isArray(sg.suggestions) ? sg.suggestions : [];
  return (
    <View style={s.card} accessibilityLabel="方法改进建议">
      {items.length === 0 ? <Text style={s.muted}>{sg.note}</Text> : null}
      {items.map((x) => (
        <View key={x.title}>
          <Button title={`${picked.includes(x.title) ? '☑' : '☐'} ${x.title}（${x.reason}）`}
                  onPress={() => setPicked(picked.includes(x.title) ? picked.filter((t) => t !== x.title) : [...picked, x.title])} />
          <Text style={s.muted}>{x.current_note || '（原来没有备注）'} → {x.suggested_note}</Text>
        </View>
      ))}
      {items.length > 0 && <Button title="写回我的方法" disabled={!picked.length} onPress={() => void client.applyMissionMethodSuggestions(missionId, picked)
        .then((m) => { setMsg(`已写回「${m.name}」，现在是第 ${m.version} 版`); setSg(null); }, (e) => setMsg(apiErrorText(e)))} />}
      {!!msg && <Text>{msg}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4, alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#777' },
  link: { color: '#2563eb' },
  error: { color: '#b91c1c' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
});
