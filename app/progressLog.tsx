// TASK-022 App 上的执行动态（386 号 spec）：成交双方看进度、写进度；接单人可以顺手报「还要几天」（AI-DEC-021d），
// 发单人的驾驶舱时间线按它重排。网页早有这一块，App 上原来没有——接单人在手机上发不了进度，发单人也看不到。
// 与网页同一组接口、同一套判断（共享 SDK 的 daysLeftNote / parseDaysLeft）。
import { apiErrorText, daysLeftNote, formatDateTime, parseDaysLeft, type PlatformClient, type Task } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type Entry = Awaited<ReturnType<PlatformClient['listProgress']>>[number];

/** 成交双方、开工以后才有（与网页同一条） */
export function canSeeProgress(task: Pick<Task, 'status' | 'creator_id' | 'executor_id'>, meId: number | null | undefined): boolean {
  return meId != null && (meId === task.creator_id || meId === task.executor_id) && !['draft', 'published'].includes(task.status);
}

export function ProgressBlock({ client, task, meId }: {
  client: PlatformClient; task: Pick<Task, 'id' | 'status' | 'executor_id'>; meId: number | null;
}) {
  const [logs, setLogs] = useState<Entry[]>([]);
  const [note, setNote] = useState('');
  const [days, setDays] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const isExecutor = meId != null && meId === task.executor_id;
  const load = useCallback(() => {
    void client.listProgress(task.id).then((r) => setLogs(Array.isArray(r) ? r : [])).catch(() => setLogs([]));
  }, [client, task.id]);
  useEffect(() => { load(); }, [load]);
  const parsed = isExecutor ? parseDaysLeft(days) : undefined;
  const canSend = !busy && note.trim() !== '' && parsed !== null;

  async function send() {
    setError(''); setBusy(true);
    try {
      await client.addProgress(task.id, note.trim(), [], parsed ?? undefined);
      setNote(''); setDays('');
      load();
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }

  return (
    <View style={s.card} accessibilityLabel="执行动态">
      <Text style={s.title}>执行动态</Text>
      {logs.length === 0 && <Text style={s.muted}>还没有进度。</Text>}
      {logs.map((p) => (
        <Text key={p.id} style={s.row}>
          {p.content}{daysLeftNote(p)}
          <Text style={s.muted}> · {formatDateTime(p.created_at)}{Array.isArray(p.images) && p.images.length ? ` · ${p.images.length} 张图` : ''}</Text>
        </Text>
      ))}
      {task.status === 'in_progress' && (
        <View style={{ gap: 6 }}>
          <TextInput style={s.input} placeholder="进度说明…" value={note} onChangeText={setNote} />
          {isExecutor && (
            <TextInput style={s.input} accessibilityLabel="还要几天" placeholder="还要几天（选填，0 = 今天做完）" keyboardType="number-pad"
                       value={days} onChangeText={setDays} />
          )}
          {isExecutor && parsed === null && <Text style={s.error}>还要几天填 0~365 的整数（0 = 今天做完）</Text>}
          <Pressable accessibilityRole="button" disabled={!canSend} style={[s.btn, !canSend && s.disabled]} onPress={() => void send()}>
            <Text style={s.btnText}>更新进度</Text>
          </Pressable>
        </View>
      )}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: '#e5e7eb' },
  title: { fontSize: 15, fontWeight: '600' },
  row: { fontSize: 14 },
  muted: { color: '#6b7280', fontSize: 12 },
  error: { color: '#b91c1c', fontSize: 13 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
  btn: { backgroundColor: '#275c52', borderRadius: 10, padding: 10, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600' },
  disabled: { opacity: 0.4 },
});
