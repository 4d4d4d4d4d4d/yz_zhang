// INF-100 影响力与专家等级（127 号 spec）——App 端：我的等级与还差什么、担保与撤回、类目排行、快照证明；
// 别人空间里的影响力与「为他担保」。影响力只能靠做成事挣，不能转让——这里也没有任何转让入口。
import {
  apiErrorText, formatDateTime,
  type InfluenceLatestSnapshot, type InfluenceLeaderboard, type InfluenceMine, type InfluenceProof, type InfluencePublic, type InfluenceVouchRow,
  type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

const KIND: Record<string, string> = {
  earn_task: '完成一单', earn_publish: '发的单做成了', earn_vouch: '担保的人做成了',
  slash_dispute: '纠纷败诉', slash_vouch: '担保罚没', restore: '申诉恢复',
};
const VOUCH_STATUS: Record<InfluenceVouchRow['status'], string> = {
  active: '担保中', released: '已释放', slashed: '已罚没', withdrawn: '已撤回',
};

export function InfluenceScreen({ client }: { client: PlatformClient }) {
  const [mine, setMine] = useState<InfluenceMine | null>(null);
  const [board, setBoard] = useState<InfluenceLeaderboard | null>(null);
  const [proof, setProof] = useState<InfluenceProof | null>(null);
  const [latest, setLatest] = useState<InfluenceLatestSnapshot | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const m = await client.myInfluence();
      setMine(m);
      const top = m.categories[0]?.category;
      if (top) setBoard(await client.influenceLeaderboard(top).catch(() => null));
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { client.latestInfluenceSnapshot().then(setLatest).catch(() => setLatest(null)); }, [client]);

  async function withdraw(v: InfluenceVouchRow) {
    setError(''); setNotice('');
    try { await client.withdrawVouch(v.id); setNotice(`已撤回对 ${v.subject_nickname} 的担保`); await load(); }
    catch (e) { setError(apiErrorText(e)); }
  }

  if (!mine) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  return (
    <View style={s.box}>
      <Text style={s.muted}>{mine.rules}</Text>
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      <View style={s.card} accessibilityLabel="我的等级">
        <Text style={s.title}>我在各类目的等级</Text>
        {mine.categories.length === 0 && <Text style={s.muted}>还没有影响力：在平台上完成第一单就有了。</Text>}
        {mine.categories.map((c) => (
          <View key={c.category}>
            <Text>{c.category} · {c.tier_name} · 影响力 {c.points} · 完成 {c.completed} 单</Text>
            {(c.locked > 0 || c.tier !== 'newcomer') && <Text style={s.muted}>担保占用 {c.locked} · 还能担保 {c.available}</Text>}
            {c.gaps.map((g) => <Text key={g} style={s.muted}>{g}</Text>)}
          </View>
        ))}
      </View>
      <View style={s.card} accessibilityLabel="担保">
        <Text style={s.title}>担保</Text>
        {mine.vouches_given.length === 0 && mine.vouches_received.length === 0 && <Text style={s.muted}>还没有担保。在别人的空间里可以为他作保（熟手以上）。</Text>}
        {mine.vouches_given.map((v) => (
          <View key={`g${v.id}`} style={s.row}>
            <Text style={{ flex: 1 }}>我为 {v.subject_nickname} 担保 {v.stake} 点「{v.category}」 · {VOUCH_STATUS[v.status]}</Text>
            {v.status === 'active' && (
              <TouchableOpacity accessibilityRole="button" accessibilityLabel={`撤回对 ${v.subject_nickname} 的担保`} onPress={() => void withdraw(v)}>
                <Text style={s.link}>撤回</Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
        {mine.vouches_received.map((v) => <Text key={`r${v.id}`}>{v.voucher_nickname} 为我担保 {v.stake} 点「{v.category}」 · {VOUCH_STATUS[v.status]}</Text>)}
      </View>
      {board && board.items.length > 0 && (
        <View style={s.card} accessibilityLabel="排行">
          <Text style={s.title}>「{board.category}」的熟手与专家</Text>
          {board.items.map((r, i) => <Text key={r.user_id}>{i + 1}. {r.nickname} · {r.tier_name} · 影响力 {r.points}</Text>)}
        </View>
      )}
      <View style={s.card} accessibilityLabel="明细">
        <Text style={s.title}>最近的变动</Text>
        {mine.events.length === 0 && <Text style={s.muted}>还没有变动。</Text>}
        {mine.events.map((e) => <Text key={e.id}>{e.points > 0 ? '+' : ''}{e.points} {KIND[e.kind] ?? e.kind} · {e.category} · {e.reason}（{formatDateTime(e.created_at)}）</Text>)}
      </View>
      <View style={s.card} accessibilityLabel="存证">
        <Text style={s.title}>快照与证明</Text>
        <Text style={s.muted}>每天的快照做成 Merkle 树，树根写进存证链；拿着树根和你这一条的路径，谁都能自己验算。</Text>
        {latest?.snapshot && !proof && <Text style={s.muted}>最近一次快照：{formatDateTime(latest.snapshot.taken_at)} · {latest.snapshot.leaves} 条</Text>}
        <Button title="查看我的证明" onPress={() => void client.myInfluenceProof().then(setProof).catch((e) => setError(apiErrorText(e)))} />
        {proof && (proof.snapshot === null ? <Text style={s.muted}>还没有做过快照（每天一次）。</Text> : (
          <View>
            <Text>快照 #{proof.snapshot.id} · {proof.snapshot.leaves} 条 · 存证序号 {proof.snapshot.anchor_seq ?? '—'}</Text>
            {proof.items.map((i) => <Text key={i.category}>{i.category}：{i.points} · {i.verified ? '验证通过' : '验证不通过'}</Text>)}
            {proof.items.length === 0 && <Text style={s.muted}>这次快照里还没有你。</Text>}
          </View>
        ))}
      </View>
    </View>
  );
}

/** 别人空间里的一块：等级、担保汇总、为他担保。取不到（含老服务端）就不显示。 */
export function InfluenceBlock({ client, userId }: { client: PlatformClient; userId: number }) {
  const [inf, setInf] = useState<InfluencePublic | null>(null);
  const [form, setForm] = useState<{ category: string; stake: string } | null>(null);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.resolve().then(() => client.userInfluence(userId))
      .then((x) => setInf(Array.isArray(x?.categories) ? x : null)).catch(() => setInf(null));
  }, [client, userId]);
  if (!inf) return null;
  async function vouch() {
    if (!form) return;
    setError(''); setMsg('');
    try {
      const v = await client.createVouch({ subject_id: userId, category: form.category, stake: Number(form.stake) });
      setMsg(`已用 ${v.stake} 点「${v.category}」影响力为他担保`); setForm(null);
      setInf(await client.userInfluence(userId));
    } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="影响力">
      <Text style={s.title}>影响力</Text>
      {inf.categories.length === 0 && <Text style={s.muted}>还没有在平台上做成过事，暂无影响力。</Text>}
      {inf.categories.map((c) => <Text key={c.category}>{c.category}：{c.tier_name} · 影响力 {c.points} · 完成 {c.completed} 单</Text>)}
      {inf.vouched.map((v) => <Text key={v.category} style={s.muted}>{v.vouchers} 人以 {v.stake} 点为他的「{v.category}」作保</Text>)}
      {form ? (
        <View style={s.box}>
          <TextInput style={s.input} accessibilityLabel="担保类目" value={form.category} onChangeText={(t) => setForm({ ...form, category: t })} />
          <TextInput style={s.input} accessibilityLabel="担保额" keyboardType="numeric" value={form.stake} onChangeText={(t) => setForm({ ...form, stake: t })} />
          <Button title="确认担保" disabled={!form.category || !(Number(form.stake) > 0)} onPress={() => void vouch()} />
        </View>
      ) : <Button title="为他担保" onPress={() => setForm({ category: inf.categories[0]?.category ?? '', stake: '10' })} />}
      <Text style={s.muted}>要你在这个类目是熟手以上；他做成了你得一点，他纠纷败诉你被罚没担保额的一半。</Text>
      {!!msg && <Text accessibilityRole="alert">{msg}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4, alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#777' },
  link: { color: '#2563eb' },
  error: { color: '#b91c1c' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
});
