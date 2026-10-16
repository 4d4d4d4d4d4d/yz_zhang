// XAPP 跨 App 助手在 App 上（161 号 spec）：授权哪些 App、发起一次执行、逐步确认、一键叫停、看记录。
// 真正去点别的 App 的原生执行器（Android 无障碍）需要开发构建与真机，暂缺；这里的「模拟执行器试跑」只走协议，不碰任何 App。
import {
  apiErrorText, driveXappRun, type PlatformClient, type XappCatalog, type XappGrant, type XappRun, type XappRunDetail,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, StyleSheet, Text, TextInput, View } from 'react-native';

const STATUS: Record<string, string> = { running: '执行中', needs_human: '交还给你了', stopped: '已叫停', done: '完成', failed: '失败' };
const STEP_STATUS: Record<string, string> = { pending: '待执行', dispatched: '执行中', done: '完成', done_by_user: '你已亲手完成', failed: '失败', skipped: '跳过' };

export function XappScreen({ client }: { client: PlatformClient }) {
  const [cat, setCat] = useState<XappCatalog | null>(null);
  const [grants, setGrants] = useState<XappGrant[]>([]);
  const [runs, setRuns] = useState<XappRun[]>([]);
  const [open, setOpen] = useState<XappRunDetail | null>(null);
  const [apps, setApps] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setCat(await client.xappCatalog());
      setGrants(await client.xappGrants());
      setRuns(await client.xappRuns());
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done = '') {
    setError(''); setNotice('');
    try { await fn(); if (done) setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const refreshRun = async (id: number) => setOpen(await client.xappRun(id));

  return (
    <View style={{ gap: 12 }}>
      {!!cat && <Text style={s.muted} accessibilityLabel="跨 App 助手说明">{cat.notice}</Text>}
      <View style={s.card} accessibilityLabel="新的授权">
        <Text style={s.title}>授权哪些 App</Text>
        <TextInput style={s.input} accessibilityLabel="目标 App" autoCapitalize="none" placeholder="包名，多个用逗号分开，例如 com.autonavi.minimap"
                   value={apps} onChangeText={setApps} />
        <Text style={s.muted}>允许的动作：打开、读取页面、填写、点击、跳转页面；7 天有效；屏幕内容只在本机处理。</Text>
        <Button title="授权" disabled={!apps.trim()} onPress={() => void act(async () => {
          await client.createXappGrant({ apps: apps.split(/[,，\s]+/).filter(Boolean), actions: ['open', 'read', 'fill', 'tap', 'navigate'], days: 7, device_label: '这台手机' });
          setApps('');
        }, '已授权')} />
      </View>
      {grants.map((g) => (
        <View key={g.id} style={s.card} accessibilityLabel={`授权 ${g.id}`}>
          <Text>{g.apps.join('、')} · {g.active ? '生效中' : '已失效'}</Text>
          {g.active && <Button title="撤销（正在跑的会一起停）" onPress={() => void act(() => client.revokeXappGrant(g.id), '已撤销')} />}
          {g.active && (
            <Button title="发起一次示例执行（模拟执行器）" onPress={() => void act(async () => {
              // 示例计划：先打开授权里的第一个 App，再对外发消息（红线步，要你亲手完成）；模拟执行器不会真的去点
              const app = g.apps[0];
              const run = await client.createXappRun({ grant_id: g.id, goal: `示例：在 ${app} 里回复客户`, executor: 'mock', confirm_mode: 'red_only',
                steps: [{ app, action: g.actions.includes('open') ? 'open' : g.actions[0], intent: '打开到对话页', channel: 'deeplink' },
                        { app, action: 'send_message', intent: '发出回复（你亲手点发送）', channel: 'a11y' }] });
              await refreshRun(run.id);
            }, '已发起，看下面的步骤')} />
          )}
        </View>
      ))}
      <Text style={s.title}>执行记录</Text>
      {runs.length === 0 && <Text style={s.muted}>还没有执行过。</Text>}
      {runs.map((r) => (
        <View key={r.id} style={s.card}>
          <Text>{r.goal} · {STATUS[r.status] ?? r.status}{r.stop_reason ? `：${r.stop_reason}` : ''}</Text>
          <Button title="看步骤" onPress={() => void act(() => refreshRun(r.id))} />
        </View>
      ))}
      {open && (
        <View style={s.card} accessibilityLabel="执行详情">
          <Text style={s.title}>{open.goal}（{STATUS[open.status] ?? open.status}）</Text>
          {open.steps.map((st) => (
            <View key={st.id} style={{ gap: 4 }}>
              <Text>{st.seq}. {st.intent}（{st.action_label} · {st.app}）· {STEP_STATUS[st.status] ?? st.status}</Text>
              {st.red_line && <Text style={s.warn}>这一步要你亲手完成，智能体只会把你带到那个页面</Text>}
              {!!st.result && <Text style={s.muted}>{st.result}</Text>}
              {open.status === 'running' && st.needs_confirm && !st.confirmed && !['done', 'done_by_user'].includes(st.status) && (
                <Button title={st.red_line ? '我已亲手完成这一步' : '确认这一步'}
                        onPress={() => void act(async () => { await client.confirmXappStep(open.id, st.id); await refreshRun(open.id); })} />
              )}
            </View>
          ))}
          {open.status === 'running' && (
            <>
              <Button title="一键叫停" color="#dc2626" onPress={() => void act(async () => { await client.stopXappRun(open.id, '本人叫停'); await refreshRun(open.id); }, '已叫停')} />
              {open.executor === 'mock' && (
                <Button title="用模拟执行器试跑（不会真的操作其他 App）" onPress={() => void act(async () => {
                  const last = await driveXappRun(client, open.id, { perform: async (st) => ({ ok: true, summary: `模拟完成：${st.intent}` }) });
                  await refreshRun(open.id);
                  setNotice(last.state === 'done' ? '模拟执行完成' : `停在这里：${last.state === 'awaiting_confirm' || last.state === 'handoff' ? '等你确认或亲手完成' : last.reason || last.state}`);
                })} />
              )}
            </>
          )}
        </View>
      )}
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 12, gap: 6 },
  title: { fontSize: 16, fontWeight: '600' },
  muted: { color: '#6b7280' },
  warn: { color: '#b45309' },
  error: { color: '#b91c1c' },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 6, padding: 8 },
});
