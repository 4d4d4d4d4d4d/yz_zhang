// API-052 App 上看 API Key 用量与设每日配额（152 号 spec）。
import { apiErrorText, formatDateTime, type ApiKeyUsageView, type PlatformClient } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

export function KeyUsageBlock({ client, keyId }: { client: PlatformClient; keyId: number }) {
  const [u, setU] = useState<ApiKeyUsageView | null>(null);
  const [quota, setQuota] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setU(await client.apiKeyUsage(keyId, 7)); } catch (e) { setError(apiErrorText(e)); }
  }, [client, keyId]);
  useEffect(() => { void load(); }, [load]);
  // 载荷不对就不显示这一块，别把整个开发者页拖白
  if (!u || !Array.isArray(u.days)) return error ? <Text style={s.error}>{error}</Text> : null;
  return (
    <View style={s.box} accessibilityLabel={`Key ${keyId} 用量`}>
      <Text>今天（{u.time_zone}）已用 {u.today_used} / {u.effective_daily_quota} 次{u.daily_quota ? '（你设的配额）' : '（平台默认配额）'}，还剩 {u.today_remaining} 次；{formatDateTime(u.resets_at)} 恢复</Text>
      {/* API-054（158 号 spec）多把 Key 不能叠加配额 */}
      {typeof u.account_daily_quota === 'number' && <Text style={s.muted}>账号下所有 Key 今天合计 {u.account_today_used} / {u.account_daily_quota} 次</Text>}
      <Text style={s.muted}>最近 7 天：{u.days.map((d) => `${d.day.slice(5)} ${d.count}${d.rejected ? `（挡回 ${d.rejected}）` : ''}`).join(' · ')}</Text>
      <TextInput style={s.input} accessibilityLabel={`Key ${keyId} 每日配额`} keyboardType="numeric" placeholder="设更低的每日配额（0 = 默认）"
                 value={quota} onChangeText={setQuota} />
      <Button title="保存配额" disabled={quota === ''} onPress={() => void (async () => {
        setError('');
        try { await client.setApiKeyQuota(keyId, Number(quota)); setQuota(''); await load(); } catch (e) { setError(apiErrorText(e)); }
      })()} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 4, paddingVertical: 4 },
  muted: { color: '#6b7280' },
  error: { color: '#b91c1c' },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 6, padding: 8 },
});
