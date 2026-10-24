// KB-080~089 / AGT-080~083 经验变成能被调用的单元——App 这一端（109 号 spec）。
//
// 用户 2026-10-10：「攒经验完全可以作为检索数据库或者 skilltool 工具给后续复用」。
// 网页上有的两块，App 上同样要有：子类详情下的可复用单元（带排除条件与验证状态），
// 任务详情里双方都能用的经验工具（只出草稿，带「未经人工确认」标签，可丢弃）。
import {
  apiErrorText, fmtYuan, type ExperienceToolDraft, type PlatformClient, type ReusableUnit,
  type ReusableUnitDetail, type ReusableUnitValidation, type Task,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

const VALIDATION_LABEL: Record<ReusableUnitValidation['status'], string> = {
  unvalidated: '还没被验证过',
  validated: '用过、多数做成了',
  needs_review: '复核中',
};

function validationText(v: ReusableUnitValidation) {
  const head = VALIDATION_LABEL[v.status] ?? v.status;
  return v.uses > 0 ? `${head} · 用过 ${v.uses} 次：做成 ${v.closed}、返工 ${v.reworked}、失败 ${v.failed}` : head;
}

function contentLines(unit: ReusableUnitDetail): string[] {
  const c = unit.content ?? {};
  if (unit.kind === 'price_hint') {
    const p50 = typeof c.p50_cents === 'number' ? fmtYuan(c.p50_cents) : '—';
    const p90 = typeof c.p90_cents === 'number' ? `，九成在 ${fmtYuan(c.p90_cents)} 以内` : '';
    return [`中位 ${p50}${p90}（${unit.sample_count} 个样本）`];
  }
  if (Array.isArray(c.steps)) {
    return (c.steps as Array<{ title?: string }>).map((s, i) => `${i + 1}. ${s.title ?? ''}`);
  }
  const items = Array.isArray(c.items) ? c.items : Array.isArray(c.checklist) ? c.checklist : [];
  return (items as string[]).map((t) => `☐ ${t}`);
}

/** 子类详情下面：从它蒸馏出来、可以直接拿去用的单元。 */
export function ClusterUnitsBlock({ client, clusterId }: { client: PlatformClient; clusterId: number }) {
  const [rows, setRows] = useState<ReusableUnit[]>([]);
  const [open, setOpen] = useState<ReusableUnitDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    client.knowledgeUnits({ cluster_id: clusterId })
      .then((r) => setRows(Array.isArray(r) ? r : []))
      .catch(() => setRows([]));
  }, [client, clusterId]);

  if (rows.length === 0) return null;
  return (
    <View style={s.card}>
      <Text style={s.title}>可以直接拿去用的经验</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {rows.map((u) => (
        <View key={u.id} style={s.item}>
          <TouchableOpacity onPress={async () => {
            setError('');
            try { setOpen(open?.id === u.id ? null : await client.knowledgeUnit(u.id)); } catch (e) { setError(apiErrorText(e)); }
          }}>
            <Text style={s.link}>{u.kind_label} · {u.title}</Text>
          </TouchableOpacity>
          <Text style={s.muted}>{validationText(u.validation)}</Text>
          {/* 排除条件和单元一起出现：它就是这个单元最容易被用错的地方 */}
          <Text style={s.muted}>不适用：{u.applicability.exclusions.join('；')}</Text>
          {open?.id === u.id && (
            <View style={s.nested}>
              {contentLines(open).map((line, i) => <Text key={i}>{line}</Text>)}
              <Text style={s.muted}>
                来自 {open.sample_count} 个双方都同意复用的样本
                {open.contributors.length > 0 ? ` · 贡献者：${open.contributors.map((c) => c.nickname).join('、')}` : ''}
              </Text>
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

/** AGT-080~083 任务详情里的经验工具：只出草稿，可丢弃。 */
export function ExperienceToolsBlock({ client, task }: { client: PlatformClient; task: Task }) {
  const [tools, setTools] = useState<ReusableUnit[]>([]);
  const [draft, setDraft] = useState<ExperienceToolDraft | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    client.knowledgeUnits({ kind: 'skill_tool', category: task.category })
      .then((r) => setTools(Array.isArray(r) ? r : []))
      .catch(() => setTools([]));
  }, [client, task.category]);

  if (tools.length === 0) return null;
  return (
    <View style={s.card}>
      <Text style={s.title}>用平台经验起草</Text>
      <Text style={s.muted}>来自同类任务里双方都同意复用的经验。只起草，不花钱、不签约、不替你发消息。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {!draft && tools.map((t) => (
        <TouchableOpacity key={t.id} disabled={busy} style={[s.ghost, busy && s.disabled]} onPress={async () => {
          setError('');
          setBusy(true);
          try { setDraft(await client.invokeExperienceTool(t.id, task.id)); } catch (e) { setError(apiErrorText(e)); }
          setBusy(false);
        }}>
          <Text>{t.title}</Text>
        </TouchableOpacity>
      ))}
      {draft && (
        <View style={s.nested}>
          <Text style={s.warn}>{draft.label}</Text>
          <Text selectable>{draft.text}</Text>
          <Text style={s.muted}>来自 {draft.contributors} 位贡献者的经验。用之前逐条核对；不适用的情形：{draft.exclusions.join('；')}</Text>
          <TouchableOpacity style={s.ghost} onPress={async () => {
            try { await client.discardToolDraft(draft.invocation_id); setDraft(null); } catch (e) { setError(apiErrorText(e)); }
          }}>
            <Text>丢弃草稿</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  item: { gap: 2, paddingVertical: 4 },
  nested: { marginLeft: 12, gap: 6 },
  title: { fontSize: 15, fontWeight: '600' },
  link: { color: '#275c52', fontSize: 15 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
  warn: { color: '#92400e', fontSize: 13, fontWeight: '600' },
  ghost: { borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#cbd5e1', alignItems: 'center' },
  disabled: { opacity: 0.4 },
});
