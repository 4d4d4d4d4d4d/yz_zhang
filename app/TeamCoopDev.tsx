// APP-069 三条线的 App 界面：团队 / 合作体 / 开发者（67 号 spec）。
//
// V84 把这三页做在了网页上，App 至今一个都没有。V92 给团队审批补了通知，
// 而**通知把人叫来了、他点进去无路可走**，比没有通知更糟——
// 这正是 V91 APP-066 的教训（V90 的必达通知指了一条 App 上不存在的路）。
//
// 按钮的可用性一律读服务端的判断（`can_decide` / `invoice_block`），
// 客户端不重写：**第二份实现必然抄漏**（UI-075 立过这条）。
import {
  apiErrorText, fmtYuan,
  type ApiKeyView, type ContributionView, type ShareRow,
  type SpendRequestView, type TeamDetail, type TeamView, type VentureView,
  type PlatformClient,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Button, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

export type SubScreen = 'teams' | 'ventures' | 'developer';

export const SUB_SCREEN_LABEL: Record<SubScreen, string> = {
  teams: '团队账户',
  ventures: '早期合作体',
  developer: '开发者（API Key / Webhook）',
};

export function SubScreenHost({ client, screen, onBack }: {
  client: PlatformClient; screen: SubScreen; onBack: () => void;
}) {
  return (
    <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 24 }}>
      <TouchableOpacity onPress={onBack}><Text style={s.link}>← 返回「我的」</Text></TouchableOpacity>
      <Text style={s.title}>{SUB_SCREEN_LABEL[screen]}</Text>
      {screen === 'teams' && <TeamsScreen client={client} />}
      {screen === 'ventures' && <VenturesScreen client={client} />}
      {screen === 'developer' && <DeveloperScreen client={client} />}
    </ScrollView>
  );
}

function useAct() {
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function act(fn: () => Promise<unknown>) {
    setError(''); setNotice('');
    try {
      await fn();
    } catch (e) {
      // CLI-064 服务端算好的「为什么不行」原样显示，不自己编一句
      setError(apiErrorText(e));
    }
  }
  return { error, notice, setNotice, act };
}

// ------------------------------------------------------------------ 团队账户
function TeamsScreen({ client }: { client: PlatformClient }) {
  const [mine, setMine] = useState<Array<TeamView & { my_role: string }>>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [name, setName] = useState('');
  const { error, act } = useAct();

  const load = useCallback(async () => {
    setMine(await client.myTeams().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 10 }}>
      <Text style={s.muted}>
        团队用自己的钱包发任务：成员有各自的月度额度，超额要审批，
        发票开给企业而不是个人。
      </Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {mine.length === 0 && <Text style={s.muted}>你还没有加入任何团队。</Text>}
      {mine.map((t) => (
        <TouchableOpacity key={t.id} style={s.card} onPress={() => setOpen(t.id)}>
          <Text style={s.cardTitle}>{t.name}</Text>
          <Text style={s.muted}>{t.my_role} · {t.company_name || '未提交企业信息'}</Text>
        </TouchableOpacity>
      ))}
      <TextInput style={s.input} value={name} onChangeText={setName} placeholder="新建团队名称" />
      <Button title="建团队" onPress={() => act(async () => {
        await client.createTeam(name.trim());
        setName('');
        await load();
      })} />
      {open !== null && <TeamDetailBlock client={client} teamId={open} />}
    </View>
  );
}

