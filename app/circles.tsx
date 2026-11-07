// APP-074e（439 号 spec）圈层：网页早就有（web/src/pages/Circles.tsx），App 一直没有。
//
// 圈层是「关系」那一层（VISION 1.1）：能力圈、地域圈里的人互相接单、发「仅圈层可见」的任务。
// 执行方多半只有手机，App 上看不到圈子、进不了圈、看不到圈内任务板，定向发到圈里的单就没人看见。
// 规则都在服务端：加入是开放还是要审核、信用分门槛、圈内动态与任务只对成员可见。
import {
  apiErrorText, CIRCLE_KIND_LABEL, circleJoinLabel, circleSummary, fmtYuan, TASK_STATUS_LABEL,
  type CircleInfo, type ContentItem, type PlatformClient, type Task,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Kind = CircleInfo['kind'];

export function CirclesScreen({ client, onOpenTask }: { client: PlatformClient; onOpenTask: (taskId: number) => void }) {
  const [circles, setCircles] = useState<CircleInfo[]>([]);
  const [active, setActive] = useState<CircleInfo | null>(null);
  const [feed, setFeed] = useState<ContentItem[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [post, setPost] = useState('');
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', kind: 'interest' as Kind, skill_tag: '', city: '', join_policy: 'open' });
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const list = await client.circles().catch(() => []);
    setCircles(Array.isArray(list) ? list : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function open(c: CircleInfo) {
    setActive(c);
    setError('');
    if (c.my_status === 'active') {
      const [f, t] = await Promise.all([client.circleFeed(c.id).catch(() => []), client.circleTasks(c.id).catch(() => [])]);
      setFeed(Array.isArray(f) ? f : []);
      setTasks(Array.isArray(t) ? t : []);
    } else {
      setFeed([]);
      setTasks([]);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try {
      await fn();
      await load();
      if (active) await open(await client.getCircle(active.id));
    } catch (e) {
      setError(apiErrorText(e));
    }
  }

  if (active) {
    const joinLabel = circleJoinLabel(active);
    return (
      <View style={s.wrap}>
        <TouchableOpacity onPress={() => { setActive(null); setError(''); }}><Text style={s.link}>‹ 全部圈层</Text></TouchableOpacity>
        <View style={s.card}>
          <Text style={s.title}>{active.name}</Text>
          <Text style={s.muted}>{circleSummary(active)}</Text>
          {joinLabel && (
            <TouchableOpacity style={s.primary} onPress={() => void act(() => client.joinCircle(active.id))}>
              <Text style={s.primaryText}>{joinLabel}</Text>
            </TouchableOpacity>
          )}
          {active.my_status === 'pending' && <Text style={s.badge}>待圈主审核</Text>}
          {active.my_role === 'owner' && <Text style={s.badge}>圈主</Text>}
          {!!error && <Text style={s.error}>{error}</Text>}
        </View>
        {active.my_status === 'active' && (
          <>
            <View style={s.card}>
              <Text style={s.title}>圈内任务板</Text>
              {tasks.length === 0 && <Text style={s.muted}>圈内暂无任务。发布任务时选「仅圈层可见」即可定向发到这里。</Text>}
              {tasks.map((t) => (
                <TouchableOpacity key={t.id} style={s.row} onPress={() => onOpenTask(t.id)}>
                  <Text style={{ flex: 1 }}>{t.title}</Text>
                  <Text style={s.muted}>{fmtYuan(t.budget_cents)} · {TASK_STATUS_LABEL[t.status] ?? t.status}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={s.card}>
              <Text style={s.title}>圈内动态</Text>
              <TextInput accessibilityLabel="发圈内帖" style={s.input} placeholder="发圈内帖…" value={post} onChangeText={setPost} />
              <TouchableOpacity style={[s.primary, !post.trim() && s.disabled]} disabled={!post.trim()}
                onPress={() => void act(async () => {
                  await client.createContent({ body: post.trim(), circle_id: active.id, visibility: 'circle' });
                  setPost('');
                })}>
                <Text style={s.primaryText}>发布</Text>
              </TouchableOpacity>
              {feed.length === 0 && <Text style={s.muted}>还没有人发帖</Text>}
              {feed.map((c) => (
                <Text key={c.id} style={s.post}><Text style={{ fontWeight: '600' }}>{c.author_nickname}</Text>：{c.body}</Text>
              ))}
            </View>
          </>
        )}
      </View>
    );
  }

  return (
    <View style={s.wrap}>
      <View style={s.card}>
        <View style={s.row}>
          <Text style={[s.title, { flex: 1 }]}>圈层</Text>
          <TouchableOpacity onPress={() => setCreating(!creating)}><Text style={s.link}>{creating ? '收起' : '＋创建'}</Text></TouchableOpacity>
        </View>
        {creating && (
          <View style={{ gap: 6 }}>
            <TextInput accessibilityLabel="圈层名称" style={s.input} placeholder="圈层名称" value={form.name}
              onChangeText={(v) => setForm({ ...form, name: v })} />
            <View style={s.row}>
              {(Object.keys(CIRCLE_KIND_LABEL) as Kind[]).map((k) => (
                <TouchableOpacity key={k} onPress={() => setForm({ ...form, kind: k })}>
                  <Text style={[s.chip, form.kind === k && s.chipOn]}>{CIRCLE_KIND_LABEL[k]}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {form.kind === 'skill' && <TextInput accessibilityLabel="绑定技能标签" style={s.input} placeholder="绑定技能标签（如：保洁）"
              value={form.skill_tag} onChangeText={(v) => setForm({ ...form, skill_tag: v })} />}
            {form.kind === 'local' && <TextInput accessibilityLabel="绑定城市" style={s.input} placeholder="绑定城市"
              value={form.city} onChangeText={(v) => setForm({ ...form, city: v })} />}
            <View style={s.row}>
              {([['open', '开放加入'], ['approval', '申请审核']] as const).map(([k, label]) => (
                <TouchableOpacity key={k} onPress={() => setForm({ ...form, join_policy: k })}>
                  <Text style={[s.chip, form.join_policy === k && s.chipOn]}>{label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity style={[s.primary, !form.name.trim() && s.disabled]} disabled={!form.name.trim()}
              onPress={() => void act(async () => {
                await client.createCircle({ ...form, name: form.name.trim() });
                setCreating(false);
                setForm({ name: '', kind: 'interest', skill_tag: '', city: '', join_policy: 'open' });
              })}>
              <Text style={s.primaryText}>创建圈层</Text>
            </TouchableOpacity>
          </View>
        )}
        {!!error && !active && <Text style={s.error}>{error}</Text>}
        {circles.length === 0 && <Text style={s.muted}>还没有圈层，可以创建一个</Text>}
        {circles.map((c) => (
          <TouchableOpacity key={c.id} style={s.row} onPress={() => void open(c)}>
            <Text style={{ flex: 1 }}>{CIRCLE_KIND_LABEL[c.kind] ?? ''} · {c.name}</Text>
            <Text style={s.muted}>{c.member_count} 人{c.my_status === 'active' ? ' · 已加入' : c.my_status === 'pending' ? ' · 待审核' : ''}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { gap: 12 },
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 16, gap: 8, borderWidth: 1, borderColor: '#dce5de' },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 13 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  link: { color: '#2563eb' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  primary: { backgroundColor: '#16a34a', borderRadius: 8, padding: 10, alignItems: 'center' },
  primaryText: { color: '#fff', fontWeight: '600' },
  disabled: { opacity: 0.5 },
  badge: { alignSelf: 'flex-start', backgroundColor: '#fef3c7', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  chip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  chipOn: { backgroundColor: '#dcfce7', borderColor: '#16a34a' },
  error: { color: '#dc2626' },
  post: { borderTopWidth: 1, borderTopColor: '#eef2ef', paddingTop: 6 },
});
