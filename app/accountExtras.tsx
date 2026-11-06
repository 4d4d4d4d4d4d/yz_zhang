// APP-074（418 号 spec）网页早就有、App 一直没有的三件事：
//
// - 登录设备：手机丢了、借给别人登过，网页上能把那台设备踢下线，App 上看不到也踢不掉；
// - 通知已读：App 的通知列表不分已读未读，顶栏「通知」也没有未读数——
//   V100 的催办、临期、预警全靠用户看见，看不出哪些是新的，等于没提醒；
// - 券：领券和「我的券」只在网页，托管资金时能用券，App 用户却不知道自己有券。
//
// 规则都在服务端与 SDK：下线是服务端吊销那个会话；券的写法用 SDK 的 couponValueText，与网页一致。
import {
  apiErrorText, asList, COUPON_STATUS_LABEL, couponTermsText, couponValueText, formatDate, formatDateTime,
  type CouponTemplate, type MyCoupon, type Notice, type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

type Session = { id: number; device: string; created_at: string };

/** ACC-005 登录设备：列出在登的设备，可以把某一台下线。 */
export function DeviceSessionsBlock({ client }: { client: PlatformClient }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setSessions(asList<Session>(await client.mySessions().catch(() => [])));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  if (sessions.length === 0) return null;
  return (
    <View style={s.card}>
      <Text style={s.title}>登录设备（{sessions.length}）</Text>
      <Text style={s.muted}>不认识的设备点「下线」，再去改密码。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {sessions.map((x) => (
        <View key={x.id} style={s.row}>
          <Text style={[s.muted, { flex: 1 }]}>{(x.device || '').slice(0, 60) || '未知设备'} · {formatDateTime(x.created_at)}</Text>
          <TouchableOpacity style={s.ghost} onPress={async () => {
            setError('');
            try {
              await client.revokeSession(x.id);
              await load();
            } catch (e) {
              setError(apiErrorText(e));
            }
          }}>
            <Text>下线</Text>
          </TouchableOpacity>
        </View>
      ))}
    </View>
  );
}

/** GRW 券：可领的与我的。托管资金时可选用一张券，一单限用一张。 */
export function CouponsBlock({ client }: { client: PlatformClient }) {
  const [offers, setOffers] = useState<CouponTemplate[]>([]);
  const [mine, setMine] = useState<MyCoupon[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const [o, m] = await Promise.all([client.availableCoupons().catch(() => null), client.myCoupons().catch(() => null)]);
    setOffers(asList<CouponTemplate>(o?.coupons));
    setMine(asList<MyCoupon>(m?.coupons));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  if (offers.length === 0 && mine.length === 0) return null;
  return (
    <View style={s.card}>
      <Text style={s.title}>券</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {offers.map((c) => (
        <View key={`o${c.id}`} style={s.row}>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{c.title}</Text>
            <Text style={s.muted}>{[couponValueText(c), couponTermsText(c)].filter(Boolean).join(' · ')}</Text>
          </View>
          <TouchableOpacity style={s.ghost} onPress={async () => {
            setError('');
            try {
              await client.claimCoupon(c.id);
              await load();
            } catch (e) {
              setError(apiErrorText(e));
            }
          }}>
            <Text>领取</Text>
          </TouchableOpacity>
        </View>
      ))}
      {mine.map((c) => (
        <View key={`m${c.id}`} style={s.row}>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{c.title}</Text>
            <Text style={s.muted}>{couponValueText(c)} · 有效期至 {formatDate(c.expires_at)}</Text>
          </View>
          <Text style={c.status === 'unused' ? s.ok : s.muted}>{COUPON_STATUS_LABEL[c.status] ?? c.status}</Text>
        </View>
      ))}
      {mine.length > 0 && <Text style={s.muted}>托管资金时可选用一张券，一单限用一张；订单取消后券自动退回。</Text>}
    </View>
  );
}

/** NTF 通知列表：未读的在视觉上区分；点一条就记成已读（从通知中心点开）；可全部标为已读。 */
export function NoticesList({ client, onChanged }: { client: PlatformClient; onChanged?: () => void }) {
  const [notes, setNotes] = useState<Notice[]>([]);
  const load = useCallback(async () => {
    setNotes(asList<Notice>(await client.notifications().catch(() => [])));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  const unread = notes.filter((n) => !n.is_read).length;
  const done = async () => { await load(); onChanged?.(); };
  return (
    <View>
      {unread > 0 && (
        <TouchableOpacity style={s.ghost} onPress={async () => { await client.markAllRead().catch(() => null); await done(); }}>
          <Text>全部标为已读（未读 {unread}）</Text>
        </TouchableOpacity>
      )}
      {notes.length === 0 && <Text style={s.muted}>暂无通知</Text>}
      {notes.map((n) => (
        <TouchableOpacity key={n.id} testID={`notice-${n.id}`} style={[s.card, n.is_read ? s.read : null]}
                          onPress={async () => {
                            if (n.is_read) return;
                            await client.markRead(n.id, 'center').catch(() => null);
                            await done();
                          }}>
          <Text style={s.name}>{n.is_read ? '' : '● '}{n.title}</Text>
          <Text style={s.muted}>{n.body}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 12, marginVertical: 6 },
  read: { opacity: 0.55 },
  title: { fontWeight: '600', marginBottom: 4 },
  name: { fontWeight: '600' },
  muted: { color: '#6b7280', marginVertical: 2 },
  ok: { color: '#15803d' },
  error: { color: '#b91c1c', marginVertical: 4 },
  row: { flexDirection: 'row', alignItems: 'center', marginVertical: 4 },
  ghost: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4, marginVertical: 4, alignSelf: 'flex-start' },
});
