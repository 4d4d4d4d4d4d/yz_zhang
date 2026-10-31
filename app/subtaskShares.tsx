// AI-DEC-024 App 上的跨子任务产出共享（321 号 spec）：交付人把成果开放给要等它的下一步、随时收回；
// 下一步的执行者看前一步开放的交付说明与预览图（原图不在里面）。与 web 的 SubtaskShares 同一份接口、同一句话。
import { apiErrorText, formatDateTime, TASK_STATUS_LABEL, type PlatformClient, type SubtaskInput, type SubtaskShareView } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Image, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

export function ShareToNextStepsBlock({ client, taskId }: { client: PlatformClient; taskId: number }) {
  const [view, setView] = useState<SubtaskShareView | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    client.subtaskShares(taskId).then(setView).catch(() => setView(null));
  }, [client, taskId]);
  useEffect(() => { load(); }, [load]);
  const steps = Array.isArray(view?.next_steps) ? view.next_steps : [];
  if (!view || steps.length === 0) return null;
  async function run(fn: () => Promise<SubtaskShareView>) {
    setError('');
    try { setView(await fn()); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View accessibilityLabel="开放给下一步" style={s.card}>
      <Text style={s.title}>把成果开放给下一步</Text>
      <Text style={s.muted}>
        {view.delivered
          ? '下面这几步要等你这一步。开不开放由你定：开了，那一步的执行者能看你的交付说明和预览图（原图不在里面），随时可以收回。'
          : '交付之后，可以把交付说明和预览图开放给要等你这一步的人。'}
      </Text>
      {steps.map((st) => (
        <View key={st.task_id} style={s.row}>
          <Text style={{ flex: 1 }}>
            {st.title} · {TASK_STATUS_LABEL[st.status] ?? st.status} · {st.executor_nickname ?? '还没人接'}{st.shared ? ' · 已开放' : ''}
          </Text>
          {view.delivered && (st.shared && st.share_id
            ? <TouchableOpacity onPress={() => void run(() => client.revokeSubtaskShare(taskId, st.share_id as number))}><Text style={s.link}>收回</Text></TouchableOpacity>
            : <TouchableOpacity onPress={() => void run(() => client.shareToNextStep(taskId, st.task_id))}><Text style={s.link}>开放给这一步</Text></TouchableOpacity>)}
        </View>
      ))}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

export function PreviousStepInputsBlock({ client, taskId, baseUrl = '' }: { client: PlatformClient; taskId: number; baseUrl?: string }) {
  const [rows, setRows] = useState<SubtaskInput[]>([]);
  useEffect(() => {
    client.subtaskInputs(taskId).then((r) => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]));
  }, [client, taskId]);
  if (rows.length === 0) return null;
  return (
    <View accessibilityLabel="前一步的成果" style={s.card}>
      <Text style={s.title}>前一步的成果</Text>
      <Text style={s.muted}>前一步的交付人开放给你的交付说明与预览图；对方可以随时收回，需要留底的请和发单人确认。</Text>
      {rows.map((r) => (
        <View key={r.from_task_id} style={{ gap: 4 }}>
          <Text style={s.row}>{r.title} · 开放于 {formatDateTime(r.shared_at)}</Text>
          {(Array.isArray(r.deliveries) ? r.deliveries : []).map((d, i) => <Text key={i}>{d.content}</Text>)}
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            {(Array.isArray(r.previews) ? r.previews : []).map((p) => (
              <Image key={p.id} accessibilityLabel="前一步的预览图" source={{ uri: `${baseUrl}${p.url}` }} style={s.img} />
            ))}
          </View>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 13 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  link: { color: '#275c52' },
  error: { color: '#b91c1c', fontSize: 13 },
  img: { width: 96, height: 96, borderRadius: 8 },
});
