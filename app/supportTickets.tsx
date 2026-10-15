// CS-013 / ESCA-051 App 上的「我的工单」（150 号 spec）：此前 App 上提不了工单、也看不到客服回复；
// 现在能提、能看回复，并且看得到有没有人接手、是否已超时升级（看不到接手的是哪位管理员）。
import { apiErrorText, formatDateTime, type MyTicket, type PlatformClient } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

export function ticketProgress(t: MyTicket): string {
  if (t.status !== 'open') return '';
  const who = t.claimed ? '已有客服接手' : '排队等待客服接手';
  const level = t.escalation_level >= 2 ? ' · 已升级给客服主管跟进' : t.escalation_level === 1 ? ' · 已超时，已催办' : '';
  return `${who} · 已等 ${t.waited_hours} 小时（承诺 ${t.sla_hours} 小时内处理）${level}`;
}

const STATUS: Record<string, string> = { open: '处理中', resolved: '已处理', escalated: '已转纠纷' };

export function SupportTicketsScreen({ client }: { client: PlatformClient }) {
  const [rows, setRows] = useState<MyTicket[]>([]);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    try { setRows(await client.myTickets()); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 12 }}>
      <View style={s.card} accessibilityLabel="提交工单">
        <Text style={s.title}>找客服</Text>
        <TextInput style={s.input} accessibilityLabel="问题概括" placeholder="问题一句话概括" value={subject} onChangeText={setSubject} />
        <TextInput style={s.input} accessibilityLabel="详细描述" placeholder="详细描述（越具体越快解决）" multiline value={body} onChangeText={setBody} />
        <Button title="提交工单" disabled={subject.trim().length < 2} onPress={() => void (async () => {
          setError(''); setNotice('');
          try {
            await client.createTicket(subject.trim(), body.trim());
            setSubject(''); setBody('');
            setNotice('已提交。客服回复会发站内信，也会显示在下面。');
            await load();
          } catch (e) { setError(apiErrorText(e)); }
        })()} />
        {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
        {!!error && <Text style={s.error}>{error}</Text>}
      </View>
      <Text style={s.title}>我的工单（{rows.length}）</Text>
      {rows.length === 0 && <Text style={s.muted}>还没有工单。</Text>}
      {rows.map((t) => (
        <View key={t.id} style={s.card} accessibilityLabel={`工单 ${t.id}`}>
          <Text style={{ fontWeight: '600' }}>{t.subject} · {STATUS[t.status] || t.status}</Text>
          {!!t.body && <Text style={s.muted}>{t.body}</Text>}
          <Text style={s.muted}>{formatDateTime(t.created_at)}</Text>
          {!!t.reply && <Text>客服回复：{t.reply}</Text>}
          {!!ticketProgress(t) && <Text style={s.muted}>{ticketProgress(t)}</Text>}
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 12, gap: 6 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#6b7280' },
  error: { color: '#b91c1c' },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 6, padding: 8 },
});
