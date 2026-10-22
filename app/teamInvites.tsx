// TEAM-066 团队邀请链接在 App 上（147 号 spec）：所有者生成链接交给系统分享；被邀请的人粘贴链接或邀请码，看清楚再加入。
import { INVITE_STATE_LABEL, apiErrorText, fmtYuan, formatDateTime, inviteJoinedLine, type PlatformClient, type TeamInviteLink, type TeamInvitePreview } from '@platform/core';
import { useCallback, useState } from 'react';
import { Button, Share, StyleSheet, Text, TextInput, View } from 'react-native';

/** 从整条链接或单独的邀请码里取出令牌 */
export function inviteToken(input: string): string {
  const t = input.trim();
  const m = t.match(/\/teams\/join\/([A-Za-z0-9_-]+)/);
  return m ? m[1] : t;
}

// 网页地址：部署时配 EXPO_PUBLIC_WEB_URL；没配时用 API 地址（网页与 API 同源部署时就是同一个）
const WEB_ORIGIN = (process.env.EXPO_PUBLIC_WEB_URL || process.env.EXPO_PUBLIC_API_BASE_URL || '').replace(/\/$/, '');

export function TeamInviteLinkBlock({ client, teamId, origin = WEB_ORIGIN, share = Share.share }: {
  client: PlatformClient; teamId: number; origin?: string; share?: (c: { message: string }) => Promise<unknown>;
}) {
  const [limit, setLimit] = useState('0');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  // TEAM-072（232 号 spec）链接清单：状态、用了几次、谁通过它加入（228 号）；链接外泄时在手机上就能作废
  // 点开才加载：打开团队页的人多半只是想发一条新链接
  const [links, setLinks] = useState<TeamInviteLink[] | null>(null);
  const load = useCallback(async () => {
    const r = await client.teamInviteLinks(teamId).catch(() => []);
    setLinks(Array.isArray(r) ? r : []);
  }, [client, teamId]);
  return (
    <View style={s.card} accessibilityLabel="邀请链接">
      <Text style={s.title}>邀请链接</Text>
      <Text style={s.muted}>不用让对方先报用户编号：生成一条 7 天有效、用一次的链接发给对方，对方看清楚后自己加入。</Text>
      <TextInput style={s.input} accessibilityLabel="链接的月度额度" keyboardType="numeric" placeholder="加入后的月度额度（元）" value={limit} onChangeText={setLimit} />
      <Button title="生成并分享邀请链接" onPress={() => void (async () => {
        setError(''); setNotice('');
        try {
          const r = await client.createTeamInviteLink(teamId, { spend_limit_cents: Math.round(Number(limit || '0') * 100) });
          // 没有网页地址时只分享邀请码：对方在 App「团队」里粘贴它一样能加入
          const where = origin ? `${origin}${r.path}` : `邀请码 ${r.token}`;
          await share({ message: `邀请你加入我的团队：${where}\n（7 天内有效，只能用一次；也可以在 App「团队」里粘贴它加入）` });
          setNotice('已生成并交给系统分享。链接只显示这一次，丢了就作废重发。');
          if (links) await load();
        } catch (e) { setError(apiErrorText(e)); }
      })()} />
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
      {links === null
        ? <Button title="查看已发的链接" onPress={() => void load()} />
        : links.length === 0 && <Text style={s.muted}>还没有发过邀请链接。</Text>}
      {(links ?? []).map((l) => (
        <View key={l.id} style={{ gap: 4 }} accessibilityLabel={`邀请链接 ${l.id}`}>
          <Text style={s.muted}>
            #{l.id} 额度 {fmtYuan(l.spend_limit_cents)} · 已用 {l.uses}/{l.max_uses} · {INVITE_STATE_LABEL[l.state] ?? l.state}
            {inviteJoinedLine(l) ? ` · ${inviteJoinedLine(l)}` : ''}
          </Text>
          {l.state === 'active' && (
            <Button title={`作废 #${l.id}`} color="#b91c1c" onPress={() => void (async () => {
              setError(''); setNotice('');
              try {
                await client.revokeTeamInviteLink(teamId, l.id);
                setNotice(`已作废邀请链接 #${l.id}：再有人点开会看到「链接无效」`);
                await load();
              } catch (e) { setError(apiErrorText(e)); }
            })()} />
          )}
        </View>
      ))}
    </View>
  );
}

export function JoinTeamByCode({ client, onJoined }: { client: PlatformClient; onJoined: () => void }) {
  const [code, setCode] = useState('');
  const [p, setP] = useState<TeamInvitePreview | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  async function run(fn: () => Promise<unknown>) {
    setError(''); setNotice('');
    try { await fn(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <View style={s.card} accessibilityLabel="用邀请链接加入团队">
      <Text style={s.title}>用邀请链接加入团队</Text>
      <TextInput style={s.input} accessibilityLabel="邀请链接或邀请码" autoCapitalize="none" placeholder="粘贴对方发来的链接" value={code} onChangeText={(v) => { setCode(v); setP(null); }} />
      {!p && <Button title="看看是哪个团队" disabled={!code.trim()} onPress={() => void run(async () => setP(await client.teamInvitePreview(inviteToken(code))))} />}
      {p && (
        <View style={{ gap: 4 }}>
          <Text>{p.inviter_nickname || '团队所有者'} 邀请你加入「{p.team_name}」，成为普通成员</Text>
          <Text style={s.muted}>每月最多可以花团队的 {fmtYuan(p.spend_limit_cents)}（超出要审批）；{formatDateTime(p.expires_at)} 前有效</Text>
          {p.already_member ? <Text>你已经是这个团队的成员了。</Text> : (
            <Button title="加入团队" onPress={() => void run(async () => {
              await client.acceptTeamInvite(inviteToken(code));
              setNotice(`已加入「${p.team_name}」`); setP(null); setCode(''); onJoined();
            })} />
          )}
        </View>
      )}
      {!!notice && <Text accessibilityRole="alert">{notice}</Text>}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 10, gap: 6, alignSelf: 'stretch' },
  title: { fontSize: 15, fontWeight: '600' },
  muted: { color: '#777' },
  error: { color: '#b91c1c' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#e5e7eb' },
});
