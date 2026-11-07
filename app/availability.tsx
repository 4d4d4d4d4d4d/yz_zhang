// SPACE-023 可用时段与「少量接单」——App 端（118 号 spec）。
//
// 附近服务（保洁、维修、搬家）的执行方主要在手机上。推荐里会写「截止前有空」，
// 但不会把完整日程给别人看。
import { apiErrorText, type PlatformClient, type WeeklySlot } from '@platform/core';
import { useEffect, useState } from 'react';
import { Button, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';

const WEEK = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$|^24:00$/;

export function AvailabilityScreen({ client }: { client: PlatformClient }) {
  const [slots, setSlots] = useState<WeeklySlot[] | null>(null);
  const [limited, setLimited] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    client.me().then((m) => { setSlots(m.weekly_slots ?? []); setLimited(!!m.limited_capacity); })
      .catch((e) => setError(apiErrorText(e)));
  }, [client]);

  if (slots === null) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  const slotOf = (d: number) => slots.find((x) => x.d === d);
  const put = (d: number, next: WeeklySlot | null) =>
    setSlots([...slots.filter((x) => x.d !== d), ...(next ? [next] : [])].sort((a, b) => a.d - b.d));

  async function save() {
    setMsg(''); setError('');
    if (slots!.some((x) => !HHMM.test(x.from) || !HHMM.test(x.to) || x.to <= x.from)) {
      setError('时间格式为 HH:MM，且结束要晚于开始');
      return;
    }
    try {
      await client.updateMe({ weekly_slots: slots!, limited_capacity: limited });
      setMsg('已保存');
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <View style={s.box}>
      <Text style={s.muted}>推荐里只会写「截止前有空」，不会公开你的完整日程。时间按北京时间。</Text>
      {WEEK.map((w, d) => {
        const x = slotOf(d);
        return (
          <View key={d} style={s.row}>
            <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: !!x }}
              onPress={() => put(d, x ? null : { d, from: '09:00', to: '18:00' })}>
              <Text style={s.day}>{x ? '☑' : '☐'} {w}</Text>
            </TouchableOpacity>
            {x && <>
              <TextInput style={s.input} value={x.from} accessibilityLabel={`${w}开始`} onChangeText={(v) => put(d, { ...x, from: v })} />
              <Text>—</Text>
              <TextInput style={s.input} value={x.to} accessibilityLabel={`${w}结束`} onChangeText={(v) => put(d, { ...x, to: v })} />
            </>}
          </View>
        );
      })}
      <View style={s.row}>
        <Switch value={limited} onValueChange={setLimited} accessibilityLabel="少量接单" />
        <Text style={{ flex: 1 }}>这阵子少量接单（推荐里靠后一点并写明）</Text>
      </View>
      <Button title="保存可用时间" onPress={() => void save()} />
      {!!msg && <Text style={s.ok}>{msg}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  day: { width: 72, fontSize: 15 },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 6, width: 70 },
  muted: { color: '#777' },
  ok: { color: '#2e7d32' },
  error: { color: '#c0392b' },
});
