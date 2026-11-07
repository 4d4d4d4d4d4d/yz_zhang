// SCN-122 服务对象自己看进度在 App 上（356 号 spec）：替别人发的单，发单人生成一条免登录只读链接交给系统分享（微信等），
// 服务对象在浏览器里打开网页 /r/令牌。与 web 的 RecipientLinkPanel 同一份接口、同一句话。
import { RECIPIENT_LINK_DAYS, apiErrorText, recipientLinkLine, recipientLinkUrl, type PlatformClient, type RecipientLinkStatus, type Task } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, Share, StyleSheet, Text, View } from 'react-native';

// 网页地址：部署时配 EXPO_PUBLIC_WEB_URL；没配时用 API 地址（网页与 API 同源部署时就是同一个）
const WEB_ORIGIN = (process.env.EXPO_PUBLIC_WEB_URL || process.env.EXPO_PUBLIC_API_BASE_URL || '').replace(/\/$/, '');

export function canShareRecipientLink(task: Pick<Task, 'on_behalf' | 'status' | 'creator_id'>, meId: number | null | undefined): boolean {
  return !!task.on_behalf && meId === task.creator_id && !['completed', 'cancelled'].includes(task.status);
}

export function RecipientLinkBlock({ client, taskId, origin = WEB_ORIGIN, share = Share.share }: {
  client: PlatformClient; taskId: number; origin?: string; share?: (c: { message: string }) => Promise<unknown>;
}) {
  const [status, setStatus] = useState<RecipientLinkStatus | null>(null);
  const [days, setDays] = useState<number>(7);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(() => {
    client.recipientLink(taskId).then(setStatus).catch((e) => setError(apiErrorText(e)));
  }, [client, taskId]);
  useEffect(load, [load]);
  const active = status?.state === 'active';
  return (
    <View style={s.card} accessibilityLabel="服务对象进度链接">
      <Text style={s.title}>给服务对象一条进度链接</Text>
      <Text style={s.muted}>{recipientLinkLine(status)}</Text>
      <Text style={s.muted}>对方只看得到：谁来、哪天几点、到没到；看不到电话、地址、价钱和照片。</Text>
      <View style={s.row}>
        {RECIPIENT_LINK_DAYS.map((d) => (
          <Pressable key={d} accessibilityRole="radio" accessibilityLabel={`有效 ${d} 天`} accessibilityState={{ selected: d === days }}
                     onPress={() => setDays(d)}>
            <Text style={d === days ? s.chipOn : s.chip}>{d} 天</Text>
          </Pressable>
        ))}
      </View>
      <Pressable accessibilityRole="button" onPress={() => void (async () => {
        setError(''); setNotice('');
        if (!origin) { setError('这个版本没有配置网页地址，生成的链接对方打不开：请在网页上生成'); return; }
        try {
          const r = await client.createRecipientLink(taskId, days);
          setStatus(r);
          await share({ message: `这单的进度在这里看，不用登录：${recipientLinkUrl(origin, r.path)}` });
          setNotice('已生成并交给系统分享。链接只显示这一次，丢了就重新生成（旧的会作废）。');
        } catch (e) { setError(apiErrorText(e)); }
      })()}><Text style={s.link}>{active ? '重新生成并分享（旧的作废）' : '生成并分享链接'}</Text></Pressable>
      {active && (
        <Pressable accessibilityRole="button" onPress={() => void (async () => {
          setError(''); setNotice('');
          try { setStatus(await client.revokeRecipientLink(taskId)); setNotice('已作废，对方再打开会看到「链接已作废」。'); } catch (e) { setError(apiErrorText(e)); }
        })()}><Text style={s.danger}>作废链接</Text></Pressable>
      )}
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 12, gap: 6, borderWidth: 1, borderColor: '#e5e7eb' },
  title: { fontSize: 15, fontWeight: '600', color: '#111827' },
  row: { flexDirection: 'row', gap: 8 },
  chip: { color: '#374151', borderWidth: 1, borderColor: '#d1d5db', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  chipOn: { color: '#fff', backgroundColor: '#2563eb', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  link: { color: '#2563eb', fontSize: 14, paddingVertical: 4 },
  danger: { color: '#b91c1c', fontSize: 14, paddingVertical: 4 },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
});
