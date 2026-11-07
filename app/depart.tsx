// SCN-122c App 上的「出发了」（364 号 spec）：接单人选预计多少分钟到，发单人收到通知，服务对象的进度链接页也显示。
// 与 web 的 DepartPanel 同一份接口、同一句话。
import { DEPART_ETA_MINUTES, apiErrorText, formatDateTime, type DepartResult, type PlatformClient, type Task } from '@platform/core';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

export function canDepart(task: Pick<Task, 'is_remote' | 'status' | 'executor_id'>, meId: number | null | undefined): boolean {
  return !task.is_remote && meId != null && task.executor_id === meId && ['matched', 'in_progress'].includes(task.status);
}

export function DepartBlock({ client, taskId }: { client: PlatformClient; taskId: number }) {
  const [minutes, setMinutes] = useState<number>(30);
  const [done, setDone] = useState<DepartResult | null>(null);
  const [error, setError] = useState('');
  return (
    <View style={s.card} accessibilityLabel="出发了">
      <View style={s.row}>
        {DEPART_ETA_MINUTES.map((m) => (
          <Pressable key={m} accessibilityRole="radio" accessibilityLabel={`预计 ${m} 分钟到`} accessibilityState={{ selected: m === minutes }}
                     onPress={() => setMinutes(m)}>
            <Text style={m === minutes ? s.chipOn : s.chip}>{m} 分钟</Text>
          </Pressable>
        ))}
      </View>
      <Pressable accessibilityRole="button" onPress={() => void (async () => {
        setError('');
        try { setDone(await client.departTask(taskId, minutes)); } catch (e) { setError(apiErrorText(e)); }
      })()}><Text style={s.link}>{done ? '改一下预计时间' : '出发了'}</Text></Pressable>
      {!!done && <Text accessibilityRole="alert">已告诉发单人：预计 {formatDateTime(done.eta_at)} 到{done.updated ? '（已更新时间）' : ''}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: '#e5e7eb' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { color: '#374151', borderWidth: 1, borderColor: '#d1d5db', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  chipOn: { color: '#fff', backgroundColor: '#2563eb', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  link: { color: '#2563eb', fontSize: 15, paddingVertical: 4 },
  error: { color: '#b91c1c', fontSize: 13 },
});
