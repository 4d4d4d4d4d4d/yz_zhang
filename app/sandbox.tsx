// SBX-100 隐私沙箱（128 号 spec）——App 端：开关、本机助手（端侧模型或本机规则）、本机笔记、同步前脱敏、端侧模型目录。
// 开着时：助手的活在手机上本机做，原文不发到云端；把原文交给云端 AI 的请求在发出之前就被拦下。
import {
  LOCAL_SKILL_NAMES, REDACT_NAMES, apiErrorText, askLocal, redact, runLocal,
  type LocalResult, type LocalSkill, type PlatformClient, type SandboxModelList, type SandboxModelRow, type SandboxState,
} from '@platform/core';
import { useEffect, useState } from 'react';
import { Button, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  ModelError, activateModel, downloadModel, installedModels, pauseDownload, removeModel, staleModels,
  type InstalledModel, type ModelFs,
} from './modelStore';
import {
  getLocalModel, isSandbox, loadLocalNotes, loadSandbox, saveLocalNotes, setSandboxLocal, type LocalNote,
} from './sandboxState';

const SKILLS: LocalSkill[] = ['summarize', 'checklist', 'todos', 'rewrite', 'reply'];

export function SandboxScreen({ client, fs }: { client: PlatformClient; fs?: ModelFs }) {
  const [state, setState] = useState<SandboxState | null>(null);
  const [on, setOn] = useState(isSandbox());
  const [notes, setNotes] = useState<LocalNote[]>([]);
  const [text, setText] = useState('');
  const [instruction, setInstruction] = useState('');
  const [result, setResult] = useState<LocalResult | null>(null);
  const [refused, setRefused] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [catalog, setCatalog] = useState<SandboxModelList | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [model, setModel] = useState(getLocalModel());
  const [installed, setInstalled] = useState<InstalledModel[]>([]);
  const [progress, setProgress] = useState<Record<string, string>>({});

  useEffect(() => {
    void loadSandbox().then(setOn);
    void loadLocalNotes().then(setNotes);
    client.mySandbox().then(async (s) => {
      setState(s);
      if (s.enabled && !isSandbox()) { await setSandboxLocal(true); setOn(true); }   // 服务端记着开着：以开着为准
    }).catch((e) => setError(apiErrorText(e)));
    client.sandboxModels().then(setCatalog).catch(() => setCatalog(null));
    void installedModels().then(setInstalled);
  }, [client]);

  // SBX-111 下载 → 校验 → 登记；暂停后再点会续上
  async function download(m: SandboxModelRow) {
    setError(''); setNotice('');
    try {
      const inst = await downloadModel(m, (phase, r) => setProgress((p) => ({ ...p, [m.key]: `${phase === 'download' ? '下载' : '校验'} ${Math.round(r * 100)}%` })), fs);
      setInstalled(await installedModels());
      setNotice(`「${inst.name}」已下载并通过 sha256 校验`);
    } catch (e) { setError(e instanceof ModelError ? e.message : apiErrorText(e)); }
    finally { setProgress((p) => { const n = { ...p }; delete n[m.key]; return n; }); }
  }
  async function activate(inst: InstalledModel) {
    const r = await activateModel(inst);
    setModel(r.model);
    setNotice(r.model ? `已启用「${inst.name}」：本机助手用它生成` : r.reason);
  }
  async function remove(inst: InstalledModel) {
    await removeModel(inst, fs);
    setInstalled(await installedModels()); setModel(getLocalModel());
    setNotice(`已从这台手机上删掉「${inst.name}」`);
  }
  const stale = catalog ? staleModels(installed, catalog.items) : [];

  async function toggle(next: boolean) {
    setError(''); setNotice('');
    if (next) { await setSandboxLocal(true); setOn(true); }      // 打开：先在本机生效
    try {
      setState(await client.setSandbox(next));
      if (!next) { await setSandboxLocal(false); setOn(false); }  // 关闭：服务端成功了才在本机关
      setNotice(next ? '隐私沙箱已打开：助手的活在本机做' : '隐私沙箱已关闭：可以用云端助手了');
    } catch (e) { setError(apiErrorText(e)); }
  }

  async function run(skill?: LocalSkill) {
    setRefused(''); setConfirmed(false);
    if (skill) { setResult(await runLocal(skill, text, model)); return; }
    const r = await askLocal(instruction, text, model);
    if ('refused' in r) { setResult(null); setRefused(r.refused); } else setResult(r);
  }

  async function keep() {
    if (!text.trim()) return;
    const next = [{ id: String(Date.now()), text: text.trim(), updated_at: Date.now() }, ...notes].slice(0, 200);
    setNotes(next); await saveLocalNotes(next); setNotice('已存在这台手机上');
  }

  const outgoing = result ? redact(result.output) : null;
  async function sync() {
    if (!outgoing || !confirmed || !result) return;
    setError('');
    try {
      await client.createNote({ body: outgoing.text, title: `本机助手：${LOCAL_SKILL_NAMES[result.skill]}`, tags: ['本机助手'] });
      setNotice('脱敏后的结果已放进你的知识库'); setConfirmed(false);
    } catch (e) { setError(apiErrorText(e)); }
  }

  return (
    <View style={s.box}>
      <View style={[s.card, s.row]} accessibilityLabel="沙箱开关">
        <Text style={{ flex: 1 }}>{on ? `隐私沙箱开着：${state?.blocked_endpoints ?? ''} 类云端助手接口被拦下` : '隐私沙箱关着'}</Text>
        <Switch accessibilityLabel="隐私沙箱" value={on} onValueChange={(v) => void toggle(v)} />
      </View>
      {!!state && <Text style={s.muted}>{state.note}</Text>}
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}

      <View style={s.card} accessibilityLabel="本机助手">
        <Text style={s.title}>本机助手</Text>
        <Text style={s.muted}>{model ? `端侧模型：${model.id}` : '这台手机还没有装端侧模型，用的是本机规则'}</Text>
        <TextInput style={[s.input, { minHeight: 96 }]} multiline accessibilityLabel="本机内容" value={text} onChangeText={setText}
          placeholder="贴一段纪要、消息或要做的事（只在这台手机上）" />
        <View style={s.wrap}>
          {SKILLS.map((k) => (
            <TouchableOpacity key={k} accessibilityRole="button" style={s.chip} disabled={!text.trim()} onPress={() => void run(k)}>
              <Text>{LOCAL_SKILL_NAMES[k]}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity accessibilityRole="button" style={s.chip} disabled={!text.trim()} onPress={() => void keep()}><Text>存在本机</Text></TouchableOpacity>
        </View>
        <TextInput style={s.input} accessibilityLabel="一句话指令" value={instruction} onChangeText={setInstruction}
          placeholder="或者直接说：帮我抽出待办 / 拆成步骤 / 回复一下" />
        <Button title="让本机助手做" disabled={!instruction.trim() || !text.trim()} onPress={() => void run()} />
        {!!refused && <Text style={s.error}>{refused}</Text>}
        {result && (
          <View accessibilityLabel="本机结果">
            <Text>{result.output}</Text>
            <Text style={s.muted}>{result.notice}</Text>
          </View>
        )}
        {outgoing && (
          <View style={s.card} accessibilityLabel="同步前脱敏">
            <Text>要放进云端知识库吗？发出去的是这份（已脱敏）：</Text>
            <Text>{outgoing.text}</Text>
            <Text style={s.muted}>{outgoing.hits.length ? `遮掉了：${outgoing.hits.map((h) => `${REDACT_NAMES[h.kind]} ${h.count} 处`).join('、')}` : '没有找到需要遮的号码；人名、地址请你自己看一遍'}</Text>
            <View style={s.row}>
              <Switch accessibilityLabel="我看过了，可以发到云端" value={confirmed} onValueChange={setConfirmed} />
              <Text>我看过了，可以发到云端</Text>
            </View>
            <Button title="放进我的知识库" disabled={!confirmed} onPress={() => void sync()} />
          </View>
        )}
      </View>

      <View style={s.card} accessibilityLabel="本机笔记">
        <Text style={s.title}>本机笔记（{notes.length}）</Text>
        {notes.map((n) => (
          <View key={n.id} style={s.row}>
            <TouchableOpacity style={{ flex: 1 }} onPress={() => setText(n.text)}><Text numberOfLines={1}>{n.text}</Text></TouchableOpacity>
            <TouchableOpacity accessibilityRole="button" accessibilityLabel="删掉这条本机笔记" onPress={() => {
              const next = notes.filter((x) => x.id !== n.id); setNotes(next); void saveLocalNotes(next);
            }}><Text style={s.link}>删除</Text></TouchableOpacity>
          </View>
        ))}
      </View>

      <View style={s.card} accessibilityLabel="端侧模型">
        <Text style={s.title}>端侧模型</Text>
        <Text style={s.muted}>{catalog?.note ?? ''}</Text>
        {catalog && catalog.items.length === 0 && <Text style={s.muted}>平台还没有上架端侧模型。</Text>}
        {catalog?.items.map((m) => {
          const inst = installed.find((i) => i.key === m.key && i.sha256 === m.sha256.toLowerCase());
          return (
            <View key={m.id} style={s.card} accessibilityLabel={`模型 ${m.name}`}>
              <Text>{m.name} · {m.params_b}B · {m.quant} · {m.size_mb} MB · 至少 {m.min_ram_gb} GB 内存</Text>
              {progress[m.key] ? (
                <View style={s.row}><Text style={{ flex: 1 }}>{progress[m.key]}</Text>
                  <Button title="暂停" onPress={() => void pauseDownload(m.key)} /></View>
              ) : inst ? (
                <View style={s.row}>
                  <Text style={{ flex: 1 }}>已下载，校验通过</Text>
                  <Button title="启用" onPress={() => void activate(inst)} />
                  <Button title="删除" onPress={() => void remove(inst)} />
                </View>
              ) : <Button title="下载并校验" onPress={() => void download(m)} />}
            </View>
          );
        })}
        {stale.map((i) => (
          <View key={i.key} style={s.row} accessibilityLabel="已下架的模型">
            <Text style={{ flex: 1 }}>「{i.name}」平台已下架或换了版本，建议删掉</Text>
            <Button title="删掉" onPress={() => void remove(i)} />
          </View>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  box: { gap: 8 },
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { borderWidth: 1, borderColor: '#ddd', borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4 },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#777' },
  link: { color: '#2563eb' },
  error: { color: '#b91c1c' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
});
