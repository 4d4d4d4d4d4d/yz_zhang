import {
  apiErrorText, fmtYuan, teamHandoverDetail,
  type SpendRequestView, type TeamDetail, type TeamInviteLink, type TeamView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../store';

/** UI-075 团队账户（53 号 spec 的界面侧）。
 *
 * 两个按钮的可用性都**读服务端的判断**，客户端不重写：
 * `can_decide` 里已经包含「自己不能批自己」，`invoice_block` 里已经包含
 * 「企业信息未核验」——重写一遍就是第二份实现，而第二份必然抄漏。
 */
export default function Teams() {
  const { client } = useApp();
  const [mine, setMine] = useState<Array<TeamView & { my_role: string }>>([]);
  const [current, setCurrent] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setMine(await client.myTeams().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (err) { setError(apiErrorText(err)); }
  }

  return (
    <div className="page">
      <div className="card">
        <h3>团队账户</h3>
        <p className="muted">
          团队用自己的钱包发任务：成员有各自的支出额度，超额要审批，
          发票开给企业而不是个人。
        </p>
        {error && <p className="error">{error}</p>}
        <div className="list">
          {mine.length === 0 && <p className="muted">你还没有加入任何团队。</p>}
          {mine.map((t) => (
            <div className="task-item" key={t.id}>
              <div>
                <strong>{t.name}</strong> <span className="badge">{t.my_role}</span>
                <p className="muted">{t.company_name || '未提交企业信息'}</p>
              </div>
              <button className="ghost" onClick={() => setCurrent(t.id)}>打开</button>
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <input className="grow" placeholder="新建团队名称" value={name}
                 onChange={(e) => setName(e.target.value)} />
          <button disabled={name.trim().length < 2}
                  onClick={() => act(async () => { await client.createTeam(name); setName(''); })}>
            建团队
          </button>
        </div>
      </div>
      {current !== null && <TeamCard teamId={current} />}
    </div>
  );
}

function TeamCard({ teamId }: { teamId: number }) {
  const { client } = useApp();
  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [spends, setSpends] = useState<SpendRequestView[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [amount, setAmount] = useState('');
  const [purpose, setPurpose] = useState('');

  const load = useCallback(async () => {
    setTeam(await client.team(teamId).catch(() => null));
    setSpends(await client.teamSpends(teamId).catch(() => []));
  }, [client, teamId]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError(''); setNotice('');
    try { await fn(); await load(); } catch (err) { setError(apiErrorText(err)); }
  }

  if (!team) return null;

  return (
    <>
      <div className="card">
        <h3>{team.name}</h3>
        <p className="muted">
          余额 <span className="price">{fmtYuan(team.balance_cents)}</span> ·
          我的角色 {team.my_role} ·{' '}
          {/* TEAM-050 额度是**月度累计**的，界面要说清楚，不能让人以为是单笔 */}
          我的本月额度 {fmtYuan(team.my_spend_limit_cents)}（已用 {fmtYuan(team.my_month_spent_cents)}）
        </p>
        {/* TEAM-052 预算池与本月用量：只显示「超额」的话，
            人不知道该改金额还是该改池子 */}
        <p className="muted" data-testid="team-budget">
          {team.monthly_budget_cents > 0
            ? `团队本月预算池 ${fmtYuan(team.monthly_budget_cents)}，已用 ${fmtYuan(team.month_spent_cents)}，剩余 ${fmtYuan(Math.max(0, team.monthly_budget_cents - team.month_spent_cents))}`
            : `未设预算池（本月已花 ${fmtYuan(team.month_spent_cents)}）`}
          {team.my_role === 'owner' && (
            <button className="ghost" style={{ marginLeft: 8, padding: '2px 8px' }}
                    onClick={() => {
                      const yuan = prompt('团队本月预算池（元，0 = 不设池）：',
                        String(team.monthly_budget_cents / 100));
                      if (yuan !== null) {
                        void act(() => client.setTeamBudget(teamId, Math.round(parseFloat(yuan || '0') * 100)));
                      }
                    }}>
              设置
            </button>
          )}
        </p>
        {error && <p className="error">{error}</p>}
        {notice && <p className="muted" data-testid="spend-notice">{notice}</p>}

        {/* TEAM-065 成员管理（136 号 spec）：只有所有者能加人、改角色与月度额度、移出 */}
        <TeamMembers teamId={teamId} team={team} onChanged={() => void load()} />

        <h4>申请支出</h4>
        <div className="row">
          <input style={{ width: 140 }} type="number" min={0.01} step={0.01} placeholder="金额（元）"
                 value={amount} onChange={(e) => setAmount(e.target.value)} />
          <input className="grow" placeholder="用途" value={purpose}
                 onChange={(e) => setPurpose(e.target.value)} />
          <button disabled={!amount} onClick={() => act(async () => {
            const r = await client.requestTeamSpend(teamId, Math.round(parseFloat(amount) * 100), purpose);
            setAmount(''); setPurpose('');
            // UI-075 超额不是失败：申请已经建好了，在等审批。
            // 把它显示成报错，用户会以为自己做错了什么。
            setNotice(r.needed_approval
              ? `已提交，等待管理员审批：${r.reason}`
              : '已通过额度校验，可直接执行');
          })}>
            提交申请
          </button>
        </div>

        <h4>支出申请</h4>
        <div className="list">
          {spends.length === 0 && <p className="muted">还没有支出申请。</p>}
          {spends.map((s) => (
            <div className="task-item" key={s.id}>
              <div>
                <strong>{fmtYuan(s.amount_cents)}</strong> · {s.purpose || '未填用途'}
                <p className="muted">
                  #{s.requester_id} · {s.status}
                  {s.decision_reason && ` · ${s.decision_reason}`}
                </p>
              </div>
              <span className="row">
                {/* UI-075 读服务端的 can_decide：自己批自己不算审批 */}
                {s.can_decide && (
                  <>
                    <button onClick={() => act(() => client.decideTeamSpend(teamId, s.id, true))}>批准</button>
                    <button className="danger" onClick={() => {
                      const reason = prompt('驳回理由：') ?? '';
                      void act(() => client.decideTeamSpend(teamId, s.id, false, reason));
                    }}>驳回</button>
                  </>
                )}
                {s.status === 'approved' && (
                  <button className="ghost" onClick={() => act(() => client.executeTeamSpend(teamId, s.id))}>
                    执行
                  </button>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>企业信息与发票</h3>
        {/* UI-075 开票按钮读服务端的 invoice_block，理由原样显示 */}
        {team.invoice_block
          ? <p className="error" data-testid="invoice-block">{team.invoice_block}</p>
          : <p className="muted">企业信息已核验，可以开具企业抬头发票。</p>}
        <p className="muted">
          当前：{team.company_name || '未提交'}（{team.verify_status}）
          {team.verify_reason && ` · ${team.verify_reason}`}
        </p>
        <button className="ghost" onClick={() => {
          const companyName = prompt('企业名称：');
          if (!companyName) return;
          const taxNumber = prompt('统一社会信用代码：') ?? '';
          void act(() => client.submitTeamCompany(teamId, companyName, taxNumber));
        }}>
          提交企业信息（转人工核验）
        </button>
      </div>
    </>
  );
}

function TeamMembers({ teamId, team, onChanged }: { teamId: number; team: TeamDetail; onChanged: () => void }) {
  const { client } = useApp();
  const [userId, setUserId] = useState('');
  const [limit, setLimit] = useState('0');
  const [notice, setNotice] = useState('');
  // TEAM-054（170 号 spec）移出后的交接说明（单独一行，「已移出」照旧）
  const [handover, setHandover] = useState('');
  const [error, setError] = useState('');
  const owner = team.my_role === 'owner';
  async function act(fn: () => Promise<unknown>, done: string) {
    setError(''); setNotice(''); setHandover('');
    try { await fn(); if (done) setNotice(done); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  const ROLE: Record<string, string> = { owner: '所有者', admin: '管理员', member: '成员' };
  return (
    <div aria-label="团队成员">
      <h4>成员（{team.members.length}）</h4>
      <table>
        <thead><tr><th>成员</th><th>角色</th><th>月度额度</th>{owner && <th>操作</th>}</tr></thead>
        <tbody>
          {team.members.map((m) => (
            <tr key={m.user_id}>
              <td><Link to={`/people/${m.user_id}`}>{m.nickname || `用户 #${m.user_id}`}</Link></td>
              <td>{ROLE[m.role] ?? m.role}</td>
              <td>{fmtYuan(m.spend_limit_cents)}</td>
              {owner && <td>{m.role !== 'owner' && <>
                <button className="text-link" onClick={() => void act(() => client.updateTeamMember(teamId, m.user_id, { role: m.role === 'admin' ? 'member' : 'admin' }), '角色已更新')}>
                  {m.role === 'admin' ? '设为成员' : '设为管理员'}</button>
                {' '}<button className="text-link" onClick={() => {
                  const yuan = prompt('这个成员的月度额度（元）：', String(m.spend_limit_cents / 100));
                  if (yuan !== null) void act(() => client.updateTeamMember(teamId, m.user_id, { spend_limit_cents: Math.round(parseFloat(yuan || '0') * 100) }), '额度已更新');
                }}>改额度</button>
                {' '}<button className="text-link" onClick={() => {
                  if (window.confirm(`把 ${m.nickname || m.user_id} 移出团队？移出后对方不能再用团队的钱。`)) void act(async () => setHandover(teamHandoverDetail(await client.removeTeamMember(teamId, m.user_id))), '已移出');
                }}>移出</button>
              </>}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {owner ? (
        <div className="row">
          <input aria-label="成员用户编号" type="number" placeholder="对方的用户编号（在对方个人空间地址里）" value={userId} onChange={(e) => setUserId(e.target.value)} />
          <input aria-label="月度额度" type="number" min={0} placeholder="月度额度（元）" value={limit} onChange={(e) => setLimit(e.target.value)} />
          <button disabled={!Number(userId)} onClick={() => void act(async () => {
            await client.addTeamMember(teamId, Number(userId), 'member', Math.round(Number(limit || '0') * 100));
            setUserId('');
          }, '已加入')}>加入团队</button>
        </div>
      ) : <p className="muted">只有团队所有者能管理成员。</p>}
      {notice && <p role="status">{notice}</p>}
      {handover && <p className="muted" data-testid="team-handover">{handover}</p>}
      {error && <p className="error">{error}</p>}
      {owner && <InviteLinks teamId={teamId} />}
    </div>
  );
}

/** TEAM-066 邀请链接（147 号 spec）：不用让对方先报用户编号。链接只显示一次，用完、过期或作废就失效。 */
function InviteLinks({ teamId }: { teamId: number }) {
  const { client } = useApp();
  const [rows, setRows] = useState<TeamInviteLink[]>([]);
  const [limit, setLimit] = useState('0');
  const [uses, setUses] = useState('1');
  const [fresh, setFresh] = useState('');
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const r = await client.teamInviteLinks(teamId).catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client, teamId]);
  useEffect(() => { void load(); }, [load]);
  const STATE: Record<string, string> = { active: '有效', used_up: '已用完', expired: '已过期', revoked: '已作废' };
  return (
    <div aria-label="邀请链接">
      <h4>邀请链接</h4>
      <div className="row">
        <input aria-label="链接的月度额度" type="number" min={0} placeholder="加入后的月度额度（元）" value={limit} onChange={(e) => setLimit(e.target.value)} />
        <input aria-label="可用次数" type="number" min={1} max={50} value={uses} onChange={(e) => setUses(e.target.value)} />
        <button onClick={() => void (async () => {
          setError('');
          try {
            const r = await client.createTeamInviteLink(teamId, { spend_limit_cents: Math.round(Number(limit || '0') * 100), max_uses: Number(uses || '1') });
            setFresh(`${window.location.origin}${r.path}`);
            await load();
          } catch (e) { setError(apiErrorText(e)); }
        })()}>生成邀请链接（7 天有效）</button>
      </div>
      {fresh && <p role="status" data-testid="fresh-invite">把这条链接发给对方（只显示这一次）：<code>{fresh}</code></p>}
      {error && <p className="error">{error}</p>}
      <ul className="muted">
        {rows.map((r) => (
          <li key={r.id}>额度 {fmtYuan(r.spend_limit_cents)} · 已用 {r.uses}/{r.max_uses} · {STATE[r.state] ?? r.state}
            {r.state === 'active' && <> <button className="text-link" onClick={() => void client.revokeTeamInviteLink(teamId, r.id).then(load)}>作废</button></>}</li>
        ))}
      </ul>
    </div>
  );
}
