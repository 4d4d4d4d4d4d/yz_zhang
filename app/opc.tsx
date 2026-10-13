// OPC-100 一人公司（124 号 spec）——App 端：导入平台收入、记一笔、本季汇总、申报日历（放进工作台）、合同体检、主体设置。
// 只出底稿与提醒：报税、开票、签字由本人在官方渠道完成。
import {
  apiErrorText, chinaDateAt, chinaQuarter, chinaToday, fmtYuan,
  type ContractReview, type OpcCalendar, type OpcProfileView, type OpcSummary, type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Tab = 'books' | 'calendar' | 'contract' | 'profile';
const ENTITY: [OpcProfileView['entity'], string][] = [['individual', '个人'], ['sole_prop', '个体工商户'], ['company', '公司']];

export function OpcScreen({ client }: { client: PlatformClient }) {
  const [tab, setTab] = useState<Tab>('books');
  return (
    <View style={s.box}>
      <Text style={s.muted}>只出底稿与提醒：报税、开票、签字由你本人在官方渠道完成。</Text>
      <View style={s.row}>
        {([['books', '账本与汇总'], ['calendar', '申报日历'], ['contract', '合同体检'], ['profile', '主体设置']] as [Tab, string][]).map(([t, label]) => (
          <TouchableOpacity key={t} onPress={() => setTab(t)} accessibilityRole="tab" accessibilityState={{ selected: tab === t }}>
            <Text style={tab === t ? s.tabOn : s.tab}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {tab === 'books' && <Books client={client} />}
      {tab === 'calendar' && <Calendar client={client} />}
      {tab === 'contract' && <Contract client={client} />}
      {tab === 'profile' && <Profile client={client} />}
    </View>
  );
}

function Books({ client }: { client: PlatformClient }) {
  const [sum, setSum] = useState<OpcSummary | null>(null);
  const [yuan, setYuan] = useState('');
  const [category, setCategory] = useState('');
  const [kind, setKind] = useState<'income' | 'expense'>('expense');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setSum(await client.opcSummary(chinaQuarter())); } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  async function act(fn: () => Promise<string>) {
    setError(''); setNotice('');
    try { setNotice(await fn()); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const cents = Math.round(Number(yuan) * 100);
  return (
    <View style={s.box}>
      <Button title="导入平台收入" onPress={() => void act(async () => `导入了 ${(await client.importPlatformIncome()).imported} 笔平台收入`)} />
      <View style={s.row}>
        <TouchableOpacity onPress={() => setKind(kind === 'income' ? 'expense' : 'income')}><Text style={s.link}>{kind === 'income' ? '收入' : '支出'} ⇄</Text></TouchableOpacity>
        <TextInput style={[s.input, { flex: 1 }]} placeholder="金额（元）" keyboardType="decimal-pad" value={yuan} onChangeText={setYuan} />
        <TextInput style={[s.input, { flex: 1 }]} placeholder="类别" value={category} onChangeText={setCategory} />
      </View>
      <Button title="记一笔" disabled={!(cents > 0)} onPress={() => void act(async () => {
        await client.addOpcEntry({ occurred_on: chinaToday(), kind, amount_cents: cents, category });
        setYuan('');
        return '记上了';
      })} />
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {sum && (
        <View style={s.card}>
          <Text style={s.title}>{sum.period}：收入 {fmtYuan(sum.income_cents)} · 支出 {fmtYuan(sum.expense_cents)}</Text>
          {sum.vat_check && <Text style={sum.vat_check.over ? s.error : undefined}>免税标准 {fmtYuan(sum.vat_check.sales_cents)} / {fmtYuan(sum.vat_check.limit_cents)}{sum.vat_check.over ? '（已超过）' : '（未超过）'}</Text>}
          {sum.notes.map((n) => <Text key={n}>· {n}</Text>)}
          <Text style={s.muted}>{sum.disclaimer}</Text>
        </View>
      )}
    </View>
  );
}

function Calendar({ client }: { client: PlatformClient }) {
  const [cal, setCal] = useState<OpcCalendar | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { client.opcCalendar(120).then(setCal).catch((e) => setError(apiErrorText(e))); }, [client]);
  if (!cal) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  return (
    <View style={s.box}>
      {!cal.configured && <Text style={s.muted}>还没填主体设置，下面按「个人」推算。</Text>}
      <Text style={s.muted}>{cal.notice}</Text>
      {cal.items.map((i) => (
        <View key={`${i.date}${i.title}`} style={s.card}>
          <Text style={s.title}>{i.date} {i.title}</Text>
          <Text style={s.muted}>{i.detail}</Text>
          <TouchableOpacity onPress={() => void client.createWorkbenchItem({ title: i.title, priority: 2, category: '财税',
            due_at: chinaDateAt(i.date), remind_at: chinaDateAt(i.date, '18:00', 3) })
            .then(() => setNotice(`已放进工作台：${i.title}`)).catch((e) => setError(apiErrorText(e)))}>
            <Text style={s.link}>放进工作台（提前 3 天提醒）</Text>
          </TouchableOpacity>
        </View>
      ))}
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

function Contract({ client }: { client: PlatformClient }) {
  const [text, setText] = useState('');
  const [r, setR] = useState<ContractReview | null>(null);
  const [error, setError] = useState('');
  return (
    <View style={s.box}>
      <Text style={s.muted}>把合同全文贴进来（按接活一方的视角看）。原文不保存。</Text>
      <TextInput style={[s.input, { minHeight: 120 }]} multiline placeholder="合同全文" value={text} onChangeText={setText} />
      <Button title="体检" disabled={text.trim().length < 20} onPress={() => void client.reviewContract(text, 'party_b').then(setR).catch((e) => setError(apiErrorText(e)))} />
      {!!error && <Text style={s.error}>{error}</Text>}
      {r && (
        <View style={s.card}>
          {!r.findings.length && <Text>按清单没看到明显问题。</Text>}
          {r.findings.map((f, n) => (
            <Text key={n}><Text style={f.level === 'high' ? s.error : s.title}>[{f.level === 'high' ? '要改' : '注意'}] {f.clause}</Text>：{f.finding}。建议：{f.suggestion}</Text>
          ))}
          <Text style={s.muted}>{r.disclaimer}</Text>
        </View>
      )}
    </View>
  );
}

function Profile({ client }: { client: PlatformClient }) {
  const [p, setP] = useState<OpcProfileView | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { client.opcProfile().then(setP).catch((e) => setError(apiErrorText(e))); }, [client]);
  if (!p) return <Text style={s.muted}>{error || '正在加载…'}</Text>;
  const vatOptions: [OpcProfileView['vat'], string][] = p.entity === 'individual' ? [['none', '不是纳税人']] : [['small_scale', '小规模纳税人'], ['general', '一般纳税人']];
  return (
    <View style={s.box}>
      <View style={s.row}>{ENTITY.map(([k, label]) => (
        <TouchableOpacity key={k} onPress={() => setP({ ...p, entity: k, vat: k === 'individual' ? 'none' : (p.vat === 'none' ? 'small_scale' : p.vat) })}
          accessibilityState={{ selected: p.entity === k }}><Text style={p.entity === k ? s.tabOn : s.tab}>{label}</Text></TouchableOpacity>
      ))}</View>
      <View style={s.row}>{vatOptions.map(([k, label]) => (
        <TouchableOpacity key={k} onPress={() => setP({ ...p, vat: k })} accessibilityState={{ selected: p.vat === k }}>
          <Text style={p.vat === k ? s.tabOn : s.tab}>{label}</Text></TouchableOpacity>
      ))}</View>
      {p.vat === 'small_scale' && (
        <TouchableOpacity onPress={() => setP({ ...p, vat_period: p.vat_period === 'quarter' ? 'month' : 'quarter' })}>
          <Text style={s.link}>申报周期：{p.vat_period === 'quarter' ? '按季' : '按月'} ⇄</Text>
        </TouchableOpacity>
      )}
      <Button title="保存" onPress={() => void client.saveOpcProfile({ entity: p.entity, vat: p.vat, vat_period: p.vat_period, small_low_profit: p.small_low_profit })
        .then((x) => { setP(x); setNotice('已保存'); }).catch((e) => setError(apiErrorText(e)))} />
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  tab: { paddingVertical: 6, paddingHorizontal: 10, color: '#666' },
  tabOn: { paddingVertical: 6, paddingHorizontal: 10, color: '#b5532f', fontWeight: '600' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 8 },
  card: { borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4 },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#777' },
  error: { color: '#c0392b' },
  link: { color: '#b5532f' },
});
