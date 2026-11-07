// TEAM-070（226 号 spec）钱包页「团队拨款」：团队拨给我、没用完的可以退回（离开了团队也能退）。
import { OperationKey, TEAM_RETURN_HINT, apiErrorText, teamReturnedNotice, teamReturnLine, type PlatformClient, type ReturnableTeamSpend } from '@platform/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

export function TeamReturnsBlock({ client, onChanged }: { client: PlatformClient; onChanged: () => void }) {
  const [rows, setRows] = useState<ReturnableTeamSpend[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  // 每笔拨款一把「这次操作」的键：信号断了再按是重试，钱只退一次（104 号）
  const keys = useRef(new Map<number, OperationKey>());

  const load = useCallback(async () => {
    const r = await client.returnableTeamSpends().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function giveBack(r: ReturnableTeamSpend) {
    setError(''); setNotice('');
    const cents = Math.round(parseFloat(amounts[r.id] ?? String(r.returnable_cents / 100)) * 100);
    if (!(cents > 0)) { setError('退回金额要大于 0'); return; }
    if (!keys.current.has(r.id)) keys.current.set(r.id, new OperationKey());
    try {
      const out = await keys.current.get(r.id)!.run(`${r.id}:${cents}`, (k) => client.returnTeamSpend(r.team_id, r.id, cents, k));
      setNotice(teamReturnedNotice(cents, out));
      setAmounts((a) => { const n = { ...a }; delete n[r.id]; return n; });
      await load();
      onChanged();
    } catch (e) { setError(apiErrorText(e)); }
  }

  if (rows.length === 0 && !notice) return null;
  return (
    <View style={s.card} accessibilityLabel="团队拨款">
      <Text style={s.title}>团队拨款</Text>
      <Text style={s.muted}>{TEAM_RETURN_HINT}</Text>
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {rows.map((r) => (
        <View key={r.id} style={{ gap: 4 }}>
          <Text>{teamReturnLine(r)}</Text>
          <TextInput style={s.input} keyboardType="numeric" accessibilityLabel={`退回金额 ${r.id}`}
                     value={amounts[r.id] ?? String(r.returnable_cents / 100)}
                     onChangeText={(v) => setAmounts({ ...amounts, [r.id]: v })} />
          <Button title="退回团队" onPress={() => void giveBack(r)} />
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#777' },
  error: { color: '#b91c1c' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 8 },
});
