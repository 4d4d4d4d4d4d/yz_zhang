// VER-053 App 上的核验台（381 号 spec）：看单、接单、提交结论，被点名的单可以当场拒绝。
// 和网页 /verify 同一组接口、同一套说法：不能接的写原因（CLI-064），置信度写明是助理自报的（AGT-013），
// 不通过时理由太空当场提醒（KB-063b），修正稿要重新过平台判据（VER-030）。
import {
  apiErrorText, asList, lessonSpecific, VAGUE_LESSON_HINT, verifyTriggerLabel, fmtYuan,
  type PlatformClient, type VerificationOrderDetail, type VerificationOrderView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

type OpenOrder = VerificationOrderView & { category: string; task_title: string; claimable: boolean; reason: string };
type Outcome = 'approved' | 'revised' | 'rejected';
const OUTCOMES: ReadonlyArray<readonly [Outcome, string]> = [['approved', '通过'], ['revised', '已修正'], ['rejected', '不通过']];

export function VerifyDeskScreen({ client }: { client: PlatformClient }) {
  const [orders, setOrders] = useState<OpenOrder[]>([]);
  const [meId, setMeId] = useState<number | null>(null);
  const [detail, setDetail] = useState<VerificationOrderDetail | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setOrders(asList<OpenOrder>(await client.openVerificationOrders().catch(() => [])));
  }, [client]);
  useEffect(() => {
    void load();
    void client.me().then((m) => setMeId(m && typeof m.id === 'number' ? m.id : null)).catch(() => setMeId(null));
  }, [client, load]);

  async function act(fn: () => Promise<unknown>, done = '') {
    setError(''); setNotice(''); setBusy(true);
    try { await fn(); if (done) setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }

  if (detail) {
    return <OrderDetail client={client} detail={detail} onDone={(msg) => { setDetail(null); setNotice(msg); void load(); }} />;
  }
  return (
    <View style={s.box} accessibilityLabel="核验台">
      <Text style={s.muted}>AI 助理没把握、判据没过、或发布方点名请你看的单在这里。核验是「看一遍」不是「重做」，报酬按原任务金额的一个比例计。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {!!notice && <Text style={s.ok}>{notice}</Text>}
      {orders.length === 0 && <Text style={s.muted}>当前没有待核验的单。</Text>}
      {orders.map((o) => {
        const mine = o.designated_verifier_id != null && o.designated_verifier_id === meId && o.status === 'open';
        return (
          <View key={o.id} style={s.item}>
            <Text style={s.name}>{o.task_title}</Text>
            <Text style={s.muted}>{o.category} · 报酬 {fmtYuan(o.fee_cents)}</Text>
            <Text style={s.muted}>{verifyTriggerLabel(o.trigger)}</Text>
            {!o.claimable && !!o.reason && <Text style={s.error}>{o.reason}</Text>}
            <View style={s.row}>
              <Pressable accessibilityRole="button" disabled={!o.claimable || busy} style={[s.btn, (!o.claimable || busy) && s.disabled]}
                         onPress={() => void act(async () => {
                           await client.claimVerificationOrder(o.id);
                           const d = await client.verificationOrder(o.id);
                           if (d && typeof d === 'object' && typeof d.id === 'number') setDetail(d);
                         })}>
                <Text style={s.btnText}>接下</Text>
              </Pressable>
              {/* VER-050b（374 号 spec）点名请我核验、还没接的单：不方便就当场拒绝，钱立刻退给发布方 */}
              {mine && (
                <Pressable accessibilityRole="button" disabled={busy} style={s.ghost}
                           onPress={() => void act(() => client.declineVerificationOrder(o.id), '已拒绝，核验费已退回给发布方')}>
                  <Text>不方便，拒绝</Text>
                </Pressable>
              )}
            </View>
          </View>
        );
      })}
    </View>
  );
}

function OrderDetail({ client, detail, onDone }: { client: PlatformClient; detail: VerificationOrderDetail; onDone: (msg: string) => void }) {
  const [outcome, setOutcome] = useState<Outcome>('approved');
  const [comment, setComment] = useState('');
  const [revised, setRevised] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const criteria = asList<{ text: string; kind: string }>(detail.acceptance_criteria);
  const results = asList<{ text: string; passed: boolean }>(detail.agent_criteria_results);

  async function submit() {
    setError(''); setBusy(true);
    try {
      await client.submitVerificationOutcome(detail.id, outcome, comment, revised);
      onDone('结论已提交');
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }

  return (
    <View style={s.box} accessibilityLabel="核验单详情">
      <Text style={s.name}>核验 #{detail.id}：{detail.task_title}</Text>
      {!!detail.task_description && <Text style={s.muted}>{detail.task_description}</Text>}
      <Text style={s.name}>验收标准</Text>
      {criteria.map((c, i) => <Text key={i} style={s.muted}>• {c.text}{c.kind === 'auto' ? '（平台自动判）' : ''}</Text>)}
      <Text style={s.name}>AI 产出</Text>
      <Text selectable>{detail.agent_output}</Text>
      <Text style={s.muted}>
        助理自报置信度 {typeof detail.agent_confidence_bps === 'number' ? `${(detail.agent_confidence_bps / 100).toFixed(1)}%` : '—'}（自报值，仅供参考）
      </Text>
      {results.map((c, i) => <Text key={i} style={s.muted}>{c.passed ? '✓' : '✗'} {c.text}</Text>)}
      <Text style={s.name}>你的结论</Text>
      <View style={s.row}>
        {OUTCOMES.map(([v, label]) => (
          <Pressable key={v} accessibilityRole="button" accessibilityState={{ selected: outcome === v }}
                     style={[s.chip, outcome === v && s.chipOn]} onPress={() => setOutcome(v)}>
            <Text>{outcome === v ? '● ' : '○ '}{label}</Text>
          </Pressable>
        ))}
      </View>
      <TextInput style={s.input} multiline value={comment} onChangeText={setComment}
                 placeholder={outcome === 'approved' ? '核验说明（发布方与平台都会看到）' : '哪里不对、要怎么改（也会成为下一单的经验）'} />
      {/* KB-063b 不通过时理由写得太空就当场提醒（不拦提交） */}
      {outcome !== 'approved' && comment.trim() !== '' && !lessonSpecific(comment, revised) && (
        <Text style={s.error} testID="vague-lesson">{VAGUE_LESSON_HINT}</Text>
      )}
      {outcome === 'revised' && (
        <>
          <TextInput style={s.input} multiline value={revised} onChangeText={setRevised} placeholder="修正稿正文（它会成为交付物）" />
          <Text style={s.muted}>修正稿会重新跑一遍平台的自动判据，不通过会被退回。</Text>
        </>
      )}
      {!!error && <Text style={s.error}>{error}</Text>}
      <Pressable accessibilityRole="button" disabled={busy} style={[s.btn, busy && s.disabled]} onPress={() => void submit()}>
        <Text style={s.btnText}>提交结论</Text>
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  item: { gap: 4, paddingVertical: 8, borderTopWidth: 1, borderTopColor: '#eef2ef' },
  name: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
  ok: { color: '#166534', fontSize: 13 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb', minHeight: 44 },
  btn: { backgroundColor: '#275c52', borderRadius: 10, paddingVertical: 10, paddingHorizontal: 16, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600' },
  ghost: { borderRadius: 10, paddingVertical: 10, paddingHorizontal: 16, borderWidth: 1, borderColor: '#cbd5e1', alignItems: 'center' },
  chip: { backgroundColor: '#f1f5f2', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 6 },
  chipOn: { backgroundColor: '#dcefe7' },
  disabled: { opacity: 0.4 },
});
