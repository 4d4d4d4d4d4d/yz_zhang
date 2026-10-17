// SC-004 / SC-014 分期在 App 上（146 号 spec）。
// 此前 App 的整单验收提示写着「请用下面分期列表里的『验收本期』」——而 App 上**根本没有分期列表**。
// 这里补上：执行方逐期交付；发布方逐期验收，或一次只放已交付的那几期（没交付的不动）。
import { apiErrorText, fmtYuan, type Contract, type PlatformClient } from '@platform/core';
import { useState } from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';

const STATUS: Record<string, string> = { pending: '进行中', delivered: '待验收', released: '已放款' };

export function MilestonesBlock({ client, contract, isCreator, isExecutor, onChanged }: {
  client: PlatformClient; contract: Contract; isCreator: boolean; isExecutor: boolean; onChanged: (c: Contract) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  const ms = contract.milestones ?? [];
  if (ms.length < 2) return null;
  const live = contract.status === 'funded' && !contract.frozen;
  const delivered = ms.filter((m) => m.status === 'delivered');
  const sum = delivered.reduce((n, m) => n + m.amount_cents, 0);
  async function act(fn: () => Promise<Contract>) {
    setError('');
    try { onChanged(await fn()); setConfirming(false); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="分期">
      <Text style={s.title}>分期</Text>
      {ms.map((m) => (
        <View key={m.idx} style={s.row}>
          <Text style={{ flex: 1 }}>第 {m.idx} 期 {m.title} · {fmtYuan(m.amount_cents)} · {STATUS[m.status] ?? m.status}</Text>
          {isExecutor && live && m.status === 'pending' && (
            <Button title="交付本期" onPress={() => void act(() => client.deliverMilestone(contract.id, m.idx))} />
          )}
          {isCreator && live && m.status === 'delivered' && (
            <Button title="验收本期" onPress={() => void act(() => client.acceptMilestone(contract.id, m.idx))} />
          )}
        </View>
      ))}
      {isCreator && live && delivered.length >= 2 && (confirming ? (
        <View style={{ gap: 6 }}>
          <Text style={s.title}>只放这 {delivered.length} 期已交付的，合计 {fmtYuan(sum)}</Text>
          {delivered.map((m) => <Text key={m.idx}>· 第 {m.idx} 期 {m.title} {fmtYuan(m.amount_cents)}</Text>)}
          <Text style={s.muted}>还没交付的期不会动。</Text>
          <Button title="确认放款" onPress={() => void act(() => client.releaseDelivered(contract.id, delivered.map((m) => m.idx), sum))} />
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
});
