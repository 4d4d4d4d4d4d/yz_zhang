// TASK-022 App 上的执行动态（386 号 spec）：成交双方看进度、写进度；接单人可以顺手报「还要几天」（AI-DEC-021d），
// 发单人的驾驶舱时间线按它重排。网页早有这一块，App 上原来没有——接单人在手机上发不了进度，发单人也看不到。
// 与网页同一组接口、同一套判断（共享 SDK 的 daysLeftNote / parseDaysLeft）。
// TASK-022c（388 号 spec）写进度可以拍照或从相册选图留证（MOB-021：纠纷时最有力的证据往往是现场照片），与网页一样最多 9 张。
import { apiErrorText, daysLeftNote, formatDateTime, mediaUri, parseDaysLeft, type PlatformClient, type Task } from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type Entry = Awaited<ReturnType<PlatformClient['listProgress']>>[number];

/** 服务端每条进度最多 9 张（ProgressIn.images）、每张 2MB（storage.MAX_BYTES）；本地先拦，省得传完再被拒 */
export const MAX_PROGRESS_PHOTOS = 9;
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

/** 成交双方、开工以后才有（与网页同一条） */
export function canSeeProgress(task: Pick<Task, 'status' | 'creator_id' | 'executor_id'>, meId: number | null | undefined): boolean {
  return meId != null && (meId === task.creator_id || meId === task.executor_id) && !['draft', 'published'].includes(task.status);
}

export function ProgressBlock({ client, task, meId, baseUrl = '' }: {
  client: PlatformClient; task: Pick<Task, 'id' | 'status' | 'executor_id'>; meId: number | null;
  /** TASK-022d（390 号 spec）服务端地址：进度照片是相对路径，App 要拼上它才加载得出来 */
  baseUrl?: string;
}) {
  const [logs, setLogs] = useState<Entry[]>([]);
  const [note, setNote] = useState('');
  const [days, setDays] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [shots, setShots] = useState<string[]>([]);
  const isExecutor = meId != null && meId === task.executor_id;
  const load = useCallback(() => {
    void client.listProgress(task.id).then((r) => setLogs(Array.isArray(r) ? r : [])).catch(() => setLogs([]));
  }, [client, task.id]);
  useEffect(() => { load(); }, [load]);
  const parsed = isExecutor ? parseDaysLeft(days) : undefined;
  const canSend = !busy && note.trim() !== '' && parsed !== null;

  async function pick(fromCamera: boolean) {
    setError(''); setBusy(true);
    try {
      const perm = fromCamera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (perm.status !== 'granted') {
        setError(fromCamera ? '没有相机权限，请在系统设置里允许后重试' : '没有相册权限，请在系统设置里允许后重试');
        return;
      }
      const opts = { quality: 0.5, base64: true } as const;
      const r = fromCamera ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
      if (r.canceled) return;
      const asset = r.assets?.[0];
      if (!asset?.base64) { setError('读不到图片数据，请换一张或改用拍照'); return; }
      if ((asset.base64.length / 4) * 3 > MAX_IMAGE_BYTES) { setError('这张图超过 2MB，请拍得近一些或选一张更小的'); return; }
      // 进度里的图要的是上传后回的地址（/api/v1/files/…），服务端只认本平台的
      const up = await client.uploadImage(asset.mimeType || 'image/jpeg', asset.base64);
      setShots((prev) => [...prev, up.url].slice(0, MAX_PROGRESS_PHOTOS));
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }

  async function send() {
    setError(''); setBusy(true);
    try {
      await client.addProgress(task.id, note.trim(), shots, parsed ?? undefined);
      setNote(''); setDays(''); setShots([]);
      load();
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }

  return (
    <View style={s.card} accessibilityLabel="执行动态">
      <Text style={s.title}>执行动态</Text>
      {logs.length === 0 && <Text style={s.muted}>还没有进度。</Text>}
      {logs.map((p) => {
        // TASK-022d（390 号 spec）照片直接看：地址拼不出来的（畸形、外链）不画
        const pics = (Array.isArray(p.images) ? p.images : []).map((u) => mediaUri(baseUrl, u)).filter(Boolean);
        return (
          <View key={p.id} style={{ gap: 4 }}>
            <Text style={s.row}>
              {p.content}{daysLeftNote(p)}
              <Text style={s.muted}> · {formatDateTime(p.created_at)}{Array.isArray(p.images) && p.images.length ? ` · ${p.images.length} 张图` : ''}</Text>
            </Text>
            {pics.length > 0 && (
              <View style={s.chips}>
                {pics.map((uri, i) => <Image key={uri} accessibilityLabel={`进度照片 ${i + 1}`} source={{ uri }} style={s.thumb} />)}
              </View>
            )}
          </View>
        );
      })}
      {task.status === 'in_progress' && (
        <View style={{ gap: 6 }}>
          <TextInput style={s.input} placeholder="进度说明…" value={note} onChangeText={setNote} />
          {isExecutor && (
            <TextInput style={s.input} accessibilityLabel="还要几天" placeholder="还要几天（选填，0 = 今天做完）" keyboardType="number-pad"
                       value={days} onChangeText={setDays} />
          )}
          {isExecutor && parsed === null && <Text style={s.error}>还要几天填 0~365 的整数（0 = 今天做完）</Text>}
          <View style={s.chips}>
            {(['拍照', '从相册选'] as const).map((label, i) => (
              <Pressable key={label} accessibilityRole="button" disabled={busy || shots.length >= MAX_PROGRESS_PHOTOS}
                         style={[s.ghost, (busy || shots.length >= MAX_PROGRESS_PHOTOS) && s.disabled]} onPress={() => void pick(i === 0)}>
                <Text>{label}</Text>
              </Pressable>
            ))}
          </View>
          {shots.length > 0 && (
            <View style={s.chips}>
              <Text style={s.muted}>已附 {shots.length} 张照片{shots.length >= MAX_PROGRESS_PHOTOS ? `（最多 ${MAX_PROGRESS_PHOTOS} 张）` : ''}</Text>
              <Pressable accessibilityRole="button" onPress={() => setShots((prev) => prev.slice(0, -1))}><Text style={s.link}>去掉最后一张</Text></Pressable>
            </View>
          )}
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
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  ghost: { borderRadius: 10, paddingVertical: 8, paddingHorizontal: 14, borderWidth: 1, borderColor: '#cbd5e1' },
  link: { color: '#275c52', fontSize: 13 },
  thumb: { width: 64, height: 64, borderRadius: 8, backgroundColor: '#f1f5f2' },
});
