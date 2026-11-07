// SCN-202 App 上的授权清单（329 号 spec）：执行方在托管期间逐项登记用到的音乐、素材、字体、模板与授权来源；
// 合约双方都看得到。与 web 的 LicensesBlock 同一份接口、同一句话。
import { apiErrorText, LICENSE_KIND_LABEL, licenseLine, type ContractLicenseItem, type LicenseKind, type PlatformClient } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export function LicensesList({ client, contractId, isExecutor = false, live = false }: {
  client: PlatformClient; contractId: number; isExecutor?: boolean; live?: boolean;
}) {
  const [rows, setRows] = useState<ContractLicenseItem[]>([]);
  const [kind, setKind] = useState<LicenseKind>('music');
  const [title, setTitle] = useState('');
  const [source, setSource] = useState('');
  const [scope, setScope] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setRows(await client.contractLicenses(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);
  const canEdit = isExecutor && live;
  if (rows.length === 0 && !canEdit) return null;
  async function add() {
    setError('');
    if (!title.trim() || source.trim().length < 2) { setError('写上名称和授权来源（比如「客户提供」「某曲库商用授权」「开源 MIT」）'); return; }
    try {
      setRows(await client.addContractLicense(contractId, { kind, title: title.trim(), source: source.trim(), scope: scope.trim() }));
      setTitle(''); setSource(''); setScope('');
    } catch (e) { setError(apiErrorText(e)); }
  }
  async function remove(id: number) {
    setError('');
    try { setRows(await client.removeContractLicense(contractId, id)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="授权清单">
      <Text style={s.title}>授权清单</Text>
      {rows.length === 0 && <Text style={s.muted}>交付物里用到别人的音乐、素材、字体、模板，在这里逐项写清授权来源。</Text>}
      {rows.map((r) => (
        <View key={r.id} style={s.row}>
          <Text style={{ flex: 1 }}>{licenseLine(r)}</Text>
          {canEdit && <TouchableOpacity onPress={() => void remove(r.id)}><Text style={s.link}>删掉</Text></TouchableOpacity>}
        </View>
      ))}
      {canEdit && (
        <View style={{ gap: 6 }}>
          <View style={s.row} accessibilityLabel="授权类别">
            {(Object.keys(LICENSE_KIND_LABEL) as LicenseKind[]).map((k) => (
              <Pressable key={k} onPress={() => setKind(k)} accessibilityRole="radio" accessibilityState={{ selected: kind === k }}
                         style={[s.chip, kind === k && s.chipOn]}>
                <Text>{LICENSE_KIND_LABEL[k]}</Text>
              </Pressable>
            ))}
          </View>
          <TextInput style={s.input} accessibilityLabel="名称" placeholder="名称（如《夏日》、思源黑体）" value={title} onChangeText={setTitle} />
          <TextInput style={s.input} accessibilityLabel="授权来源" placeholder="授权来源（客户提供 / 某曲库商用授权 / 开源 MIT）" value={source} onChangeText={setSource} />
          <TextInput style={s.input} accessibilityLabel="授权范围" placeholder="授权范围（可不填）" value={scope} onChangeText={setScope} />
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
