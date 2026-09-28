// 管理后台（12.E）：指标看板 / 举报处置队列 / 用户管理 / **提现复核** / 可疑活动
//
// PAY-040：提现复核台此前**不存在**。V82 的覆盖闸门把这两个端点豁免掉了，
// 理由写着「提现人审是风控岗位的动作，在管理后台做」——那句话是对的，
// 同时也是一个承诺，而**没有任何东西核对过那个地方是否真的有这一条**。
// 于是 V91 把提现接通之后，大额进人审的钱就冻在那儿，没有任何界面能放行。
import { apiErrorText, fmtYuan, formatDateTime, type AdminAuditRow, type BanImpactView, type PlatformFinanceView, type SuspiciousActivityRow, type WithdrawRequestRow } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

type Metrics = {
  total_users: number; verified_users: number; total_tasks: number; published_tasks: number;
  completed_tasks: number; closed_loop_rate: number; dispute_count: number;
  gmv_cents: number; fee_income_cents: number;
};
type ReportRow = { id: number; reporter_id: number; target_type: string; target_id: number; reason: string };
type UserRow = { id: number; phone: string; nickname: string; is_verified: boolean; is_banned: boolean; credit_score: number; tasks_completed: number };

export default function Admin() {
  const { client, me } = useApp();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [q, setQ] = useState('');
  const [banning, setBanning] = useState<number | null>(null);

  const load = useCallback(async () => {
    setMetrics(await client.adminMetrics());
    setReports(await client.adminReports());
    setUsers(await client.adminUsers(q));
  }, [client, q]);

  useEffect(() => {
    if (me?.is_admin) void load();
  }, [me, load]);

  if (!me) return <div className="page"><p className="muted">加载中…</p></div>;
  if (!me.is_admin) return <div className="page"><div className="card error">需要管理员权限</div></div>;

  return (
    <div className="page">
      {metrics && (
        <div className="card">
          <h3>平台指标</h3>
          <div className="row" style={{ gap: 28, marginTop: 10, flexWrap: 'wrap' }}>
            <Stat label="任务闭环率（北极星）" value={`${(metrics.closed_loop_rate * 100).toFixed(1)}%`} />
            <Stat label="GMV" value={fmtYuan(metrics.gmv_cents)} />
            <Stat label="佣金收入" value={fmtYuan(metrics.fee_income_cents)} />
            <Stat label="用户 / 实名" value={`${metrics.total_users} / ${metrics.verified_users}`} />
            <Stat label="任务 总/招募/完成" value={`${metrics.total_tasks}/${metrics.published_tasks}/${metrics.completed_tasks}`} />
            <Stat label="纠纷数" value={String(metrics.dispute_count)} />
          </div>
        </div>
      )}
      <WithdrawReview />
      <AmlQueue />
      <div className="card">
        <h3>待处置举报（{reports.length}）</h3>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>#</th><th>对象</th><th>理由</th><th>处置</th></tr></thead>
          <tbody>
            {reports.length === 0 && <tr><td colSpan={4} className="muted">队列为空</td></tr>}
            {reports.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.target_type}#{r.target_id}</td>
                <td>{r.reason}</td>
                <td className="row">
                  <button className="ghost" style={{ padding: '2px 8px' }}
                          onClick={async () => { await client.resolveReport(r.id, 'dismiss'); await load(); }}>驳回</button>
                  <button style={{ padding: '2px 8px' }}
                          onClick={async () => { await client.resolveReport(r.id, 'remove_content'); await load(); }}>下架</button>
                  <button className="danger" style={{ padding: '2px 8px' }}
                          onClick={async () => { await client.resolveReport(r.id, 'ban_user'); await load(); }}>封禁</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <div className="row">
          <h3 className="grow">用户管理</h3>
          <input style={{ width: 200 }} placeholder="搜昵称/手机号" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="ghost" onClick={() => void load()}>查询</button>
        </div>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>ID</th><th>昵称</th><th>手机</th><th>信用</th><th>完成单</th><th>状态</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td><td>{u.nickname}</td><td>{u.phone}</td>
                <td>{u.credit_score}</td><td>{u.tasks_completed}</td>
                <td>{u.is_banned ? <span className="badge bad">已封禁</span> : u.is_verified ? <span className="badge ok">实名</span> : <span className="badge">正常</span>}</td>
                <td>
                  {u.is_banned ? (
                    <button className="ghost" style={{ padding: '2px 8px' }}
                            onClick={async () => { await client.unbanUser(u.id); await load(); }}>解封</button>
                  ) : (
                    <button className="danger" style={{ padding: '2px 8px' }}
                            onClick={() => setBanning(u.id)}>封禁</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {banning !== null && (
          <BanConfirm userId={banning} onClose={() => setBanning(null)}
                      onDone={async () => { setBanning(null); await load(); }} />
        )}
      </div>
      <AuditLog />
      <PlatformFinance />
      <Announcement />
    </div>
  );
}

/** MOD-060 封禁前先看影响面。
 *
 * V58 专门算了这些数（在途合约、受影响的托管资金、会被下架的招募中任务），
 * 而管理后台此前直接调 `banUser`——**管理员在盲封**。
 * 封禁是不可逆的处置，代价必须在按下之前摆在眼前。
 */
function BanConfirm({ userId, onClose, onDone }: {
  userId: number; onClose: () => void; onDone: () => Promise<void>;
}) {
  const { client } = useApp();
  const [impact, setImpact] = useState<BanImpactView | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void client.banImpact(userId).then(setImpact).catch((e) => setError(apiErrorText(e)));
  }, [client, userId]);

  return (
    <div className="card" style={{ marginTop: 10 }} data-testid="ban-confirm">
      <h4>封禁用户 #{userId} 之前，先看这些</h4>
      {error && <p className="error">{error}</p>}
      {!impact ? <p className="muted">正在算影响面…</p> : (
        <>
          <p className={impact.escrow_at_risk_cents > 0 ? 'error' : 'muted'} data-testid="ban-escrow">
            在途合约 {impact.in_flight_count} 笔，涉及托管资金 {fmtYuan(impact.escrow_at_risk_cents)}
          </p>
          <p className="muted" data-testid="ban-tasks">
            招募中的任务 {impact.open_task_count} 个会被下架
            {impact.open_task_ids.length > 0 && `（#${impact.open_task_ids.join(', #')}）`}
          </p>
          <p className="muted">
            钱包：可用 {fmtYuan(impact.wallet.available_cents)} ·
            托管 {fmtYuan(impact.wallet.escrow_cents)} ·
            冻结 {fmtYuan(impact.wallet.frozen_cents)}
          </p>
          {impact.in_flight_contracts.map((c) => (
            <p className="muted" key={c.contract_id}>
              合约 #{c.contract_id}（任务 #{c.task_id}）{c.status} · {fmtYuan(c.amount_cents)} ·
              对手方 #{c.counterparty_id}
            </p>
          ))}
        </>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="danger" disabled={busy || !impact} onClick={async () => {
          setBusy(true);
          try { await client.banUser(userId); await onDone(); }
          catch (e) { setError(apiErrorText(e)); }
          finally { setBusy(false); }
        }}>我已知晓影响，确认封禁</button>
        <button className="ghost" onClick={onClose}>取消</button>
      </div>
    </div>
  );
}

/** ADMIN-060 审计日志。**谁批了那笔三万块**——此前这个问题只能靠查数据库
 *  回答，而那不是合规底线该有的样子。 */
function AuditLog() {
  const { client } = useApp();
  const [rows, setRows] = useState<AdminAuditRow[]>([]);
  const [action, setAction] = useState('');

  const load = useCallback(async () => {
    setRows(await client.adminAuditLog({ action: action || undefined, limit: 50 }).catch(() => []));
  }, [client, action]);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="card">
      <div className="row">
        <h3 className="grow">管理员审计日志</h3>
        <input style={{ width: 180 }} placeholder="按动作过滤，如 withdraw_approve"
               value={action} onChange={(e) => setAction(e.target.value)} />
        <button className="ghost" onClick={() => void load()}>查询</button>
      </div>
      {rows.length === 0 ? <p className="muted">没有匹配的记录。</p> : (
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>时间</th><th>管理员</th><th>动作</th><th>对象</th><th>说明</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="muted">{formatDateTime(r.created_at)}</td>
                <td>#{r.admin_id}</td>
                <td><span className="badge">{r.action}</span></td>
                <td className="muted">{r.target_type}{r.target_id !== null ? ` #${r.target_id}` : ''}</td>
                <td className="muted">{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** FIN-060 平台自己的钱。结算是把佣金从平台账户划走的动作，
 *  同样要留审计——所以放在后台而不是脚本里。 */
function PlatformFinance() {
  const { client } = useApp();
  const [fin, setFin] = useState<PlatformFinanceView | null>(null);
  const [amount, setAmount] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setFin(await client.platformFinance().catch(() => null));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  if (!fin) return null;
  return (
    <div className="card">
      <h3>平台财务</h3>
      <div className="row" style={{ gap: 28, marginTop: 10, flexWrap: 'wrap' }}>
        <Stat label="账上余额" value={fmtYuan(fin.balance_cents)} />
        <Stat label="累计佣金" value={fmtYuan(fin.total_fee_cents)} />
        <Stat label="已结算" value={fmtYuan(fin.settled_cents)} />
        <Stat label="佣金笔数" value={String(fin.fee_count)} />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <input style={{ width: 140 }} type="number" min={0.01} step={0.01} placeholder="结算金额（元）"
               value={amount} onChange={(e) => setAmount(e.target.value)} />
        <button disabled={!amount} onClick={async () => {
          setError('');
          try {
            await client.settlePlatform(Math.round(parseFloat(amount) * 100));
            setAmount('');
            await load();
          } catch (e) { setError(apiErrorText(e)); }
        }}>结算划出</button>
      </div>
      {error && <p className="error">{error}</p>}
      <p className="muted">结算只动平台自己的收入；代扣税款在独立专户，不与佣金混同。</p>
    </div>
  );
}

/** NTF-060b 全站公告。发出去就收不回来，所以按下之前先说清会送给多少人。 */
function Announcement() {
  const { client } = useApp();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  return (
    <div className="card">
      <h3>发布全站公告</h3>
      <div className="row">
        <input style={{ width: 200 }} placeholder="标题" value={title}
               onChange={(e) => setTitle(e.target.value)} />
        <input className="grow" placeholder="正文" value={body}
               onChange={(e) => setBody(e.target.value)} />
        <label className="muted">
          <input type="checkbox" checked={verifiedOnly}
                 onChange={(e) => setVerifiedOnly(e.target.checked)} /> 仅已实名
        </label>
        <button disabled={title.trim().length < 2} onClick={async () => {
          setNotice(''); setError('');
          try {
            const r = await client.broadcastAnnouncement(title.trim(), body, verifiedOnly);
            setTitle(''); setBody('');
            // 送达人数原样回显：公告发出去收不回来，得让人看到自己刚影响了多少人
            setNotice(`已送达 ${r.delivered} 人`);
          } catch (e) { setError(apiErrorText(e)); }
        }}>发布</button>
      </div>
      {notice && <p className="muted" data-testid="ann-result">{notice}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="muted">{label}</p>
      <h2>{value}</h2>
    </div>
  );
}


/** PAY-040 提现复核台。
 *
 * 队列每行带上做判断需要的东西：昵称、是否实名、注册时间、历史提现累计，
 * 以及**这笔申请命中的 AML 标记**（那些标记 V55 就在写库，此前没人读）。
 *
 * 命中依据只出现在这里——AML-030/031 的分界是「合规官看得到为什么，
 * 用户只看到中性话术」。
 */
function WithdrawReview() {
  const { client } = useApp();
  const [rows, setRows] = useState<WithdrawRequestRow[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setRows(await client.withdrawRequests('pending').catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function decide(id: number, approve: boolean) {
    setError(''); setBusy(true);
    try { await client.decideWithdraw(id, approve); await load(); }
    catch (err) { setError(apiErrorText(err)); }
    finally { setBusy(false); }
  }

  const frozen = rows.reduce((a, r) => a + r.amount_cents, 0);

  return (
    <div className="card">
      <h3>提现复核（{rows.length}）</h3>
      {rows.length === 0
        ? <p className="muted">没有待复核的提现。</p>
        : <p className="muted">这些钱正冻在用户账上等人放行，合计 {fmtYuan(frozen)}。</p>}
      {error && <p className="error">{error}</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((r) => (
          <div className="task-item" key={r.id} data-testid={`wd-${r.id}`}>
            <div>
              <strong>{fmtYuan(r.amount_cents)}</strong> · {r.nickname || `用户 #${r.user_id}`}
              {r.is_verified ? <span className="badge ok">已实名</span> : <span className="badge warn">未实名</span>}
              <p className="muted">
                申请于 {formatDateTime(r.created_at)}
                {r.registered_at && ` · 注册于 ${formatDateTime(r.registered_at)}`}
                {` · 历史已提现 ${fmtYuan(r.withdrawn_total_cents)}`}
              </p>
              {/* 命中依据带具体数值：只写「疑似拆分」，复核的人无从判断 */}
              {r.flags.length > 0 && (
                <p className="error" data-testid={`wd-flags-${r.id}`}>
                  命中 {r.flags.length} 条：{r.flags.map((f) => `${f.pattern}（${f.detail}）`).join('；')}
                </p>
              )}
            </div>
            <span className="row">
              <button disabled={busy} onClick={() => decide(r.id, true)}>批准打款</button>
              <button className="danger" disabled={busy} onClick={() => decide(r.id, false)}>驳回退回</button>
            </span>
          </div>
        ))}
      </div>
      <p className="muted">
        驳回后款项退回用户可用余额。**给用户的通知不含任何原因**——
        《反洗钱法》第五条的保密义务，说了也等于教对方下次怎么规避。
      </p>
    </div>
  );
}

/** AML-040 可疑活动复核。三个端点 V55 就建好了，SDK 里一个都没有
 *  （它们在 /admin 下，被覆盖闸门整体跳过），于是标记躺在库里没人复核。 */
function AmlQueue() {
  const { client } = useApp();
  const [rows, setRows] = useState<SuspiciousActivityRow[]>([]);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const r = await client.amlActivities('pending').catch(() => null);
    setRows(r?.items ?? []);
    setNote(r?.note ?? '');
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function review(id: number, decision: 'cleared' | 'to_report' | 'reported') {
    setError('');
    try {
      const reason = prompt('复核说明（会记入合规档案）：') ?? '';
      await client.reviewAmlActivity(id, decision, reason);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  if (rows.length === 0) return null;
  return (
    <div className="card">
      <h3>可疑活动待复核（{rows.length}）</h3>
      {error && <p className="error">{error}</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((r) => (
          <div className="task-item" key={r.id}>
            <div>
              <strong>{r.pattern_label}</strong> · 用户 #{r.user_id} · {fmtYuan(r.amount_cents)}
              <p className="muted">{r.detail} · {formatDateTime(r.at)}</p>
            </div>
            <span className="row">
              <button className="ghost" onClick={() => review(r.id, 'cleared')}>复核无问题</button>
              <button onClick={() => review(r.id, 'to_report')}>标记待报送</button>
            </span>
          </div>
        ))}
      </div>
      {/* 平台不自动对外报送，报送与否由合规官判断——这句提示原样来自服务端 */}
      {note && <p className="muted">{note}</p>}
    </div>
  );
}
