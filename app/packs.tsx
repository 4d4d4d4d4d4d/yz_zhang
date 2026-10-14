// PACK-100 服务包（123 号 spec）——App 端：浏览、启用 / 升级 / 停用、问助手专家、反馈。
import {
  apiErrorText, type AssistantContract, type PackAnswer, type PlatformClient, type ScenarioPackCard,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

const SEGMENT: Record<string, string> = {
  opc: '一人公司', gig: '接单者', creator: '创作者', studio: '工作室', buyer: '发单方', general: '所有人',
};

export function PacksScreen({ client, onPublish }: { client: PlatformClient; onPublish?: (category: string) => void }) {
  const [cards, setCards] = useState<ScenarioPackCard[]>([]);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => { client.scenarioPacks().then(setCards).catch((e) => setError(apiErrorText(e))); }, [client, version]);
  const open = cards.find((c) => c.key === openKey);
  if (open) return <Detail client={client} card={open} onBack={() => setOpenKey(null)} onChanged={refresh} onPublish={onPublish} />;
  return (
    <View style={s.box}>
      <Text style={s.muted}>每个服务包解决一类人的一件麻烦事。启用后复制进你的知识库和工作台，之后就是你自己的。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {!cards.length && <Text style={s.muted}>还没有上线的服务包。</Text>}
      {cards.map((c) => (
        <TouchableOpacity key={c.key} style={s.card} onPress={() => setOpenKey(c.key)}>
          <Text style={s.title}>{c.title}{c.enabled ? '（已启用）' : ''}</Text>
          <Text style={s.muted}>{SEGMENT[c.segment] ?? c.segment} · {c.active_users} 人在用{c.upgrade_available ? ' · 有新版本' : ''}</Text>
          <Text>{c.summary}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

function Detail({ client, card, onBack, onChanged, onPublish }: {
  client: PlatformClient; card: ScenarioPackCard; onBack: () => void; onChanged: () => void; onPublish?: (category: string) => void;
}) {
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [voted, setVoted] = useState(false);
  async function run(fn: () => Promise<string>) {
    setError(''); setNotice('');
    try { setNotice(await fn()); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.box}>
      <TouchableOpacity onPress={onBack}><Text style={s.link}>← 全部服务包</Text></TouchableOpacity>
      <Text style={s.title}>{card.title}（第 {card.version} 版）</Text>
      <Text>{card.summary}</Text>
      {card.pains.map((p) => <Text key={p}>· {p}</Text>)}
      {(!card.enabled || card.upgrade_available) && (
        <Button title={card.upgrade_available ? '升级（只补新增的）' : '启用'} onPress={() => void run(async () => {
          const r = await client.enablePack(card.key);
          return `已启用：${r.installed.methods} 份做法、${r.installed.notes} 条知识、${r.installed.routines} 个定时提醒`;
        })} />
      )}
      {card.enabled && (
        <Button title="停用（装进来的留着）" onPress={() => void run(async () => {
          await client.disablePack(card.key, false);
          return '已停用：定时提醒已关掉';
        })} />
      )}
      {!!notice && <Text>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {card.assets.assistants.map((a) => (
        <AssistantBox key={a.key} client={client} packKey={card.key} assistantKey={a.key} name={a.name}
          persona={a.persona} gates={a.human_gates} onPublish={onPublish} />
      ))}
      <Text style={s.h}>做法清单</Text>
      {card.assets.methods.map((m) => <Text key={m.key}>· {m.name}（{m.steps} 步）</Text>)}
      <Text style={s.h}>知识</Text>
      {card.assets.knowledge.map((k) => <Text key={k.key}>· {k.title}<Text style={s.muted}>（出处：{k.source}{k.valid_until ? `；有效期至 ${k.valid_until}` : ''}）</Text></Text>)}
      {voted ? <Text style={s.muted}>谢谢，已记下</Text> : (
        <View style={s.row}>
          <Text style={s.muted}>有用吗？</Text>
          <Button title="有用" onPress={() => void client.packFeedback(card.key, true).then(() => setVoted(true))} />
          <Button title="没用" onPress={() => void client.packFeedback(card.key, false).then(() => setVoted(true))} />
        </View>
      )}
    </View>
  );
}

function AssistantBox({ client, packKey, assistantKey, name, persona, gates, onPublish }: {
  client: PlatformClient; packKey: string; assistantKey: string; name: string; persona: string; gates: string[];
  onPublish?: (category: string) => void;
}) {
  const [q, setQ] = useState('');
  const [ans, setAns] = useState<PackAnswer | null>(null);
  const [contract, setContract] = useState<AssistantContract | null>(null);
  const [error, setError] = useState('');
  async function ask() {
    if (!q.trim()) return;
    setError('');
    try { setAns(await client.askPackAssistant(packKey, assistantKey, q)); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card}>
      <Text style={s.title}>{name}</Text>
      <Text style={s.muted}>{persona}</Text>
      <Text style={s.muted}>必须你本人确认：{gates.join('；')}</Text>
      {/* REL-107 完整的角色契约（130 号 spec） */}
      {contract ? (
        <View accessibilityLabel={`角色契约：${name}`}>
          <Text style={s.muted}>需要你给：{contract.inputs.join('；')}</Text>
          <Text style={s.muted}>它给你：{contract.outputs.join('；')}</Text>
          <Text style={s.muted}>不会做：{contract.forbidden.join('；')}</Text>
          <Text style={s.muted}>只用这些工具：{contract.tools.map((t) => t.name).join('；')}</Text>
        </View>
      ) : (
        <TouchableOpacity onPress={() => void client.assistantContract(packKey, assistantKey).then(setContract).catch((e) => setError(apiErrorText(e)))}>
          <Text style={s.link}>看完整的角色契约</Text>
        </TouchableOpacity>
      )}
      <TextInput style={s.input} placeholder={`问${name}`} value={q} onChangeText={setQ} onSubmitEditing={() => void ask()} />
      <Button title="问" onPress={() => void ask()} />
      {!!error && <Text style={s.error}>{error}</Text>}
      {ans && (ans.refused || !ans.citations.length ? <Text>{ans.answer}</Text> : (
        <View style={s.box}>
          {ans.citations.map((c) => (
            <Text key={c.n}>[{c.n}] {c.title}：{c.snippet}<Text style={s.muted}>（出处：{c.source}{c.valid_until ? `；有效期至 ${c.valid_until}` : ''}）</Text>
              {c.expired ? <Text style={s.error}> 已过有效期</Text> : null}</Text>
          ))}
          <Text style={s.muted}>{ans.gate_notice}</Text>
        </View>
      ))}
      {ans?.remedy && onPublish && (
        <TouchableOpacity onPress={() => onPublish(ans.remedy!.category)}><Text style={s.link}>{ans.remedy.label}</Text></TouchableOpacity>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  input: { borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 8 },
  card: { borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 4 },
  title: { fontSize: 15, fontWeight: '600' },
  h: { fontSize: 16, fontWeight: '600', marginTop: 6 },
  muted: { color: '#777' },
  error: { color: '#c0392b' },
  link: { color: '#b5532f' },
});
