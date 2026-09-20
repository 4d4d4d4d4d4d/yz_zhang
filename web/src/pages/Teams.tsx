import {
  apiErrorText, fmtYuan,
  type SpendRequestView, type TeamDetail, type TeamView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
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
          我的角色 {team.my_role} · 我的额度 {fmtYuan(team.my_spend_limit_cents)}
        </p>
        {error && <p className="error">{error}</p>}
        {notice && <p className="muted" data-testid="spend-notice">{notice}</p>}

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
