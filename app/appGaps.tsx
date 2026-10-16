// APP-090 App 补齐（136 号 spec）：平台服务费发票、纠纷证据包导出、团队成员管理（TEAM-065）。
// 三件事 Web 上早就有（或者两端都没有），App 上没有入口——用户在手机上做不完一件事。
import { apiErrorText, fmtYuan, formatDate, teamHandoverDetail, type InvoiceRow, type PlatformClient, type TeamDetail } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Share, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { TeamInviteLinkBlock } from './teamInvites';

/** TAX-024 平台服务费发票：文案照服务端口径，只开平台佣金那部分。
 *  APP-076：开票是按合约的动作——传了 `contractId` 就是合约卡片里的入口，合约号已填好、只列这一单的发票。 */
export function InvoicesBlock({ client, contractId: fixed }: { client: PlatformClient; contractId?: number }) {
  const [all, setRows] = useState<InvoiceRow[]>([]);
  const rows = fixed ? all.filter((r) => r.contract_id === fixed) : all;
  const [typed, setContractId] = useState('');
  const contractId = fixed ? String(fixed) : typed;
  const [title, setTitle] = useState('');
  const [taxNo, setTaxNo] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => { setRows(await client.myInvoices().catch(() => [])); }, [client]);
  useEffect(() => { void load(); }, [load]);
  return (
    <View style={s.card} accessibilityLabel="平台服务费发票">
      <Text style={s.title}>平台服务费发票</Text>
      <Text style={s.muted}>已放款的合约可申请平台服务费发票（即平台佣金那部分）。执行方的劳务报酬平台没有开票资格，需由执行方或代开渠道开具。</Text>
      {!fixed && <TextInput style={s.input} accessibilityLabel="合约号" keyboardType="numeric" placeholder="合约号" value={contractId} onChangeText={setContractId} />}
      <TextInput style={s.input} accessibilityLabel="开票抬头" placeholder="开票抬头" value={title} onChangeText={setTitle} />
      <TextInput style={s.input} accessibilityLabel="税号" placeholder="税号（可选）" value={taxNo} onChangeText={setTaxNo} />
      <Button title="申请开票" disabled={!contractId || title.trim().length < 2} onPress={() => void (async () => {
        setError(''); setNote('');
        try {
          const r = await client.requestInvoice(Number(contractId), title, taxNo);
          setNote(r.scope_note); setContractId(''); setTitle(''); setTaxNo('');
          await load();
        } catch (e) { setError(apiErrorText(e)); }
      })()} />
      {!!note && <Text style={s.muted}>{note}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {rows.map((r) => <Text key={r.id} style={s.muted}>#{r.id} · 合约 #{r.contract_id} · {fmtYuan(r.amount_cents)} · {r.title} · {r.status} · {formatDate(r.at)}</Text>)}
    </View>
  );
}

/** DSPC 证据包导出：整包原样（含证明力边界说明与完整性校验），用系统分享发给律师或存到文件里。 */
export function EvidenceExportButton({ client, disputeId, share = Share.share }: {
  client: PlatformClient; disputeId: number; share?: (c: { title?: string; message: string }) => Promise<unknown>;
}) {
  const [error, setError] = useState('');
  return (
    <View>
      <Button title="导出证据包" color="#6b7280" onPress={() => void (async () => {
        setError('');
        try {
          const pack = await client.exportEvidence(disputeId);
          await share({ title: `纠纷 #${disputeId} 证据包`, message: JSON.stringify(pack, null, 2) });
        } catch (e) { setError(apiErrorText(e)); }
      })()} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

/** TEAM-065 团队成员：只有 owner 能加人、改角色与月度额度、移出；owner 自己不能改。 */
export function TeamMembersBlock({ client, teamId, team, onChanged }: { client: PlatformClient; teamId: number; team: TeamDetail; onChanged: () => void }) {
  const [userId, setUserId] = useState('');
  const [limit, setLimit] = useState('0');
  const [notice, setNotice] = useState('');
  // TEAM-054（170 号 spec）移出后的交接说明（单独一行，「已移出」照旧）
  const [handover, setHandover] = useState('');
  const [error, setError] = useState('');
  const owner = team.my_role === 'owner';
  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice('');
    try { await fn(); if (done) setNotice(done); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="团队成员">
      <Text style={s.title}>成员（{team.members.length}）</Text>
      {team.members.map((m) => (
        <View key={m.user_id} style={s.row}>
          <Text style={{ flex: 1 }}>{m.nickname || `用户 #${m.user_id}`} · {m.role === 'owner' ? '所有者' : m.role === 'admin' ? '管理员' : '成员'} · 月度额度 {fmtYuan(m.spend_limit_cents)}</Text>
          {owner && m.role !== 'owner' && (
            <>
              <TouchableOpacity accessibilityLabel={`切换角色：${m.nickname || m.user_id}`} onPress={() => void act(
                () => client.updateTeamMember(teamId, m.user_id, { role: m.role === 'admin' ? 'member' : 'admin' }), '角色已更新')}>
                <Text style={s.link}>{m.role === 'admin' ? '设为成员' : '设为管理员'}</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityLabel={`移出：${m.nickname || m.user_id}`} onPress={() => Alert.alert('移出成员', '移出后对方不能再用团队的钱。', [
                { text: '不移出', style: 'cancel' },
                { text: '移出', style: 'destructive', onPress: () => void act(async () => setHandover(teamHandoverDetail(await client.removeTeamMember(teamId, m.user_id))), '已移出') },
              ])}>
                <Text style={s.error}>移出</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      ))}
      {owner && (
        <>
          <TextInput style={s.input} accessibilityLabel="成员用户编号" keyboardType="numeric" placeholder="对方的用户编号（在对方个人空间里）" value={userId} onChangeText={setUserId} />
          <TextInput style={s.input} accessibilityLabel="月度额度" keyboardType="numeric" placeholder="月度额度（元）" value={limit} onChangeText={setLimit} />
          <Button title="加入团队" disabled={!Number(userId)} onPress={() => void act(async () => {
            await client.addTeamMember(teamId, Number(userId), 'member', Math.round(Number(limit || '0') * 100));
            setUserId('');
          }, '已加入')} />
          <TeamInviteLinkBlock client={client} teamId={teamId} />
        </>
      )}
      {!owner && <Text style={s.muted}>只有团队所有者能管理成员。</Text>}
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!handover && <Text style={s.muted} accessibilityLabel="移出交接">{handover}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#777' },
  link: { color: '#2563eb' },
  error: { color: '#b91c1c' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
});
