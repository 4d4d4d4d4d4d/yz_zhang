// RISK-010~014（399 号 spec，V426）App 上的举报入口与「我的举报」。
//
// 以前 App 只能在任务详情里举报任务、不能选类型；个人空间、私信都举报不了，交了以后也看不到结果。
// 《网络信息内容生态治理规定》第十六条要求平台设置便捷的投诉举报入口、及时处置并反馈结果。
import {
  MAX_REPORT_IMAGES, REPORT_CATEGORY_OPTIONS, apiErrorText, formatDateTime, reportStatusLine, reportSubmittedNote, reportTargetLabel,
  type MyReport, type PlatformClient, type ReportCategory, type ReportTarget,
} from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

/** RISK-017（404 号 spec）从相册选一张截图上传。不从 supportTickets 引：那边已经引了本文件，互相引用会成环 */
async function pickShot(client: PlatformClient): Promise<{ url?: string; error?: string }> {
  const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (perm.status !== 'granted') return { error: '没有相册权限，请在系统设置里允许后重试' };
  const r = await ImagePicker.launchImageLibraryAsync({ quality: 0.6, base64: true });
  if (r.canceled) return {};
  const asset = r.assets?.[0];
  if (!asset?.base64) return { error: '读不到图片数据，请换一张' };
  if ((asset.base64.length / 4) * 3 > MAX_IMAGE_BYTES) return { error: '这张图超过 2MB，请裁小一些再选' };
  const up = await client.uploadImage(asset.mimeType || 'image/jpeg', asset.base64);
  return { url: up.url };
}

export function ReportBlock({ client, targetType, targetId, label }: {
  client: PlatformClient; targetType: ReportTarget; targetId: number; label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<ReportCategory>('other');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const what = reportTargetLabel(targetType);

  if (!open) {
    return (
      <View>
        <TouchableOpacity accessibilityLabel={`举报这条${what}`} onPress={() => { setOpen(true); setNote(''); setError(''); }}>
          <Text style={s.link}>{label ?? '举报'}</Text>
        </TouchableOpacity>
        {!!note && <Text style={s.muted} accessibilityLabel="举报结果">{note}</Text>}
      </View>
    );
  }
  return (
    <View style={s.card} accessibilityLabel={`举报${what}`}>
      <Text style={s.muted}>哪一类问题</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {REPORT_CATEGORY_OPTIONS.map((o) => (
          <TouchableOpacity key={o.value} accessibilityLabel={`类型：${o.label}`} accessibilityState={{ selected: category === o.value }}
                            onPress={() => setCategory(o.value)}>
            <Text style={[s.chip, category === o.value && s.chipOn]}>{o.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TextInput style={s.input} accessibilityLabel="举报说明" multiline maxLength={500}
                 placeholder="说说哪里有问题（至少 2 个字，会进入人工审核）" value={reason} onChangeText={setReason} />
      {/* RISK-017（404 号 spec）附截图，最多 3 张：聊天记录、页面截图让审核员不用只凭一句话判断 */}
      {images.length > 0 && <Text style={s.muted} accessibilityLabel="已附截图">已附 {images.length} 张截图</Text>}
      {images.length < MAX_REPORT_IMAGES && (
        <TouchableOpacity accessibilityLabel="附截图" disabled={busy} onPress={() => {
          setError('');
          pickShot(client).then((r) => {
            if (r.error) setError(r.error);
            if (r.url) setImages((old) => [...old, r.url!]);
          }).catch((e) => setError(apiErrorText(e)));
        }}>
          <Text style={s.link}>＋ 附截图（最多 {MAX_REPORT_IMAGES} 张）</Text>
        </TouchableOpacity>
      )}
      {!!error && <Text style={s.error}>{error}</Text>}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Button title="提交举报" disabled={busy || reason.trim().length < 2} onPress={() => {
          setBusy(true); setError('');
          client.report(targetType, targetId, reason.trim(), category, images.length ? images : undefined)
            .then((r) => { setNote(reportSubmittedNote(r)); setOpen(false); setReason(''); setCategory('other'); setImages([]); })
            .catch((e) => setError(apiErrorText(e)))
            .finally(() => setBusy(false));
        }} />
        <Button title="取消" onPress={() => setOpen(false)} />
      </View>
    </View>
  );
}

export function MyReportsBlock({ client }: { client: PlatformClient }) {
  const [rows, setRows] = useState<MyReport[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    client.myReports()
      .then((r) => { if (live) setRows(Array.isArray(r?.items) ? r.items : []); })
      .catch((e) => { if (live) setError(apiErrorText(e)); });
    return () => { live = false; };
  }, [client]);
  return (
    <View style={s.card} accessibilityLabel="我的举报">
      <Text style={s.title}>我的举报</Text>
      <Text style={s.muted}>在任务、个人空间和私信旁边点「举报」提交；处理完会通知你。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {rows && rows.length === 0 && <Text style={s.muted}>还没有举报过。</Text>}
      {rows && rows.map((r) => (
        <View key={r.id} accessibilityLabel={`举报 ${r.id}`}>
          <Text>{reportTargetLabel(r.target_type)} #{r.target_id} · {r.category_label}</Text>
          <Text style={s.muted}>{r.reason}{Array.isArray(r.images) && r.images.length ? ` · 附图 ${r.images.length} 张` : ''} · {formatDateTime(r.created_at)}</Text>
          <Text>{reportStatusLine(r)}{r.resolved_at ? ` · ${formatDateTime(r.resolved_at)}` : ''}</Text>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 8, padding: 12, gap: 6 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#666' },
  error: { color: '#c62828' },
  link: { color: '#1565c0' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 6, padding: 8, minHeight: 60 },
  chip: { borderWidth: 1, borderColor: '#ccc', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  chipOn: { borderColor: '#1565c0', color: '#1565c0' },
});
