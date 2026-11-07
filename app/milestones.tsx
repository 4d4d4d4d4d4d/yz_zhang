// SC-004 / SC-014 分期在 App 上（146 号 spec）。
// 此前 App 的整单验收提示写着「请用下面分期列表里的『验收本期』」——而 App 上**根本没有分期列表**。
// 这里补上：执行方逐期交付；发布方逐期验收，或一次只放已交付的那几期（没交付的不动）。
import { OperationKey, apiErrorText, fmtYuan, type Contract, type PlatformClient } from '@platform/core';
import { useRef, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

const STATUS: Record<string, string> = { pending: '进行中', delivered: '待验收', released: '已放款' };

export function MilestonesBlock({ client, contract, isCreator, isExecutor, onChanged }: {
  client: PlatformClient; contract: Contract; isCreator: boolean; isExecutor: boolean; onChanged: (c: Contract) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  // SC-015（296 号 spec）一次交付多期
  const [delivering, setDelivering] = useState(false);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  // SC-016（225 号 spec）批量放款的幂等键：信号断了再点一次是重试，钱只放一次
  const releaseKey = useRef(new OperationKey());
  const ms = contract.milestones ?? [];
  if (ms.length < 2) return null;
  const live = contract.status === 'funded' && !contract.frozen;
  const delivered = ms.filter((m) => m.status === 'delivered');
  const pending = ms.filter((m) => m.status === 'pending');
  const sum = delivered.reduce((n, m) => n + m.amount_cents, 0);
  async function act(fn: () => Promise<Contract>) {
    setError('');
    try { onChanged(await fn()); setConfirming(false); setDelivering(false); setNote(''); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="分期">
      <Text style={s.title}>分期</Text>
      {ms.map((m) => (
        <View key={m.idx} style={s.row}>
          <Text style={{ flex: 1 }}>第 {m.idx} 期 {m.title} · {fmtYuan(m.amount_cents)} · {STATUS[m.status] ?? m.status}{m.delivery_note ? `\n交付说明：${m.delivery_note}` : ''}</Text>
          {isExecutor && live && m.status === 'pending' && (
            <Button title="交付本期" onPress={() => void act(() => client.deliverMilestone(contract.id, m.idx))} />
          )}
          {isCreator && live && m.status === 'delivered' && (
            <Button title="验收本期" onPress={() => void act(() => client.acceptMilestone(contract.id, m.idx))} />
          )}
        </View>
      ))}
      {isExecutor && live && pending.length >= 2 && (delivering ? (
        <View style={{ gap: 6 }}>
          <Text style={s.title}>一次交付这 {pending.length} 期</Text>
          {pending.map((m) => <Text key={m.idx}>· 第 {m.idx} 期 {m.title} {fmtYuan(m.amount_cents)}</Text>)}
          <TextInput accessibilityLabel="交付说明" placeholder="交付说明（几期共用，可不写）" value={note} onChangeText={setNote} maxLength={500} style={s.input} />
          <Button title="确认交付" onPress={() => void act(() => client.deliverMilestones(contract.id, pending.map((m) => m.idx), note.trim()))} />
          <Button title="再想想" color="#6b7280" onPress={() => setDelivering(false)} />
        </View>
      ) : (
        <Button title={`一次交付进行中的 ${pending.length} 期`} onPress={() => setDelivering(true)} />
      ))}
      {isCreator && live && delivered.length >= 2 && (confirming ? (
        <View style={{ gap: 6 }}>
          <Text style={s.title}>只放这 {delivered.length} 期已交付的，合计 {fmtYuan(sum)}</Text>
          {delivered.map((m) => <Text key={m.idx}>· 第 {m.idx} 期 {m.title} {fmtYuan(m.amount_cents)}</Text>)}
          <Text style={s.muted}>还没交付的期不会动。</Text>
          <Button title="确认放款" onPress={() => void act(() => releaseKey.current.run(`${contract.id}:${delivered.map((m) => m.idx).join(',')}:${sum}`,
            (key) => client.releaseDelivered(contract.id, delivered.map((m) => m.idx), sum, key)))} />
          <Button title="再想想" color="#6b7280" onPress={() => setConfirming(false)} />
        </View>
      ) : (
        <Button title={`放款已交付的 ${delivered.length} 期（共 ${fmtYuan(sum)}）`} onPress={() => setConfirming(true)} />
      ))}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#777' },
  error: { color: '#b91c1c' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 8 },
});
