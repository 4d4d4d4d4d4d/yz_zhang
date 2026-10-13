// GIG-100 接单（125 号 spec）——App 端：现在有空（附近新单推给我）、附近的单与行情、常用地点与顺路单。
// 位置只用到约 1 公里；「现在有空」到点自动关掉、位置随之删除；距离都是直线估算。
import {
  apiErrorText, fmtYuan, formatDateTime,
  type GigAlong, type GigAvailabilityView, type GigNearby, type GigPlaceRow, type GigQuote, type GigTaskCard, type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

export type Locate = () => Promise<{ lat: number; lng: number } | null>;

/** 拿不到定位就返回 null：「现在有空」不能拿 0,0 去推单。 */
const deviceLocate: Locate = async () => {
  try {
    const Location = await import('expo-location');
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== 'granted') return null;
    const pos = await Location.getCurrentPositionAsync({});
    return { lat: pos.coords.latitude, lng: pos.coords.longitude };
  } catch {
    return null;
  }
};

export function GigScreen({ client, locate = deviceLocate, onOpenTask }: {
  client: PlatformClient; locate?: Locate; onOpenTask?: (taskId: number) => void;
}) {
  const [avail, setAvail] = useState<GigAvailabilityView | null>(null);
  const [radius, setRadius] = useState(5);
  const [near, setNear] = useState<GigNearby | null>(null);
  const [places, setPlaces] = useState<GigPlaceRow[]>([]);
  const [to, setTo] = useState<number | null>(null);
  const [along, setAlong] = useState<GigAlong | null>(null);
  const [quote, setQuote] = useState<GigQuote | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      const a = await client.gigAvailability();
      setAvail(a);
      setPlaces(await client.gigPlaces());
      setNear(a.available ? await client.gigNearby() : null);
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function withHere(fn: (here: { lat: number; lng: number }) => Promise<string>) {
    setError(''); setNotice('');
    const here = await locate();
    if (!here) { setError('没拿到位置：请在系统设置里允许使用定位'); return; }
    try { setNotice(await fn(here)); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const showQuote = (id: number) => void client.gigQuote({ task_id: id }).then(setQuote).catch((e) => setError(apiErrorText(e)));

  return (
    <View style={s.box}>
      <Text style={s.muted}>位置只用到约 1 公里，距离是直线估算。</Text>
      {avail?.available ? (
        <View style={s.card}>
          <Text style={s.title}>现在有空：{avail.radius_km} 公里内，到 {formatDateTime(avail.until)}（已推 {avail.pushed} 条）</Text>
          <Button title="不接了" onPress={() => void client.stopGigAvailable().then(() => { setNear(null); setNotice('已关掉，位置已删除'); return load(); })} />
        </View>
      ) : (
        <View style={s.card}>
          <View style={s.row}>
            {[1, 3, 5, 10].map((n) => (
              <TouchableOpacity key={n} onPress={() => setRadius(n)} accessibilityState={{ selected: radius === n }}>
                <Text style={radius === n ? s.tabOn : s.tab}>{n} 公里</Text>
              </TouchableOpacity>
            ))}
          </View>
          <Button title="我现在有空（2 小时）" onPress={() => void withHere(async (here) => {
            await client.setGigAvailable({ ...here, radius_km: radius, hours: 2 });
            return '好的：接下来 2 小时附近有新单就推给你';
          })} />
        </View>
      )}
      {near && <Cards items={near.items} empty="附近暂时没有招募中的单" onQuote={showQuote} onOpen={onOpenTask} />}

      <Text style={s.h}>顺路单</Text>
      <View style={s.row}>
        {places.map((p) => (
          <TouchableOpacity key={p.id} onPress={() => setTo(p.id)} accessibilityState={{ selected: to === p.id }}>
            <Text style={to === p.id ? s.tabOn : s.tab}>到{p.name}</Text>
          </TouchableOpacity>
        ))}
        {['家', '公司'].filter((n) => !places.some((p) => p.name === n)).map((n) => (
          <TouchableOpacity key={n} onPress={() => void withHere(async (here) => {
            await client.addGigPlace(n, here.lat, here.lng);
            return `已把这里存为「${n}」`;
          })}><Text style={s.link}>把这里存为「{n}」</Text></TouchableOpacity>
        ))}
      </View>
      {to !== null && (
        <Button title="从这里出发，看顺路的单" onPress={() => void withHere(async (here) => {
          const r = await client.gigAlong({ to_place: to, from_lat: here.lat, from_lng: here.lng, max_detour_km: 2 });
          setAlong(r);
          return '';
        })} />
      )}
      {along && <Cards items={along.items} empty={`去「${along.to}」的路上暂时没有顺路的单`} onQuote={showQuote} onOpen={onOpenTask} />}
      {quote && (
        <View style={s.card}>
          <Text style={s.title}>报价参考：{quote.category}</Text>
          {quote.basis.map((b) => <Text key={b}>· {b}</Text>)}
          <Text style={s.muted}>{quote.disclaimer}</Text>
        </View>
      )}
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

function Cards({ items, empty, onQuote, onOpen }: {
  items: GigTaskCard[]; empty: string; onQuote: (id: number) => void; onOpen?: (id: number) => void;
}) {
  if (!items.length) return <Text style={s.muted}>{empty}</Text>;
  return (
    <View style={s.box}>
      {items.map((t) => (
        <View key={t.task_id} style={s.card}>
          <TouchableOpacity onPress={() => onOpen?.(t.task_id)}><Text style={s.title}>{t.title}</Text></TouchableOpacity>
          <Text style={s.muted}>
            {t.category} · {t.address_hint}
            {t.distance_m !== undefined ? ` · 约 ${(t.distance_m / 1000).toFixed(1)} 公里` : ''}
            {t.detour_m !== undefined ? ` · 多走约 ${(t.detour_m / 1000).toFixed(1)} 公里` : ''} · 到手约 {fmtYuan(t.net_cents)}
          </Text>
          <TouchableOpacity onPress={() => onQuote(t.task_id)}><Text style={s.link}>看行情</Text></TouchableOpacity>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  tab: { paddingVertical: 6, paddingHorizontal: 10, color: '#666' },
  tabOn: { paddingVertical: 6, paddingHorizontal: 10, color: '#b5532f', fontWeight: '600' },
  card: { borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4 },
  title: { fontSize: 15, fontWeight: '600' },
  h: { fontSize: 16, fontWeight: '600', marginTop: 6 },
  muted: { color: '#777' },
  error: { color: '#c0392b' },
  link: { color: '#b5532f' },
});