function TeamDetailBlock({ client, teamId }: { client: PlatformClient; teamId: number }) {
  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [spends, setSpends] = useState<SpendRequestView[]>([]);
  const [amount, setAmount] = useState('');
  const [purpose, setPurpose] = useState('');
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState('');
  const { error, notice, setNotice, act } = useAct();

  const load = useCallback(async () => {
    setTeam(await client.team(teamId).catch(() => null));
    setSpends(await client.teamSpends(teamId).catch(() => []));
  }, [client, teamId]);
  useEffect(() => { void load(); }, [load]);

  if (!team) return null;
  const poolLeft = Math.max(0, team.monthly_budget_cents - team.month_spent_cents);

  return (
    <View style={{ gap: 10, marginTop: 8 }}>
      <Text style={s.cardTitle}>{team.name}</Text>
      <Text style={s.muted}>
        余额 {fmtYuan(team.balance_cents)} · 我的角色 {team.my_role}
      </Text>
      {/* TEAM-050 额度是**月度累计**的，要说清楚，别让人以为是单笔 */}
      <Text style={s.muted}>
        我的本月额度 {fmtYuan(team.my_spend_limit_cents)}（已用 {fmtYuan(team.my_month_spent_cents)}）
      </Text>
      <Text style={s.muted}>
        {team.monthly_budget_cents > 0
          ? `团队本月预算池 ${fmtYuan(team.monthly_budget_cents)}，已用 ${fmtYuan(team.month_spent_cents)}，剩余 ${fmtYuan(poolLeft)}`
          : `未设预算池（本月已花 ${fmtYuan(team.month_spent_cents)}）`}
      </Text>

      <Text style={s.cardTitle}>申请支出</Text>
      <TextInput style={s.input} keyboardType="numeric" value={amount}
                 onChangeText={setAmount} placeholder="金额（元）" />
      <TextInput style={s.input} value={purpose} onChangeText={setPurpose} placeholder="用途" />
      <Button title="提交申请" onPress={() => act(async () => {
        const r = await client.requestTeamSpend(
          teamId, Math.round(parseFloat(amount || '0') * 100), purpose);
        setAmount(''); setPurpose('');
        // UI-075 超额不是失败：申请已经建好了，在等审批。
        // 显示成报错，用户会以为自己做错了什么。
        setNotice(r.needed_approval ? `已提交，等待管理员审批：${r.reason}` : '已通过额度校验，可直接执行');
        await load();
      })} />
      {!!notice && <Text style={s.muted}>{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}

      <Text style={s.cardTitle}>支出申请</Text>
      {spends.length === 0 && <Text style={s.muted}>还没有支出申请。</Text>}
      {spends.map((sp) => (
        <View key={sp.id} style={s.card}>
          <Text style={s.cardTitle}>{fmtYuan(sp.amount_cents)} · {sp.purpose || '未填用途'}</Text>
          <Text style={s.muted}>
            #{sp.requester_id} · {sp.status}
            {/* TEAM-061 被强制写下的那段理由，界面要显示出来 */}
            {sp.decision_reason ? ` · ${sp.decision_reason}` : ''}
          </Text>
          {/* UI-075 读服务端的 can_decide：自己批自己不算审批，客户端不重判 */}
          {sp.can_decide && rejecting !== sp.id && (
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
              <Button title="批准" onPress={() => act(async () => {
                await client.decideTeamSpend(teamId, sp.id, true);
                await load();
              })} />
              <Button title="驳回" color="#dc2626" onPress={() => { setRejecting(sp.id); setReason(''); }} />
            </View>
          )}
          {rejecting === sp.id && (
            <View style={{ gap: 6, marginTop: 6 }}>
              {/* 服务端强制驳回必须写原因（reason_required）。
                  这里不做成「可不填」——填了才是给对方的下一步依据 */}
              <TextInput style={s.input} value={reason} onChangeText={setReason}
                         placeholder="驳回理由（必填，对方会收到）" />
              <Button title="确认驳回" color="#dc2626" onPress={() => act(async () => {
                await client.decideTeamSpend(teamId, sp.id, false, reason);
                setRejecting(null);
                await load();
              })} />
            </View>
          )}
          {sp.status === 'approved' && (
            <Button title="执行" onPress={() => act(async () => {
              await client.executeTeamSpend(teamId, sp.id);
              await load();
            })} />
          )}
        </View>
      ))}

      <Text style={s.cardTitle}>企业信息与发票</Text>
      {/* UI-075 开票能力读服务端的 invoice_block，理由原样显示 */}
      <Text style={team.invoice_block ? s.error : s.muted}>
        {team.invoice_block || '企业信息已核验，可以开具企业抬头发票。'}
      </Text>
      <Text style={s.muted}>
        当前：{team.company_name || '未提交'}（{team.verify_status}）
        {team.verify_reason ? ` · ${team.verify_reason}` : ''}
      </Text>
    </View>
  );
}

// ---------------------------------------------------------------- 早期合作体
function VenturesScreen({ client }: { client: PlatformClient }) {
  const [mine, setMine] = useState<Array<VentureView & { role: string }>>([]);
  const [open, setOpen] = useState<number | null>(null);
  const { error, act } = useAct();

  const load = useCallback(async () => {
    setMine(await client.myVentures().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 10 }}>
      <Text style={s.muted}>
        没有现金的早期项目：贡献经确认后折算成份额，项目有收入时按份额分配。
      </Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {mine.length === 0 && <Text style={s.muted}>你还没有参与任何合作体。</Text>}
      {mine.map((v) => (
        <TouchableOpacity key={v.id} style={s.card} onPress={() => setOpen(v.id)}>
          <Text style={s.cardTitle}>{v.name}</Text>
          <Text style={s.muted}>{v.role} · {v.status}</Text>
        </TouchableOpacity>
      ))}
      {open !== null && <VentureDetailBlock client={client} ventureId={open} act={act} />}
    </View>
  );
}

function VentureDetailBlock({ client, ventureId, act }: {
  client: PlatformClient; ventureId: number; act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [shares, setShares] = useState<ShareRow[]>([]);
  const [basis, setBasis] = useState('');
  const [rows, setRows] = useState<ContributionView[]>([]);
  const [desc, setDesc] = useState('');
  const [risk, setRisk] = useState('');

  const load = useCallback(async () => {
    const sh = await client.ventureShares(ventureId).catch(() => null);
    setShares(sh?.shares ?? []);
    setBasis(sh?.basis ?? '');
    setRows(await client.ventureContributions(ventureId).catch(() => []));
    // COOP-030 风险揭示是**按项目名取的通用文本**，不是某个 venture 的字段
    const r = await client.ventureRiskDisclosure().catch(() => null);
    setRisk(r ? `${r.title}\n${r.points.join('\n')}` : '');
  }, [client, ventureId]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 10, marginTop: 8 }}>
      <Text style={s.cardTitle}>份额</Text>
      {/* COOP-021 份额口径要写出来：不说清楚按什么折算，数字没有意义 */}
      {!!basis && <Text style={s.muted}>{basis}</Text>}
      {shares.length === 0 && <Text style={s.muted}>还没有确认的贡献，份额为空。</Text>}
      {shares.map((row) => (
        <View key={row.user_id} style={s.card}>
          <Text style={s.cardTitle}>#{row.user_id} · {(row.share_bps / 100).toFixed(2)}%</Text>
          <Text style={s.muted}>已确认贡献折算 {fmtYuan(row.valued_cents)}</Text>
        </View>
      ))}

      <Text style={s.cardTitle}>贡献</Text>
      <TextInput style={s.input} value={desc} onChangeText={setDesc} placeholder="描述你做了什么" />
      <Button title="提交贡献（待确认）" onPress={() => act(async () => {
        await client.submitContribution(ventureId, 'time', desc);
        setDesc('');
        await load();
      })} />
      {rows.map((c) => (
        <View key={c.id} style={s.card}>
          <Text style={s.cardTitle}>#{c.user_id} · {c.kind} · {c.status}</Text>
          <Text style={s.muted}>{c.description}</Text>
          {/* COOP-010 贡献不能自己确认——与 TEAM-021、VER-021 同一条规矩，
              准入判断在服务端，这里只是不把按钮摆给本人 */}
          {c.can_confirm && (
            <Button title="确认并折算 ¥1000" onPress={() => act(async () => {
              await client.confirmContribution(ventureId, c.id, 100000, '按约定折算');
              await load();
            })} />
          )}
        </View>
      ))}

      {/* COOP-030 风险揭示：份额不是股权，这句话必须出现在人看得到的地方 */}
      {!!risk && <Text style={s.muted}>{risk}</Text>}
    </View>
  );
}

