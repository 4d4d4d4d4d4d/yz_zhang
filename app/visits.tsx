// SCN-120 App 上的上门回报（176 号 spec）：接单人每次上门勾清单、写备注、拍一张；双方看得到计划几次、回报几次、每次漏了什么。
// 与 web 的 VisitsPanel 同一份接口与同一句话；拍照沿用资质页的取图方式（压到 0.5 质量、超过 2MB 不传）。
import { apiErrorText, formatDateTime, visitPresence, type PlatformClient, type Task, type TaskVisits } from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

/** 写了上门次数或清单的单才有这一块（两端同一条）。 */
export function hasVisits(task: Pick<Task, 'visits_planned' | 'visit_checklist'>): boolean {
  return (task.visits_planned ?? 0) > 0 || (task.visit_checklist ?? []).length > 0;
}

export function VisitsBlock({ client, task, isExecutor, locate }: {
  client: PlatformClient; task: Task; isExecutor: boolean;
  /** SCN-124 取当前位置（App 主框架传进来；拿不到抛错）。没有就不显示「带上位置」 */
  locate?: () => Promise<{ lat: number; lng: number }>;
}) {
  const [data, setData] = useState<TaskVisits | null>(null);
  const [withLocation, setWithLocation] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const [note, setNote] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(() => { client.taskVisits(task.id).then(setData).catch(() => setData(null)); }, [client, task.id]);
  useEffect(() => { load(); }, [load]);
  const checklist = task.visit_checklist ?? [];

  async function shoot() {
    setError('');
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (perm.status !== 'granted') { setError('没有相机权限，请在系统设置里允许后重试'); return; }
      const r = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
      if (r.canceled) return;
      const asset = r.assets?.[0];
      if (!asset?.base64) { setError('读不到图片数据，请再拍一次'); return; }
      if ((asset.base64.length / 4) * 3 > MAX_IMAGE_BYTES) { setError('这张图超过 2MB，请拍得近一些'); return; }
      const up = await client.uploadImage(asset.mimeType || 'image/jpeg', asset.base64);
      setImages((prev) => [...prev, up.url]);
    } catch (e) { setError(apiErrorText(e)); }
  }

  async function submit() {
    setError('');
    try {
      // SCN-124 勾了「带上位置」才取定位：与到场打卡同一套规则，超出范围时服务端会写明差多远
      const pos = withLocation && locate ? await locate() : null;
      await client.reportVisit(task.id, { done, note, images, ...(pos ? { lat: pos.lat, lng: pos.lng } : {}) });
      setDone([]); setNote(''); setImages([]);
      load();
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <View style={styles.card} accessibilityLabel="上门回报">
      <Text style={styles.title}>上门回报{data ? ` · ${data.reported}${data.planned ? `/${data.planned}` : ''} 次` : ''}</Text>
      {!!data && data.missed_total > 0 && <Text style={styles.warn}>一共有 {data.missed_total} 项没做（见下面每次的记录）</Text>}
      {/* SCN-136 几次回报带了到场打卡 */}
      {!!visitPresence(data) && <Text accessibilityLabel="到场次数">{visitPresence(data)}</Text>}
      {!!data && Array.isArray(data.visits) && data.visits.map((v) => (
        <Text key={v.id} style={styles.row}>
          第 {v.n} 次 · {formatDateTime(v.created_at)}：{v.done.length ? `已做：${v.done.join('、')}` : '清单没勾'}
          {v.missed.length ? `；没做：${v.missed.join('、')}` : ''}{v.note ? ` · ${v.note}` : ''}{v.images.length ? ` · ${v.images.length} 张照片` : ''}
          {typeof v.at_site_m === 'number' ? ` · 到场（距 ${v.at_site_m} 米）` : ''}
        </Text>
      ))}
      {isExecutor && task.status === 'in_progress' && (
        <>
          {checklist.map((item) => (
            <TouchableOpacity key={item} accessibilityRole="checkbox" accessibilityLabel={`做了：${item}`}
                              accessibilityState={{ checked: done.includes(item) }}
                              onPress={() => setDone((d) => d.includes(item) ? d.filter((x) => x !== item) : [...d, item])}>
              <Text style={styles.row}>{done.includes(item) ? '☑ ' : '☐ '}{item}</Text>
            </TouchableOpacity>
          ))}
          <TextInput style={styles.input} accessibilityLabel="这次的备注" placeholder="这次的备注（宠物状态、异常情况…）"
                     value={note} onChangeText={setNote} />
          <TouchableOpacity onPress={() => void shoot()}><Text style={styles.link}>拍一张（已 {images.length} 张）</Text></TouchableOpacity>
          {!!locate && !task.is_remote && (
            <TouchableOpacity accessibilityRole="checkbox" accessibilityLabel="带上当前位置" accessibilityState={{ checked: withLocation }}
                              onPress={() => setWithLocation((x) => !x)}>
              <Text style={styles.row}>{withLocation ? '☑ ' : '☐ '}带上当前位置（证明到场，和到场打卡一样）</Text>
            </TouchableOpacity>
          )}
          {!!error && <Text style={styles.error}>{error}</Text>}
          <TouchableOpacity style={styles.button} onPress={() => void submit()}><Text style={styles.buttonText}>交这次的上门回报</Text></TouchableOpacity>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  title: { fontSize: 15, fontWeight: '600' },
  row: { fontSize: 14 },
  warn: { color: '#92400e', fontSize: 13, fontWeight: '600' },
  error: { color: '#b91c1c', fontSize: 13 },
  link: { color: '#275c52' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  button: { backgroundColor: '#275c52', borderRadius: 10, padding: 12, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '600' },
});
