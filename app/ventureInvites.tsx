// COOP-060 合作体邀请、加入、分配记录（142 号 spec）——App 端。
// 邀请制的另一半：被邀请的人看得到邀请、整篇读风险揭示书后自己签署加入，或者拒绝；成员能邀请别人、能看分配记录。
import {
  apiErrorText, fmtYuan, type PlatformClient, type RiskDisclosure, type ShareRow, type VentureInvitationView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

export function VentureInvitesBlock({ client, onJoined }: { client: PlatformClient; onJoined: () => void }) {
  const [rows, setRows] = useState<VentureInvitationView[]>([]);
  const [doc, setDoc] = useState<RiskDisclosure | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [read, setRead] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const r = await client.myVentureInvitations().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { client.ventureRiskDisclosure().then(setDoc).catch(() => setDoc(null)); }, [client]);
  if (rows.length === 0 && !notice) return null;
  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); setNotice(done); setOpenId(null); setRead(false); await load(); onJoined(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="我收到的邀请">
      <Text style={s.title}>我收到的邀请</Text>
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {rows.map((r) => (
        <View key={r.venture_id} style={s.card}>
          <Text style={s.title}>{r.name}</Text>
          <Text style={s.muted}>{r.inviter_nickname || `#${r.inviter_id}`} 邀请你加入 · {r.purpose || '未填写目标'} · {r.expires_at.slice(0, 10)} 前有效</Text>
          {openId === r.venture_id && doc ? (
            <View style={{ gap: 6 }}>
              <Text style={s.title}>{doc.title}（{doc.version}）</Text>
              {doc.points.map((p, i) => <Text key={i}>{i + 1}. {p}</Text>)}
              <Text style={s.muted}>{doc.text}</Text>
              <View style={s.row}>
                <Switch accessibilityLabel="我已阅读并理解上述风险" value={read} onValueChange={setRead} />
                <Text>我已阅读并理解上述风险</Text>
              </View>
              <Button title="签署并加入" disabled={!read}
                onPress={() => void act(() => client.joinVenture(r.venture_id, r.risk_disclosure_version), `已加入「${r.name}」`)} />
            </View>
          ) : (
            <Button title="读风险揭示书后加入" onPress={() => { setOpenId(r.venture_id); setRead(false); }} />
          )}
          <Button title="拒绝" onPress={() => void act(() => client.declineVentureInvitation(r.venture_id), `已拒绝「${r.name}」的邀请`)} />
        </View>
      ))}
    </View>
  );
}

export function InviteMemberBlock({ client, ventureId }: { client: PlatformClient; ventureId: number }) {
  const [uid, setUid] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  return (
    <View style={s.card} accessibilityLabel="邀请成员">
      <Text style={s.title}>邀请成员</Text>
      <Text style={s.muted}>邀请制：对方会收到通知，7 天内有效；对方要自己读并签风险揭示书才能加入，你不能替对方签。</Text>
      <TextInput style={s.input} accessibilityLabel="被邀请人编号" keyboardType="numeric" placeholder="对方的用户编号" value={uid} onChangeText={setUid} />
      <Button title="发出邀请" disabled={!Number(uid)} onPress={() => void (async () => {
        setError(''); setNotice('');
        try { await client.inviteToVenture(ventureId, Number(uid)); setNotice(`已邀请 #${uid}`); setUid(''); } catch (e) { setError(apiErrorText(e)); }
      })()} />
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

type Dist = { id: number; total_cents: number; memo: string; share_snapshot: ShareRow[]; created_at: string };

export function DistributionHistoryBlock({ client, ventureId }: { client: PlatformClient; ventureId: number }) {
  const [rows, setRows] = useState<Dist[]>([]);
  useEffect(() => {
    client.ventureDistributions(ventureId).then((r) => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]));
  }, [client, ventureId]);
  return (
    <View style={s.card} accessibilityLabel="分配记录">
      <Text style={s.title}>分配记录</Text>
      {rows.length === 0 && <Text style={s.muted}>还没有分配过。</Text>}
      {rows.map((d) => (
        <Text key={d.id}>{d.created_at.slice(0, 10)} · 共 {fmtYuan(d.total_cents)}{d.memo ? ` · ${d.memo}` : ''}（按当时份额：{d.share_snapshot.map((x) => `#${x.user_id} ${(x.share_bps / 100).toFixed(2)}%`).join('、')}）</Text>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#777' },
  error: { color: '#b91c1c' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
});