// ------------------------------------------------------------------ 开发者
function DeveloperScreen({ client }: { client: PlatformClient }) {
  const [keys, setKeys] = useState<ApiKeyView[]>([]);
  const [hooks, setHooks] = useState<Array<{ id: number; url: string; events: string[]; active: boolean }>>([]);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [plain, setPlain] = useState('');
  const { error, act } = useAct();

  const load = useCallback(async () => {
    setKeys(await client.apiKeys().catch(() => []));
    setHooks(await client.webhooks().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 10 }}>
      {!!error && <Text style={s.error}>{error}</Text>}
      <Text style={s.cardTitle}>API Key</Text>
      <TextInput style={s.input} value={name} onChangeText={setName} placeholder="用途备注" />
      <Button title="创建 Key（只读范围）" onPress={() => act(async () => {
        const r = await client.createApiKey(name.trim() || '移动端', ['tasks:read']);
        // API-013 明文**只在创建时返回这一次**。服务端存的是哈希，
        // 之后谁也拿不回来——所以这里必须原样显示出来，并说明它不会再出现。
        setPlain(`${r.key}\n\n${r.warning}`);
        setName('');
        await load();
      })} />
      {!!plain && <Text style={s.mono}>{plain}</Text>}
      {keys.length === 0 && <Text style={s.muted}>还没有 API Key。</Text>}
      {keys.map((k) => (
        <View key={k.id} style={s.card}>
          <Text style={s.cardTitle}>{k.name} · {k.key_prefix}…</Text>
          <Text style={s.muted}>{k.scopes.join('、')} · {k.active ? '启用中' : '已吊销'}</Text>
          {k.active && (
            <Button title="吊销" color="#dc2626"
                    onPress={() => act(async () => { await client.revokeApiKey(k.id); await load(); })} />
          )}
        </View>
      ))}

      <Text style={s.cardTitle}>Webhook</Text>
      <TextInput style={s.input} value={url} onChangeText={setUrl}
                 placeholder="https://…（接收地址）" autoCapitalize="none" />
      <Button title="添加（任务状态变更）" onPress={() => act(async () => {
        const r = await client.createWebhook(url.trim(), ['task.status_changed']);
        // 签名密钥同理：只此一次
        setPlain(`${r.secret}\n\n${r.signature_howto}`);
        setUrl('');
        await load();
      })} />
      {hooks.length === 0 && <Text style={s.muted}>还没有 Webhook。</Text>}
      {hooks.map((h) => (
        <View key={h.id} style={s.card}>
          <Text style={s.cardTitle}>{h.url}</Text>
          <Text style={s.muted}>{h.events.join('、')} · {h.active ? '启用中' : '已停用'}</Text>
          <Button title="删除" color="#dc2626"
                  onPress={() => act(async () => { await client.deleteWebhook(h.id); await load(); })} />
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  title: { fontSize: 20, fontWeight: '700', color: '#2f6fed' },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 4 },
  muted: { color: '#6b7280', fontSize: 13 },
  mono: { fontFamily: 'Courier', backgroundColor: '#fff', padding: 10, borderRadius: 8 },
  error: { color: '#dc2626' },
  link: { color: '#2f6fed', paddingVertical: 8 },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
});
