// SCN-205 App 上的账号交接清单（330 号 spec）：执行方逐项登记要交给发单人的账号，发单人逐项确认「已在我名下」。
// 与 web 的 HandoverBlock 同一份接口、同一句话。
import { apiErrorText, HANDOVER_KIND_LABEL, handoverSummary, type ContractHandoverItem, type HandoverKind, type PlatformClient } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export function HandoverList({ client, contractId, isExecutor = false, isRequester = false, live = false }: {
  client: PlatformClient; contractId: number; isExecutor?: boolean; isRequester?: boolean; live?: boolean;
}) {
  const [rows, setRows] = useState<ContractHandoverItem[]>([]);
  const [kind, setKind] = useState<HandoverKind>('domain');
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setRows(await client.contractHandover(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);
  const canEdit = isExecutor && live;
  if (rows.length === 0 && !canEdit) return null;
  async function run(fn: () => Promise<ContractHandoverItem[]>) {
    setError('');
    try { setRows(await fn()); } catch (e) { setError(apiErrorText(e)); }
  }
  async function add() {
    if (!name.trim()) { setError('写上账号是什么（比如域名 example.com、某某小店小程序）'); return; }
    await run(() => client.addContractHandover(contractId, { kind, name: name.trim(), note: note.trim() }));
    setName(''); setNote('');
  }
  const summary = handoverSummary(rows);
  const allDone = rows.every((r) => r.confirmed_at);
  return (
    <View style={s.card} accessibilityLabel="账号交接">
      <Text style={s.title}>账号交接</Text>
      {!!summary && <Text style={allDone ? s.muted : s.error}>{summary}</Text>}
      {rows.map((r) => (
        <View key={r.id} style={s.row}>
          <Text style={{ flex: 1 }}>
            {HANDOVER_KIND_LABEL[r.kind] ?? '其他账号'}：{r.name}{r.note ? `（${r.note}）` : ''} · {r.confirmed_at ? '已在发单人名下' : '待确认'}
          </Text>
          {isRequester && !r.confirmed_at && (
            <TouchableOpacity onPress={() => void run(() => client.confirmContractHandover(contractId, r.id))}><Text style={s.link}>已在我名下</Text></TouchableOpacity>
          )}
          {canEdit && !r.confirmed_at && (
            <TouchableOpacity onPress={() => void run(() => client.removeContractHandover(contractId, r.id))}><Text style={s.link}>删掉</Text></TouchableOpacity>
          )}
        </View>
      ))}
      {canEdit && (
        <View style={{ gap: 6 }}>
          <View style={s.row} accessibilityLabel="账号类别">
            {(Object.keys(HANDOVER_KIND_LABEL) as HandoverKind[]).map((k) => (
              <Pressable key={k} onPress={() => setKind(k)} accessibilityRole="radio" accessibilityState={{ selected: kind === k }}
                         style={[s.chip, kind === k && s.chipOn]}>
                <Text>{HANDOVER_KIND_LABEL[k]}</Text>
              </Pressable>
            ))}
          </View>
          <TextInput style={s.input} accessibilityLabel="账号" placeholder="账号（如 example.com）" value={name} onChangeText={setName} />
          <TextInput style={s.input} accessibilityLabel="说明" placeholder="说明（可不填）" value={note} onChangeText={setNote} />
          <TouchableOpacity style={s.button} onPress={() => void add()}><Text style={s.buttonText}>登记一项</Text></TouchableOpacity>
        </View>
      )}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#6b7280', fontSize: 13 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  chip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: '#dce5de' },
  chipOn: { backgroundColor: '#e6f0ec', borderColor: '#275c52' },
  link: { color: '#275c52' },
  error: { color: '#b91c1c', fontSize: 13 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  button: { backgroundColor: '#275c52', borderRadius: 10, padding: 12, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '600' },
});
