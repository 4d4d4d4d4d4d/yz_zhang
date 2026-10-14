// ORC-066 / AGT-084 AI 编排（131 号 spec）——App 端：说一个目标，平台在预算上限内拆成任务发出去、看结果、不达标就整改；
// 授权后分发时用平台经验工具生成草稿，挂在步骤上等你「采用 / 丢弃」，不会替你发给任何人。
import {
  apiErrorText, fmtYuan, type Mission, type MissionEvent, type MissionStep, type PlatformClient,
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
  const [goal, setGoal] = useState('');
  const [budget, setBudget] = useState('300');
  const [tools, setTools] = useState(true);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setList(await client.myMissions());
      setDetail(openId ? await client.getMission(openId) : null);
    } catch (e) { setError(apiErrorText(e)); }
  }, [client, openId]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
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
        <Button title="建好，先不花钱" disabled={goal.trim().length < 2 || !(Number(budget) > 0)} onPress={() => void act(async () => {
          const m = await client.createMission({ goal: goal.trim(), budget_cap_cents: Math.round(Number(budget) * 100), allow_tools: tools });
          setGoal(''); setOpenId(m.id);
        }, '已建好：点「推进一轮」开始规划和分发')} />
      </View>
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
