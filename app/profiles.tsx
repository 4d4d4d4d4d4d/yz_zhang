// PROF-100 任务画像与能力画像（126 号 spec）——App 端：发布时边写边提示、我的能力画像。
import {
  hasLists, MALFORMED_TEXT,
  apiErrorText, fmtYuan, type CapabilityProfile, type PlatformClient, type SkillNormalized, type TaskDraftInput, type TaskProfile,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

const POSITION: Record<string, string> = {
  below_min: '低于近期同类最低成交价', below_median: '低于同类成交中位', around_median: '与同类成交中位相当',
  above_median: '高于同类成交中位', unknown: '同类成交数据不足',
};

/** 停下半秒再算，不每个字都请求；取不到就不显示（不挡发布）。 */
export function DraftHints({ client, draft, delayMs = 500 }: { client: PlatformClient; draft: TaskDraftInput; delayMs?: number }) {
  const [p, setP] = useState<TaskProfile | null>(null);
  const key = JSON.stringify(draft);
  useEffect(() => {
    const timer = setTimeout(() => {
      Promise.resolve().then(() => client.taskDraftProfile(JSON.parse(key) as TaskDraftInput))
        .then((x) => setP(Array.isArray(x?.checks) ? x : null)).catch(() => setP(null));
    }, delayMs);
    return () => clearTimeout(timer);
  }, [client, key, delayMs]);
  if (!p) return null;
  const missing = p.checks.filter((c) => !c.ok);
  return (
    <View style={s.card} accessibilityLabel="说明完整度">
      <Text style={s.title}>说明完整度 {Math.round(p.completeness * 100)}%</Text>
      {p.price.sample_size > 0 && <Text style={s.muted}>预算{POSITION[p.price.position]}（中位 {fmtYuan(p.price.p50_cents ?? 0)}）</Text>}
      {missing.map((c) => <Text key={c.key}>· {c.hint}</Text>)}
      {/* SCN-106 创作类需求九项（140 号 spec）：只是提示，不计入完整度 */}
      {p.brief && p.brief.missing > 0 && (
        <View accessibilityLabel="创作类需求九项">
          <Text style={s.muted}>创作类需求一般写清九项，已写 {p.brief.items.length - p.brief.missing}/{p.brief.items.length}。还可以补：</Text>
          {p.brief.items.filter((i) => !i.ok).map((i) => <Text key={i.name}>· {i.name}：{i.ask}</Text>)}
        </View>
      )}
      {p.risks.map((r) => <Text key={r.kind} style={s.muted}>⚠ {r.text}</Text>)}
    </View>
  );
}

/** 任务详情上的一块：报名前看一眼风险、技能、价格位置。取不到就不显示。 */
export function TaskProfileBlock({ client, taskId }: { client: PlatformClient; taskId: number }) {
  const [p, setP] = useState<TaskProfile | null>(null);
  useEffect(() => {
    Promise.resolve().then(() => client.taskProfile(taskId))
      .then((x) => setP(Array.isArray(x?.risks) ? x : null)).catch(() => setP(null));
  }, [client, taskId]);
  if (!p) return null;
  const skills = [...p.declared_skills, ...p.inferred_skills];
  return (
    <View style={s.card} accessibilityLabel="这单的画像">
      <Text style={s.muted}>{p.mode === 'remote' ? '线上' : '线下'}{skills.length ? ` · 技能：${skills.join('、')}` : ''}
        {p.price.sample_size > 0 ? ` · 预算${POSITION[p.price.position]}` : ''} · 说明完整度 {Math.round(p.completeness * 100)}%</Text>
      {p.risks.map((r) => <Text key={r.kind}>⚠ {r.text}</Text>)}
    </View>
  );
}

export function CapabilityScreen({ client }: { client: PlatformClient }) {
  const [c, setC] = useState<CapabilityProfile | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    client.myCapability().then((got) => { if (hasLists(got, 'categories', 'skills')) setC(got); else setError(MALFORMED_TEXT); })   // APP-093
      .catch((e) => setError(apiErrorText(e)));
  }, [client]);
  if (!c) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  const pct = (x: number | null) => (x === null ? '样本不足' : `${Math.round(x * 100)}%`);
  return (
    <View style={s.box}>
      <Text style={s.muted}>只统计在平台上完成的单；自述的技能与有成交佐证的分开写。</Text>
      {c.tasks_completed === 0 && <Text>还没有在平台上完成过合作。</Text>}
      {c.categories.map((x) => <Text key={x.category}>· {x.category}：完成 {x.completed} 单{x.rating_avg !== null ? `，平均 ${x.rating_avg} 星` : ''}</Text>)}
      {c.skills.length > 0 && <Text>技能：{c.skills.map((k) => `${k.skill}（${k.evidenced ? '有成交佐证' : '自述'}）`).join('、')}</Text>}
      {c.certifications.length > 0 && <Text>已核验资质：{c.certifications.join('、')}</Text>}
      <Text style={s.muted}>准时交付 {pct(c.on_time_rate)} · 返工 {pct(c.rework_rate)}{c.disputes !== null ? ` · 纠纷 ${c.disputes} 次（只有你看得到）` : ''}</Text>
    </View>
  );
}

