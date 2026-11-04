// RISK-010~014（399 号 spec，V426）App 上的举报入口与「我的举报」。
//
// 以前 App 只能在任务详情里举报任务、不能选类型；个人空间、私信都举报不了，交了以后也看不到结果。
// 《网络信息内容生态治理规定》第十六条要求平台设置便捷的投诉举报入口、及时处置并反馈结果。
import {
  REPORT_CATEGORY_OPTIONS, apiErrorText, formatDateTime, reportStatusLine, reportSubmittedNote, reportTargetLabel,
  type MyReport, type PlatformClient, type ReportCategory, type ReportTarget,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export function ReportBlock({ client, targetType, targetId, label }: {
  client: PlatformClient; targetType: ReportTarget; targetId: number; label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<ReportCategory>('other');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
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
      {!!error && <Text style={s.error}>{error}</Text>}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Button title="提交举报" disabled={busy || reason.trim().length < 2} onPress={() => {
          setBusy(true); setError('');
          client.report(targetType, targetId, reason.trim(), category)
            .then((r) => { setNote(reportSubmittedNote(r)); setOpen(false); setReason(''); setCategory('other'); })
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
          <Text style={s.muted}>{r.reason} · {formatDateTime(r.created_at)}</Text>
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