/** SKL-106 App 上编辑我的技能（135 号 spec）：写的是别名也没关系，平台按技能概念匹配，这里写清会按什么匹配。 */
export function SkillsScreen({ client }: { client: PlatformClient }) {
  const [text, setText] = useState('');
  const [hints, setHints] = useState<SkillNormalized[]>([]);
  const [known, setKnown] = useState<string[]>([]);
  useEffect(() => {
    Promise.resolve().then(() => client.skillConcepts())
      .then((r) => setKnown(Array.isArray(r?.items) ? r.items.map((c) => c.name) : [])).catch(() => setKnown([]));
  }, [client]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { client.me().then((m) => setText((m.skills ?? []).join('、'))).catch((e) => setError(apiErrorText(e))); }, [client]);
  const list = text.split(/[、,，\s]+/).filter(Boolean);
  const key = list.join(',');
  useEffect(() => {
    if (!key) { setHints([]); return undefined; }
    const t = setTimeout(() => {
      Promise.resolve().then(() => client.normalizeSkills(key.split(',')))
        .then((r) => setHints(Array.isArray(r?.items) ? r.items : [])).catch(() => setHints([]));
    }, 500);
    return () => clearTimeout(t);
  }, [client, key]);
  const mapped = hints.filter((i) => i.known && i.canonical !== i.skill);
  const unknown = hints.filter((i) => !i.known);
  return (
    <View style={s.box}>
      <Text style={s.muted}>技能用于推荐接单。写「VI 设计」「标志设计」都可以：平台按技能概念匹配。</Text>
      <TextInput style={s.input} accessibilityLabel="我的技能" value={text} onChangeText={setText} placeholder="用、分隔，如：保洁、跑腿" />
      {mapped.map((i) => <Text key={i.skill} style={s.muted}>「{i.skill}」按「{i.canonical}」匹配</Text>)}
      {unknown.length > 0 && <Text style={s.muted}>{unknown.map((i) => `「${i.skill}」`).join('')}平台还不认识，只按原样匹配</Text>}
      {known.filter((n) => !list.includes(n)).length > 0 && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} accessibilityLabel="平台认得的技能">
          {known.filter((n) => !list.includes(n)).slice(0, 12).map((n) => (
            <Text key={n} style={s.chip} onPress={() => setText([...list, n].join('、'))}>{n}</Text>
          ))}
        </View>
      )}
      <Button title="保存" onPress={() => void client.updateMe({ skills: list }).then(() => setNotice('技能已更新')).catch((e) => setError(apiErrorText(e)))} />
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={{ color: '#b91c1c' }}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  card: { borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4, alignSelf: 'stretch' },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#777' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  chip: { borderWidth: 1, borderColor: '#ddd', borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4, color: '#275c52' },
});
