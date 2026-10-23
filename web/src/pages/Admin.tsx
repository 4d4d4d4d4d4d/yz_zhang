// 管理后台（12.E）：指标看板 / 举报处置队列 / 用户管理 / **提现复核** / 可疑活动
//
// PAY-040：提现复核台此前**不存在**。V82 的覆盖闸门把这两个端点豁免掉了，
// 理由写着「提现人审是风控岗位的动作，在管理后台做」——那句话是对的，
// 同时也是一个承诺，而**没有任何东西核对过那个地方是否真的有这一条**。
// 于是 V91 把提现接通之后，大额进人审的钱就冻在那儿，没有任何界面能放行。
import { apiErrorText, asList, autoVerifyLevel, autoVerifyLine, type AutoVerifyUsage, canSeeAdminSection, fmtYuan, formatDateTime, hiddenAdminSections, type AdminSectionKey, type ClientErrorRow, type AdminAuditRow, type AdminRow, type AuditChainReport, type AdminTicketDetail, type AdminTicketRow, type SupportAgentStatus, type SupportScope, type SupportScheduleWindow, type TicketCategory, type AnnouncementAudience, type AnnouncementReadByCategory, type AnnouncementReadCurve, type AnnouncementPreview, type AnnouncementRow, type ReviewQueuesView, type BanImpactView, type PendingCertificationRow, type PendingTeamRow, type PendingUploadRow, type PlatformFinancePeriods, type PlatformGmvTaxPeriods, type PlatformFinanceView, type PlatformSettleRequestRow, type SecurityBoardView, type SuspiciousActivityRow, type WithdrawRequestRow } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { KnowledgeAdmin } from '../AdminKnowledge';
import { LegalFaqAdmin } from '../AdminLegal';
import { PacksAdmin } from '../AdminPacks';
import { SandboxModelsAdmin } from '../AdminSandbox';
import { SkillConceptsAdmin } from '../AdminSkills';
import { AdminRolesPanel } from '../AdminRoles';
import { useApp } from '../store';
import { TicketImages } from './Support';
import { ApiQuotasAdmin } from '../AdminApiQuotas';
import PhotoPicker from '../PhotoPicker';

type Metrics = {
  total_users: number; verified_users: number; total_tasks: number; published_tasks: number;
  completed_tasks: number; closed_loop_rate: number; dispute_count: number;
  gmv_cents: number; fee_income_cents: number;
  auto_verify?: AutoVerifyUsage;
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
  const [clientErrors, setClientErrors] = useState<ClientErrorRow[]>([]);

  // SEC-061d（165 号 spec）：只加载看得到的板块——以前财务一进后台，举报与用户两个请求就 403，整段加载跟着失败
  const see = (k: AdminSectionKey) => canSeeAdminSection(me, k);
  const load = useCallback(async () => {
    if (canSeeAdminSection(me, 'metrics')) setMetrics(await client.adminMetrics());
    if (canSeeAdminSection(me, 'reports')) setReports(await client.adminReports());
    if (canSeeAdminSection(me, 'users')) setUsers(await client.adminUsers(q));
    // APP-094（184 号 spec）哪一页常坏
    if (canSeeAdminSection(me, 'clientErrors')) setClientErrors(asList(await client.adminClientErrors().catch(() => [])));
  }, [client, q, me]);

  useEffect(() => {
    if (me?.is_admin) void load();
  }, [me, load]);

  if (!me) return <div className="page"><p className="muted">加载中…</p></div>;
  if (!me.is_admin) return <div className="page"><div className="card error">需要管理员权限</div></div>;

  return (
    <div className="page">
      {see('clientErrors') && (
        <div className="card" aria-label="页面出错">
          <h3>页面出错（近 7 天）</h3>
          {typeof clientErrors[0]?.alert_people === 'number' && (
            <p className="muted">同一端同一页 24 小时内坏过的不同用户到 {clientErrors[0].alert_people} 人，会给运营发站内信（每页 24 小时一次）。</p>
          )}
          {clientErrors.length === 0 ? <p className="muted">近 7 天没有页面渲染出错的上报。</p> : (
            <table>
              <thead><tr><th>端</th><th>页面</th><th>错误类型</th><th>次数</th><th>人数</th><th>最近一次</th><th>提醒运营</th></tr></thead>
              <tbody>
                {clientErrors.map((r) => (
                  <tr key={`${r.platform}${r.page}${r.kind}`}>
                    <td>{r.platform === 'web' ? '网页' : 'App'}</td><td>{r.page}</td><td>{r.kind}</td>
                    <td>{r.count}</td><td>{r.people}</td><td>{formatDateTime(r.last_at)}</td>
                    <td>{r.alerted_at ? `已提醒 ${formatDateTime(r.alerted_at)}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {see('metrics') && metrics && (
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
          {/* AGT-073（224 号 spec）平台自费核验的用量：用完了之后拿不准的交付不再自动请人看 */}
          {metrics.auto_verify && (
            <p data-testid="auto-verify-usage" className={autoVerifyLevel(metrics.auto_verify) === 'ok' ? 'muted' : 'error'}>
              {autoVerifyLine(metrics.auto_verify)}
            </p>
          )}
        </div>
      )}
      {see('roles') && <AdminRolesPanel />}
      {see('launch') && <LaunchReadiness />}
      {see('queues') && <QueueOverview />}
      {see('withdraw') && <WithdrawReview />}
      {see('aml') && <AmlQueue />}
      {see('knowledge') && <KnowledgeAdmin />}
      {see('packs') && <PacksAdmin />}
      {see('legal') && <LegalFaqAdmin />}
      {see('sandbox') && <SandboxModelsAdmin />}
      {see('skills') && <SkillConceptsAdmin />}
      {see('teams') && <TeamVerifyQueue />}
      {see('certifications') && <CertificationQueue />}
      {see('uploads') && <UploadQueue />}
      {see('tickets') && <TicketQueue />}
      {see('reports') && <div className="card" aria-label="举报处置">
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
      </div>}
      {see('users') && <div className="card" aria-label="用户管理">
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
      </div>}
      {see('security') && <SecurityBoard />}
      {see('cities') && <CityAndCategory />}
      {see('audit') && <AuditLog />}
      {see('finance') && <PlatformFinance />}
      {see('announcements') && <Announcement />}
      {/* API-056（235 号 spec） */}
      {see('apiQuotas') && <ApiQuotasAdmin />}
      {hiddenAdminSections(me).length > 0 && (
        <p className="muted" aria-label="不在你职责里的板块">
          这些板块不在你的职责里，所以没有显示：{hiddenAdminSections(me).join('、')}。需要的话请超级管理员在「管理员与角色」里给你加上对应角色。
        </p>
      )}
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
  const [total, setTotal] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [f, setF] = useState({ action: '', admin_id: '', target_type: '', target_id: '', since: '', until: '', q: '' });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const PAGE = 50;
  // ADMIN-061 筛选条件（143 号 spec）：日期按北京时间的整天算，换成 UTC 交给服务端
  const filter = useCallback(() => ({
    action: f.action || undefined, target_type: f.target_type || undefined, q: f.q || undefined,
    admin_id: f.admin_id ? Number(f.admin_id) : undefined, target_id: f.target_id ? Number(f.target_id) : undefined,
    since: f.since ? `${f.since}T00:00:00+08:00` : undefined,
    // 结束日期这一天整天都算：到北京时间当天 23:59:59.999999（服务端按「早于」比较）
    until: f.until ? `${f.until}T23:59:59.999999+08:00` : undefined,
  }), [f]);

  const load = useCallback(async (p = 0) => {
    setError('');
    try {
      const r = await client.adminAuditLogPage({ ...filter(), limit: PAGE, offset: p * PAGE });
      setRows(r.items); setTotal(r.total); setPage(p);
    } catch (e) { setRows([]); setError(apiErrorText(e)); }
  }, [client, filter]);
  useEffect(() => { void load(0); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  async function exportCsv() {
    setError(''); setNotice('');
    try {
      const r = await client.exportAuditLog(filter());
      const url = URL.createObjectURL(new Blob(['\ufeff' + r.csv], { type: 'text/csv;charset=utf-8' }));
      const a = document.createElement('a'); a.href = url; a.download = r.filename; a.click(); URL.revokeObjectURL(url);
      setNotice(`已导出 ${r.rows} 行（时间为${r.timezone}）${r.truncated ? `；共 ${r.total} 行，超过上限只导出了最新的 ${r.rows} 行，请缩小时间段` : ''}。导出已记入审计。`);
    } catch (e) { setError(apiErrorText(e)); }
  }
  // ADMIN-062 完整性自检（149 号 spec）
  const [chain, setChain] = useState<AuditChainReport | null>(null);
  async function verifyChain() {
    setError(''); setChain(null);
    try { setChain(await client.verifyAuditChain()); } catch (e) { setError(apiErrorText(e)); }
  }
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const pages = total === null ? null : Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="card" aria-label="管理员审计日志">
      <h3>管理员审计日志</h3>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <input style={{ width: 170 }} aria-label="动作" placeholder="动作，如 withdraw_approve" value={f.action} onChange={set('action')} />
        <input style={{ width: 100 }} aria-label="管理员编号" type="number" placeholder="管理员编号" value={f.admin_id} onChange={set('admin_id')} />
        <input style={{ width: 110 }} aria-label="对象类型" placeholder="对象类型" value={f.target_type} onChange={set('target_type')} />
        <input style={{ width: 90 }} aria-label="对象编号" type="number" placeholder="对象编号" value={f.target_id} onChange={set('target_id')} />
        <input aria-label="开始日期" type="date" value={f.since} onChange={set('since')} />
        <input aria-label="结束日期" type="date" value={f.until} onChange={set('until')} />
        <input style={{ width: 140 }} aria-label="说明包含" placeholder="说明里包含" value={f.q} onChange={set('q')} />
        <button className="ghost" onClick={() => void load(0)}>查询</button>
        <button className="ghost" onClick={() => void exportCsv()}>导出 CSV</button>
        <button className="ghost" onClick={() => void verifyChain()}>校验完整性</button>
      </div>
      {chain && (
        <div aria-label="审计完整性" className={chain.ok ? 'muted' : 'error'}>
          {chain.ok
            ? <p>完整：链上 {chain.checked} 条逐条对得上，最新一条是 #{chain.head_audit_id}。{chain.legacy_unchained > 0 && `另有 ${chain.legacy_unchained} 条是启用哈希链之前的旧记录，不在链上。`}
                {/* ADMIN-063（156 号 spec）存证锚点 */}
                {chain.anchors_checked > 0
                  ? ` 存证锚点 ${chain.anchors_checked} 个都对得上，最近一次锚定到 #${chain.last_anchor_audit_id}（${formatDateTime(chain.last_anchored_at ?? '')}）。`
                  : ' 还没有存证锚点（每天自动锚定一次）。'}</p>
            : (<>
                <p>发现断点：日志可能被改过或删过。请保留现场，交合规负责人和数据库管理员核查。</p>
                <ul>{chain.problems.map((x, i) => <li key={i}>#{x.audit_id}：{x.reason}</li>)}</ul>
              </>)}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
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
      <div className="row">
        <button className="ghost" disabled={page === 0} onClick={() => void load(page - 1)}>上一页</button>
        <span className="muted" data-testid="audit-pages">第 {page + 1}{pages !== null ? ` / ${pages}` : ''} 页{total !== null ? ` · 共 ${total} 条` : ''}</span>
        <button className="ghost" disabled={pages !== null ? page + 1 >= pages : rows.length < PAGE} onClick={() => void load(page + 1)}>下一页</button>
      </div>
    </div>
  );
}

/** FIN-060 平台自己的钱。结算是把佣金从平台账户划走的动作，
 *  同样要留审计——所以放在后台而不是脚本里。 */
function PlatformFinance() {
  const { client } = useApp();
  const [fin, setFin] = useState<PlatformFinanceView | null>(null);
  const [amount, setAmount] = useState('');
  const [notice, setNotice] = useState('');
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
          setError(''); setNotice('');
          try {
            const r = await client.settlePlatform(Math.round(parseFloat(amount) * 100));
            // SEC-061c 大额结算先等第二位财务确认（148 号 spec）：钱还没动，说清楚
            if ('status' in r && r.status === 'awaiting_second') setNotice(r.message);
            setAmount('');
            await load();
          } catch (e) { setError(apiErrorText(e)); }
        }}>结算划出</button>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <SettleRequests onChanged={() => void load()} />
      <p className="muted">结算只动平台自己的收入；代扣税款在独立专户，不与佣金混同。</p>
      <FinancePeriods />
    </div>
  );
}

/** SEC-061c / PAY-042b 待第二位财务确认的结算（148 号 spec）：发起人自己不能确认，可以撤回；驳回别人的要写理由。 */
function SettleRequests({ onChanged }: { onChanged: () => void }) {
  const { client } = useApp();
  const [rows, setRows] = useState<PlatformSettleRequestRow[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const r = await client.settleRequests().catch(() => []);
    setRows(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  if (rows.length === 0 && !error) return null;
  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); onChanged(); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="待确认的结算">
      <h4>待第二位财务确认的结算（{rows.length}）</h4>
      {error && <p className="error">{error}</p>}
      {rows.map((r) => (
        <div className="task-item" key={r.id}>
          <div>{fmtYuan(r.amount_cents)} · {r.memo} <span className="muted">由财务 #{r.requested_by} 于 {formatDateTime(r.created_at)} 发起；钱还没划出</span>
            {/* SEC-061f（155 号 spec） */}
            {r.needs_super_second && <span className="badge" data-testid={`settle-super-${r.id}`}>金额较大：须超级管理员确认</span>}</div>
          <span className="row">
            <button onClick={() => void act(() => client.approveSettle(r.id))}>确认划出</button>
            <button className="danger" onClick={() => {
              const reason = prompt('驳回理由（发起人自己撤回可以不写）：');
              if (reason !== null) void act(() => client.rejectSettle(r.id, reason));
            }}>驳回 / 撤回</button>
          </span>
        </div>
      ))}
    </div>
  );
}

/** FIN-062（242 号 spec）按期间的成交额与代扣税额：与平台收支分开，口径逐条写明，是草稿 */
function GmvTaxPeriods({ granularity }: { granularity: 'month' | 'quarter' }) {
  const { client } = useApp();
  const [data, setData] = useState<PlatformGmvTaxPeriods | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    client.platformGmvTax({ granularity })
      .then((d) => setData(d && Array.isArray(d.periods) ? d : null)).catch((e) => setError(apiErrorText(e)));
  }, [client, granularity]);
  const [notice, setNotice] = useState('');
  // FIN-066（249 号 spec）导出 CSV 给记账代理：表尾附口径与草稿提示
  async function exportCsv() {
    setError(''); setNotice('');
    try {
      const r = await client.exportPlatformGmvTax({ granularity });
      const url = URL.createObjectURL(new Blob(['\ufeff' + r.csv], { type: 'text/csv;charset=utf-8' }));
      const a = document.createElement('a'); a.href = url; a.download = r.filename; a.click(); URL.revokeObjectURL(url);
      setNotice(`已导出 ${r.rows} 个期间（起止时间为${r.timezone}，表尾附口径）。导出已记入审计。`);
    } catch (e) { setError(apiErrorText(e)); }
  }
  if (error && !data) return <p className="error">{error}</p>;
  if (!data) return null;
  return (
    <div aria-label="成交额与代扣税">
      <div className="row"><h4 className="grow">成交额与代扣税</h4><button className="ghost" onClick={() => void exportCsv()}>导出成交额与代扣税 CSV</button></div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      <p className="badge warn">{data.draft_note}</p>
      <table>
        <thead><tr><th>期间</th><th>成交额（按放款）</th><th>放款笔数</th><th>纠纷分账</th><th>退款</th><th>代扣税</th><th>被代扣人数</th><th>缴库</th><th>期末待缴</th></tr></thead>
        <tbody>
          {[...data.periods].reverse().map((r) => (
            <tr key={r.period} data-testid={`gmv-${r.period}`}>
              <td>{r.period}</td><td>{fmtYuan(r.gmv_cents)}</td><td>{r.release_count}</td><td>{fmtYuan(r.dispute_split_cents)}</td>
              <td>{fmtYuan(r.refund_cents)}</td><td>{fmtYuan(r.withheld_cents)}（{r.withheld_count} 笔）</td><td>{r.withheld_people}</td>
              <td>{fmtYuan(r.remitted_cents)}</td><td>{fmtYuan(r.tax_pending_cents)}
                {/* FIN-067（258 号 spec）锁过账的月份读快照，锁账后又记进来的另报 */}
                {r.closed && <span className="badge"> 已锁</span>}
                {r.closed && ((r.late_gmv_cents ?? 0) !== 0 || (r.late_withheld_cents ?? 0) !== 0) &&
                  <span className="muted"> 锁账后又记进成交额 {fmtYuan(r.late_gmv_cents ?? 0)}、代扣 {fmtYuan(r.late_withheld_cents ?? 0)}，未计入上面的数</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details><summary>口径</summary><ul>{(Array.isArray(data.basis) ? data.basis : []).map((b) => <li key={b}>{b}</li>)}</ul></details>
    </div>
  );
}

/** FIN-061 按期间的平台财务（144 号 spec）：本月佣金、本季结算。期间按北京时间自然月 / 季度。 */
function FinancePeriods() {
  const { client } = useApp();
  const [granularity, setGranularity] = useState<'month' | 'quarter'>('month');
  const [data, setData] = useState<PlatformFinancePeriods | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    client.platformFinancePeriods({ granularity })
      .then((d) => setData(d && Array.isArray(d.periods) ? d : null)).catch((e) => setError(apiErrorText(e)));
  }, [client, granularity, reload]);
  // FIN-063（223 号 spec）锁账：锁过的月份报表不再变，补记记到第一个未锁月份；不能解锁，所以按下前说清
  const [through, setThrough] = useState('');
  async function lock() {
    setError(''); setNotice('');
    if (!through) { setError('先选要锁到哪个月'); return; }
    if (!window.confirm(`锁账到 ${through}（含）之后，这些月份的报表不再变化，之后补记的流水记到下一个未锁月份。锁了不能解锁，确定吗？`)) return;
    try {
      const r = await client.lockPlatformFinance(through);
      setNotice(`已锁到 ${r.locked_through}（这次锁了 ${r.months.length} 个月：${r.months[0]}~${r.months[r.months.length - 1]}）。已记入审计。`);
      setReload((n) => n + 1);
    } catch (e) { setError(apiErrorText(e)); }
  }
  async function exportCsv() {
    setError(''); setNotice('');
    try {
      const r = await client.exportPlatformFinancePeriods({ granularity });
      const url = URL.createObjectURL(new Blob(['\ufeff' + r.csv], { type: 'text/csv;charset=utf-8' }));
      const a = document.createElement('a'); a.href = url; a.download = r.filename; a.click(); URL.revokeObjectURL(url);
      setNotice(`已导出 ${r.rows} 个期间（起止时间为${r.timezone}）。导出已记入审计。`);
    } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="按期间">
      <div className="row">
        <h4 className="grow">按期间</h4>
        <select aria-label="期间粒度" value={granularity} onChange={(e) => setGranularity(e.target.value as 'month' | 'quarter')}>
          <option value="month">按月（最近 12 个月）</option>
          <option value="quarter">按季度（最近 4 个季度）</option>
        </select>
        <button className="ghost" onClick={() => void exportCsv()}>导出 CSV</button>
      </div>
      <div className="row">
        <span className="muted grow" data-testid="finance-locked-through">
          {data?.locked_through ? `已锁到 ${data.locked_through}${data.locked_at ? `（${formatDateTime(data.locked_at)}）` : ''}：锁过的月份报表不再变` : '还没有锁过账：每次打开都按最新流水现算'}
        </span>
        <input type="month" aria-label="锁账到" value={through} onChange={(e) => setThrough(e.target.value)} />
        <button className="ghost" onClick={() => void lock()}>锁账到此月</button>
      </div>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {data && (
        <table>
          <thead><tr><th>期间</th><th>佣金</th><th>笔数</th><th>结算划出</th><th>补贴</th><th>其他</th><th>期末余额</th><th /></tr></thead>
          <tbody>
            {[...data.periods].reverse().map((r) => (
              <tr key={r.period}>
                <td>{r.period}</td><td>{fmtYuan(r.fee_cents)}</td><td>{r.fee_count}</td><td>{fmtYuan(r.settled_cents)}</td>
                <td>{fmtYuan(r.subsidy_cents)}</td><td>{fmtYuan(r.other_cents)}</td><td>{fmtYuan(r.closing_cents)}</td>
                <td data-testid={`period-note-${r.period}`}>
                  {r.balanced ? '' : <span className="badge warn">期末与期初对不上</span>}
                  {r.closed && <span className="badge"> 已锁</span>}
                  {r.closed && r.late_count > 0 && <span className="muted"> 锁账后又记进 {r.late_count} 笔（{fmtYuan(r.late_cents)}），已记到下一个未锁月份</span>}
                  {r.carried_in_count > 0 && <span className="muted"> 含补记以前期间 {r.carried_in_count} 笔（{fmtYuan(r.carried_in_cents)}）</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <GmvTaxPeriods granularity={granularity} />
    </div>
  );
}

/** NTF-060b 全站公告。发出去就收不回来，所以按下之前先说清会送给多少人。
 *  NTF-064（151 号 spec）：先预览（受众人数、要留意的地方）再发；可以定时；发错了可以撤回（写明理由），
 *  定时的还没发可以取消。下面列出发过的公告。 */
function Announcement() {
  const { client } = useApp();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  // 北京时间的日期与时刻，交给服务端前带上 +08:00
  const [when, setWhen] = useState('');
  // NTF-066（159 号 spec）定向
  const [city, setCity] = useState('');
  const [aud, setAud] = useState<AnnouncementAudience>('all');
  // NTF-068（238 号 spec）只发给某个类目的人
  const [cat, setCat] = useState('');
  // NTF-070（246 号 spec）「也发给」的类目
  const [extraCats, setExtraCats] = useState<string[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [preview, setPreview] = useState<AnnouncementPreview | null>(null);
  const [history, setHistory] = useState<AnnouncementRow[]>([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const loadHistory = useCallback(async () => {
    const r = await client.announcements().catch(() => []);
    setHistory(Array.isArray(r) ? r : []);
  }, [client]);
  useEffect(() => { void loadHistory(); }, [loadHistory]);
  useEffect(() => {
    void client.categories().then((r) => setCats(Array.isArray(r) ? r.map((c) => c.name) : []), () => setCats([]));
  }, [client]);

  async function run(fn: () => Promise<void>) {
    setNotice(''); setError('');
    try { await fn(); } catch (e) { setError(apiErrorText(e)); }
  }
  const draftChanged = () => setPreview(null);
  // 「发布」保持一步可发（原有行为）；预览是建议的前一步，发布时一并清掉
  const publish = () => run(async () => {
    const r = await client.broadcastAnnouncement(title.trim(), body, verifiedOnly, when ? `${when}:00+08:00` : undefined,
      { city: city.trim(), audience: aud, category: cat, categories: cat ? extraCats : [] });
    setTitle(''); setBody(''); setWhen(''); setPreview(null);
    // 送达人数原样回显：公告发出去收不回来，得让人看到自己刚影响了多少人
    setNotice(r.status === 'scheduled' ? `已定时，到 ${formatDateTime(r.scheduled_at ?? '')} 发出；发出前可以取消` : `已送达 ${r.delivered} 人`);
    await loadHistory();
  });

  return (
    <div className="card" aria-label="全站公告">
      <h3>发布全站公告</h3>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <input style={{ width: 200 }} placeholder="标题" value={title}
               onChange={(e) => { setTitle(e.target.value); draftChanged(); }} />
        <input className="grow" placeholder="正文" value={body}
               onChange={(e) => { setBody(e.target.value); draftChanged(); }} />
        <label className="muted">
          <input type="checkbox" checked={verifiedOnly}
                 onChange={(e) => { setVerifiedOnly(e.target.checked); draftChanged(); }} /> 仅已实名
        </label>
        <input style={{ width: 110 }} aria-label="只发给城市" placeholder="城市（可不填）" value={city}
               onChange={(e) => { setCity(e.target.value); draftChanged(); }} />
        <select aria-label="发给哪类人" value={aud} onChange={(e) => { setAud(e.target.value as AnnouncementAudience); draftChanged(); }}>
          <option value="all">全体用户</option>
          <option value="publishers">近 180 天发过单的人</option>
          <option value="workers">近 180 天报过名接单的人</option>
        </select>
        {cats.length > 0 && (
          <select aria-label="只发给类目" value={cat} onChange={(e) => { setCat(e.target.value); draftChanged(); }}>
            <option value="">不限类目</option>
            {cats.map((c) => <option key={c} value={c}>{c}（近 180 天在这类发过单或报过名）</option>)}
          </select>
        )}
        {cat && cats.length > 1 && (
          <span aria-label="也发给类目" className="muted">也发给：
            {cats.filter((c) => c !== cat).map((c) => (
              <label key={c}><input type="checkbox" checked={extraCats.includes(c)} onChange={(e) => {
                setExtraCats(e.target.checked ? [...extraCats, c] : extraCats.filter((x) => x !== c)); draftChanged();
              }} /> {c}</label>
            ))}
          </span>
        )}
        <label className="muted">定时（北京时间，可不填）
          <input aria-label="定时发送" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </label>
        <button className="ghost" disabled={title.trim().length < 2} onClick={() => void run(async () => {
          setPreview(await client.previewAnnouncement(title.trim(), body, verifiedOnly, { city: city.trim(), audience: aud, category: cat, categories: cat ? extraCats : [] }));
        })}>预览</button>
        <button disabled={title.trim().length < 2} onClick={() => void publish()}>发布</button>
      </div>
      {when && <p className="muted">已填定时：按「发布」后先排队，到时间才发出，发出前可以取消。</p>}
      {preview && (
        <div data-testid="ann-preview" style={{ marginTop: 8 }}>
          <p>将送给 <strong>{preview.audience}</strong> 人（{preview.verified_only ? '仅已实名用户' : '全体用户'}{preview.city ? ` · ${preview.city}` : ''}{preview.audience_kind && preview.audience_kind !== 'all' ? ` · ${AUD_LABEL[preview.audience_kind]}` : ''}{preview.categories?.length ? ` · 类目「${preview.categories.join('、')}」` : preview.category ? ` · 类目「${preview.category}」` : ''}），用户会看到：</p>
          <div className="task-item"><div><strong>{preview.title}</strong><p className="muted">{preview.body || '（没有正文）'}</p></div></div>
          {preview.warnings.map((w) => <p key={w} className="error">留意：{w}</p>)}
          <p className="muted">没问题就按上面的「发布」。</p>
        </div>
      )}
      {notice && <p className="muted" data-testid="ann-result">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {history.length > 0 && (
        <table style={{ marginTop: 8 }} aria-label="发过的公告">
          <thead><tr><th>标题</th><th>状态</th><th>时间</th><th>送达</th><th>已读</th><th></th></tr></thead>
          <tbody>
            {history.map((a) => (
              <tr key={a.id}>
                <td>{a.title}{a.verified_only ? '（仅已实名）' : ''}{a.city ? `（${a.city}）` : ''}{a.audience && a.audience !== 'all' ? `（${AUD_LABEL[a.audience]}）` : ''}{a.categories?.length ? `（类目「${a.categories.join('、')}」）` : a.category ? `（类目「${a.category}」）` : ''}</td>
                <td>{ANN_STATUS[a.status] ?? a.status}{a.close_reason ? `：${a.close_reason}` : ''}</td>
                <td>{formatDateTime(a.sent_at ?? a.scheduled_at ?? a.created_at)}</td>
                <td>{a.status === 'scheduled' ? '—' : a.delivered}</td>
                {/* NTF-067（159 号 spec）阅读率 */}
                <td>{typeof a.read_rate === 'number' ? `${a.read} 人（${Math.round(a.read_rate * 100)}%）` : '—'}
                  {/* NTF-071（252 号 spec）多类目的公告按类目拆开看 */}
                  {(a.categories?.length ?? 0) > 1 && a.status !== 'scheduled' && <CategoryReads id={a.id} />}
                  {/* NTF-072（261 号 spec）发出后多久点开 */}
                  {a.status === 'sent' && <ReadCurve id={a.id} />}</td>
                <td>
                  {a.status === 'scheduled' && <button className="ghost" onClick={() => void run(async () => {
                    await client.cancelAnnouncement(a.id, prompt('取消的原因（可不填）：') ?? '');
                    setNotice('已取消，这条不会发出'); await loadHistory();
                  })}>取消</button>}
                  {a.status === 'sent' && <button className="ghost" onClick={() => void run(async () => {
                    const reason = prompt('撤回的理由（用户会看到这句话）：') ?? '';
                    if (!reason.trim()) return;
                    const r = await client.revokeAnnouncement(a.id, reason);
                    setNotice(`已撤回：${r.notifications_updated} 条通知改成「已撤回」并显示理由。已经推到手机上的推送收不回来，需要的话再发一条更正。`);
                    await loadHistory();
                  })}>撤回</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** NTF-071（252 号 spec）每个类目收到几人、点开几人；点开才加载 */
function ReadCurve({ id }: { id: number }) {
  const { client } = useApp();
  const [v, setV] = useState<AnnouncementReadCurve | null>(null);
  const [error, setError] = useState('');
  if (!v) {
    return <>{error && <span className="error">{error}</span>}<button className="text-link" onClick={() => void client.announcementReadCurve(id)
      .then(setV, (e) => setError(apiErrorText(e)))}>看曲线</button></>;
  }
  const points = Array.isArray(v.points) ? v.points : [];
  return (
    <div data-testid={`read-curve-${id}`} className="muted">
      {points.map((p) => (
        <div key={p.hours}>{p.label}内：{p.read} 人{typeof p.read_rate === 'number' ? `（${Math.round(p.read_rate * 100)}%）` : ''}{p.reached ? '' : '（还没到，数字是到现在为止的）'}</div>
      ))}
      {v.note && <div>{v.note}</div>}
    </div>
  );
}

function CategoryReads({ id }: { id: number }) {
  const { client } = useApp();
  const [v, setV] = useState<AnnouncementReadByCategory | null>(null);
  const [error, setError] = useState('');
  if (!v) {
    return <>{error && <span className="error">{error}</span>}<button className="text-link" onClick={() => void client.announcementReadByCategory(id)
      .then(setV, (e) => setError(apiErrorText(e)))}>分类目</button></>;
  }
  const rows = Array.isArray(v.categories) ? v.categories : [];
  return (
    <div data-testid={`cat-reads-${id}`} className="muted">
      {rows.map((r) => <div key={r.category}>{r.category}：{r.read}/{r.delivered} 人{typeof r.read_rate === 'number' ? `（${Math.round(r.read_rate * 100)}%）` : ''}</div>)}
      {v.overlap > 0 && <div>{v.overlap} 人同时属于几个类目，各类都算了一次</div>}
    </div>
  );
}

const AUD_LABEL: Record<string, string> = { all: '全体用户', publishers: '近 180 天发过单的人', workers: '近 180 天报过名接单的人' };
const ANN_STATUS: Record<string, string> = { scheduled: '等待定时发出', sent: '已发出', cancelled: '已取消', revoked: '已撤回' };

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
  const [totals, setTotals] = useState<{ pending: number | null; awaiting: number | null }>({ pending: null, awaiting: null });
  const [minYuan, setMinYuan] = useState('');
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [largest, setLargest] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    // PAY-042 两个队列都要看得到：只看 pending 的话，**等二次确认的那些
    // 会从界面上消失**——而那正是钱冻着等人的状态。
    // PAY-043 筛选（143 号 spec）：金额下限、只看命中风控的、先看最大的；队列总长在服务端算
    // 没设筛选时发出去的请求与原来一字不差（只有 status）
    const f = { min_amount_cents: minYuan ? Math.round(Number(minYuan) * 100) : undefined, flagged_only: flaggedOnly,
      sort: largest ? 'largest' as const : undefined };
    const empty = { items: [] as WithdrawRequestRow[], total: null };
    const [pending, awaiting] = await Promise.all([
      client.withdrawRequestsPage({ status: 'pending', ...f }).catch(() => empty),
      client.withdrawRequestsPage({ status: 'awaiting_second', ...f }).catch(() => empty),
    ]);
    setRows([...awaiting.items, ...pending.items]);
    setTotals({ pending: pending.total, awaiting: awaiting.total });
  }, [client, minYuan, flaggedOnly, largest]);
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
      <div className="row" aria-label="提现复核筛选">
        <input style={{ width: 120 }} aria-label="金额下限" type="number" min={0} placeholder="金额下限（元）" value={minYuan} onChange={(e) => setMinYuan(e.target.value)} />
        <label className="row"><input type="checkbox" style={{ width: 'auto' }} checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />只看命中风控的</label>
        <label className="row"><input type="checkbox" style={{ width: 'auto' }} checked={largest} onChange={(e) => setLargest(e.target.checked)} />先看金额大的</label>
      </div>
      {(totals.pending !== null || totals.awaiting !== null) && (
        <p className="muted" data-testid="wd-totals">符合条件的：待初审 {totals.pending ?? '—'} 笔，待二次确认 {totals.awaiting ?? '—'} 笔
          {(totals.pending ?? 0) + (totals.awaiting ?? 0) > rows.length ? `（这里先显示 ${rows.length} 笔，缩小条件看其余的）` : ''}</p>
      )}
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
              {r.status === 'awaiting_second' && (
                <p className="muted" data-testid={`wd-first-${r.id}`}>
                  已由管理员 #{r.first_approved_by} 初次复核，等待第二人确认（钱仍在冻结中）
                  {/* SEC-061f / PAY-042c（155 号 spec） */}
                  {r.needs_super_second && <span className="badge" data-testid={`withdraw-super-${r.id}`}>金额较大：第二人须是超级管理员</span>}
                </p>
              )}
              {/* 命中依据带具体数值：只写「疑似拆分」，复核的人无从判断 */}
              {r.flags.length > 0 && (
                <p className="error" data-testid={`wd-flags-${r.id}`}>
                  命中 {r.flags.length} 条：{r.flags.map((f) => `${f.pattern}（${f.detail}）`).join('；')}
                </p>
              )}
            </div>
            <span className="row">
              {/* PAY-042 大额出款要两个人先后确认。按钮文案跟着状态变——
                  第二个人必须知道自己是在「确认别人的意见」，而不是在初审 */}
              <button disabled={busy} onClick={() => decide(r.id, true)}>
                {r.status === 'awaiting_second' ? '二次确认并打款' : '批准打款'}
              </button>
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

/** TEAM-031 团队企业信息核验（76 号 spec）。
 *
 * 探针：团队提交营业执照后状态是 `pending`，而**全仓没有任何端点**
 * 能把它改成 `verified`——唯一那么写的地方是一条直接写库的测试。
 * 于是没有团队能开票，也没有人能核过任何一个团队。
 */
function TeamVerifyQueue() {
  const { client } = useApp();
  const [rows, setRows] = useState<PendingTeamRow[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.pendingTeams().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function decide(teamId: number, approve: boolean) {
    setError('');
    try {
      // 驳回理由是强制的，而且会被送到 owner 面前：
      // 收不到理由，他只会把同一份材料再提交一遍
      const reason = approve ? '' : (prompt('驳回理由（会发给团队负责人）：') ?? '');
      if (!approve && !reason.trim()) return;
      await client.verifyTeam(teamId, approve, reason);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  if (rows.length === 0) return null;
  return (
    <div className="card">
      <h3>团队企业信息待核验（{rows.length}）</h3>
      {error && <p className="error">{error}</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((t) => (
          <div className="task-item" key={t.team_id} data-testid={`team-verify-${t.team_id}`}>
            <div>
              <strong>{t.company_name || t.name}</strong> · 税号 {t.tax_number || '未填'}
              <p className="muted">
                团队「{t.name}」 · 负责人 {t.owner_nickname}#{t.owner_id}
                {' · '}
                {/* 执照影像走鉴权端点，不是匿名能力 URL */}
                {t.license_urls.map((u, i) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer">执照{i + 1} </a>
                ))}
              </p>
            </div>
            <span className="row">
              <button onClick={() => decide(t.team_id, true)}>核验通过</button>
              <button className="danger" onClick={() => decide(t.team_id, false)}>驳回</button>
            </span>
          </div>
        ))}
      </div>
      <p className="muted">核验通过后该团队才能开具发票（未核验抬头的发票是税务风险，不是便利）。</p>
    </div>
  );
}

/** CERT-030 受限类目资质核验。V76 把「自己填」改成了「核过才算」，
 *  而核的那个人此前没有界面——于是受限类目的单谁都接不了。 */
function CertificationQueue() {
  const { client } = useApp();
  const [rows, setRows] = useState<PendingCertificationRow[]>([]);
  const [approved, setApproved] = useState<PendingCertificationRow[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.pendingCertifications().catch(() => []));
    setApproved(await client.adminCertifications('approved').catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function decide(id: number, approve: boolean) {
    setError('');
    try {
      const reason = approve ? '' : (prompt('驳回理由（会发给申请人）：') ?? '');
      if (!approve && !reason.trim()) return;
      await client.decideCertification(id, approve, reason);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  async function revoke(id: number) {
    setError('');
    try {
      // 撤销的理由同样会发给持证人：他要知道自己为什么不能再接这类单
      const reason = prompt('撤销理由（会发给持证人）：') ?? '';
      if (!reason.trim()) return;
      await client.revokeCertification(id, reason);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  if (rows.length === 0 && approved.length === 0) return null;
  return (
    <div className="card">
      <h3>受限类目资质待核验（{rows.length}）</h3>
      {error && <p className="error">{error}</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((r) => (
          <div className="task-item" key={r.id} data-testid={`cert-${r.id}`}>
            <div>
              <strong>{r.name}</strong> · 证号 {r.cert_number} · 发证 {r.issuer || '未填'}
              <p className="muted">
                持证人 {r.holder_name} / 实名 {r.real_name}{' '}
                {/* 姓名是否一致由服务端算好，客户端不重算 */}
                {r.name_matches
                  ? <span className="badge ok">姓名一致</span>
                  : <span className="badge bad">姓名不一致</span>}
                {r.expires_at && ` · 有效期至 ${formatDateTime(r.expires_at)}`}
                {' · '}
                {r.image_urls.map((u, i) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer">证件{i + 1} </a>
                ))}
              </p>
            </div>
            <span className="row">
              <button onClick={() => decide(r.id, true)}>通过</button>
              <button className="danger" onClick={() => decide(r.id, false)}>驳回</button>
            </span>
          </div>
        ))}
      </div>
      {approved.length > 0 && (
        <>
          <h4 style={{ marginTop: 12 }}>已核准（{approved.length}）</h4>
          <div className="list">
            {approved.map((r) => (
              <div className="task-item" key={r.id} data-testid={`cert-approved-${r.id}`}>
                <div>
                  <strong>{r.name}</strong> · {r.holder_name} · 证号 {r.cert_number}
                  <p className="muted">
                    {r.expires_at ? `有效期至 ${formatDateTime(r.expires_at)}` : '未填有效期'}
                  </p>
                </div>
                {/* 证件过期、造假或被投诉复核不通过时撤销——
                    撤不下来，持证人会继续接受限类目的单 */}
                <button className="danger" onClick={() => revoke(r.id)}>撤销</button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** UMOD-030 机审拿不准的图片。V62 把「这张图是谁传的」落了库，
 *  理由是「归属落库后处置才成为可能」——处置的界面就是这里。 */
function UploadQueue() {
  const { client } = useApp();
  const [rows, setRows] = useState<PendingUploadRow[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.pendingUploads().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function resolve(name: string, action: 'pass' | 'reject') {
    setError('');
    try {
      const reason = action === 'reject' ? (prompt('移除原因（会记入审计）：') ?? '') : '';
      await client.resolveUpload(name, action, reason);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  if (rows.length === 0) return null;
  return (
    <div className="card">
      <h3>图片待人审（{rows.length}）</h3>
      {error && <p className="error">{error}</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((r) => (
          <div className="task-item" key={r.name} data-testid={`upload-${r.name}`}>
            <div>
              <strong>{r.name}</strong> · 上传者 #{r.owner_id}
              <p className="muted">
                机审标签：{r.labels.length ? r.labels.join('、') : '无'} · {r.content_type}
              </p>
            </div>
            <span className="row">
              <button className="ghost" onClick={() => resolve(r.name, 'pass')}>通过</button>
              <button className="danger" onClick={() => resolve(r.name, 'reject')}>移除</button>
            </span>
          </div>
        ))}
      </div>
      <p className="muted">移除会物理删除文件并通知上传者——悄悄删掉、让页面变成裂图是最差的处理。</p>
    </div>
  );
}

/** ESCA-066（248 号 spec）主管看全体客服：负责哪几类、自动分配、暂停到几点、手上几张；可替人恢复接单。点开才加载 */
function SupportAgentBoard() {
  const { client } = useApp();
  const [rows, setRows] = useState<SupportAgentStatus[] | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  async function load() {
    setError('');
    try { setRows(await client.supportAgents()); } catch (e) { setError(apiErrorText(e)); }
  }
  if (rows === null) return <>{error && <p className="error">{error}</p>}<button className="ghost" onClick={() => void load()}>看客服状态</button></>;
  return (
    <div aria-label="客服状态">
      <table>
        <thead><tr><th>客服</th><th>负责</th><th>自动分配</th><th>状态</th><th>手上未结</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.user_id} data-testid={`agent-${r.user_id}`}>
              <td>{r.nickname || `#${r.user_id}`}</td>
              <td>{r.declared ? r.categories.join('、') : '都管（没选）'}</td>
              <td>{r.auto_assign ? '开' : '关'}</td>
              <td>{r.paused_until ? `暂停到 ${formatDateTime(r.paused_until)}`
                // ESCA-068（260 号 spec）没暂停但不在排班里；老服务端没有 on_duty 时照旧算在岗
                : r.on_duty === false ? '不在排班里' : '在岗'}
                {!!r.schedule?.length && <span className="muted"> · 排班 {scheduleText(r.schedule)}</span>}</td>
              <td>{r.open_tickets}</td>
              <td>{!r.paused_until && <button className="ghost" onClick={async () => {
                const hours = Number(window.prompt(`给 ${r.nickname || `#${r.user_id}`} 暂停接单几小时？（1~720）`, '8') ?? '');
                if (!hours) return;
                setError(''); setNotice('');
                try { await client.pauseSupportAgent(r.user_id, hours); setNotice(`已为 ${r.nickname || `#${r.user_id}`} 暂停接单 ${hours} 小时，已通知他`); await load(); }
                catch (e) { setError(apiErrorText(e)); }
              }}>替他暂停</button>}
                {r.paused_until && <button className="ghost" onClick={async () => {
                setError(''); setNotice('');
                try { await client.resumeSupportAgent(r.user_id); setNotice(`已恢复 ${r.nickname || `#${r.user_id}`} 的接单，已通知他`); await load(); }
                catch (e) { setError(apiErrorText(e)); }
              }}>替他恢复</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
function scheduleText(w: SupportScheduleWindow[]) {
  return w.map((x) => `${WEEKDAYS[x.weekday] ?? x.weekday} ${x.start}–${x.end}`).join('、');
}

/** ESCA-068（260 号 spec）我的排班：勾选周几、填几点到几点（北京时间）；排班以外自动不接新单，到点自动接。点开才编辑 */
function SupportScheduleEditor({ scope, onSaved }: { scope: SupportScope; onSaved: (s: SupportScope) => void }) {
  const { client } = useApp();
  const [editing, setEditing] = useState(false);
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [start, setStart] = useState('09:00');
  const [end, setEnd] = useState('18:00');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  async function save(windows: SupportScheduleWindow[]) {
    setError(''); setNote('');
    try {
      const r = await client.setMySupportSchedule(windows);
      const { schedule: _s, on_duty: _o, ...rest } = scope;
      onSaved(r.schedule.length ? { ...rest, schedule: r.schedule, on_duty: r.on_duty } : rest);
      setEditing(false);
      setNote(r.schedule.length
        ? `已保存排班：排班以外新工单不自动分给你、超时提醒先叫别人，到点自动恢复。现在${r.on_duty ? '在排班里' : '不在排班里'}`
        : '已取消排班：一直算在岗（暂停接单照常可用）');
    } catch (e) { setError(apiErrorText(e)); }
  }
  const has = !!scope.schedule?.length;
  return (
    <span aria-label="我的排班">
      {has
        ? <span data-testid="my-schedule">排班（北京时间）：{scheduleText(scope.schedule ?? [])} · {scope.on_duty ? '现在在排班里' : '现在不在排班里（新工单不自动分给你）'}</span>
        : <span className="muted">没设排班（一直算在岗）</span>}
      {' '}<button className="ghost" onClick={() => setEditing(!editing)}>{editing ? '收起' : has ? '改排班' : '设排班'}</button>
      {has && !editing && <button className="ghost" onClick={() => void save([])}>取消排班</button>}
      {editing && (
        <span>
          {WEEKDAYS.map((d, i) => (
            <label key={d}><input type="checkbox" checked={days.includes(i)}
              onChange={(e) => setDays(e.target.checked ? [...days, i].sort() : days.filter((x) => x !== i))} /> {d}</label>
          ))}
          <input aria-label="上班时间" value={start} onChange={(e) => setStart(e.target.value)} style={{ width: 64 }} />
          –<input aria-label="下班时间" value={end} onChange={(e) => setEnd(e.target.value)} style={{ width: 64 }} />
          <button className="ghost" disabled={days.length === 0}
            onClick={() => void save(days.map((weekday) => ({ weekday, start: start.trim(), end: end.trim() })))}>保存排班</button>
          <span className="muted">时间写 09:00 这样的格式；跨午夜请分两天各写一段（如 22:00–24:00 与 00:00–06:00）</span>
        </span>
      )}
      {note && <span role="status">{note}</span>}
      {error && <span className="error">{error}</span>}
    </span>
  );
}

/** CS-030 工单队列。SUPPORT_SLA_HOURS 定了多久要回，而回的那个人此前没有界面。 */
function TicketQueue() {
  const { client, me } = useApp();
  const [rows, setRows] = useState<AdminTicketRow[]>([]);
  // ESCA-054（157 号 spec）主管（超级管理员，含未分级）可以把工单指派给某位客服
  const isSuper = !!me && (!(me.admin_roles?.length) || me.admin_roles.includes('super'));
  const [agents, setAgents] = useState<AdminRow[]>([]);
  useEffect(() => {
    if (!isSuper) return;
    void client.listAdmins().then((r) => setAgents((r.admins ?? []).filter((a) => a.unclassified || a.roles.includes('support') || a.roles.includes('super'))))
      .catch(() => setAgents([]));
  }, [client, isSuper]);
  const [error, setError] = useState('');
  // PAY-045 分页：此前上限写死、offset 被忽略，队列一长后面的就在界面上不存在
  const PAGE = 20;
  const [more, setMore] = useState(false);
  // ESCA-051 筛选（150 号 spec）：只看已升级的、只看我接手的、最急的在前
  const [view, setView] = useState<{ escalated_only: boolean; mine: boolean; sort: 'id' | 'urgent'; my_categories?: boolean }>(
    { escalated_only: false, mine: false, sort: 'urgent' });
  // ESCA-061（234 号 spec）我负责的类别：没人接手的工单超时提醒优先叫负责这一类的人
  const [scope, setScope] = useState<SupportScope | null>(null);
  const [scopeDraft, setScopeDraft] = useState<TicketCategory[]>([]);
  const [scopeNote, setScopeNote] = useState('');
  const [autoAssign, setAutoAssign] = useState(false);
  useEffect(() => {
    // 老服务端没有这个接口时不显示这一块（形状不对也当没有）
    client.mySupportCategories().then((r) => {
      if (r && Array.isArray(r.categories) && r.labels) { setScope(r); setScopeDraft(r.categories); setAutoAssign(!!r.auto_assign); } else setScope(null);
    }).catch(() => setScope(null));
  }, [client]);
  // ESCA-065（240 号 spec）暂停接单：下班 / 请假时不自动分给我，到点自动恢复
  const [pauseHours, setPauseHours] = useState(8);
  async function pause() {
    const hours = pauseHours;
    setError(''); setScopeNote('');
    try {
      const r = await client.pauseMySupport(hours);
      if (scope) setScope({ ...scope, paused_until: r.paused_until ?? undefined });
      setScopeNote(`已暂停接单到 ${formatDateTime(r.paused_until ?? '')}：这段时间新工单不自动分给你，超时提醒先叫别人；到点自动恢复。手上已接的工单不动`);
    } catch (err) { setError(apiErrorText(err)); }
  }
  async function resume() {
    setError(''); setScopeNote('');
    try {
      await client.resumeMySupport();
      if (scope) { const { paused_until: _, ...rest } = scope; setScope(rest); }
      setScopeNote('已恢复接单');
    } catch (err) { setError(apiErrorText(err)); }
  }
  async function saveScope() {
    setError(''); setScopeNote('');
    try {
      const r = await client.setMySupportCategories(scopeDraft, autoAssign);
      setScope(r); setScopeNote('已保存：没人接手的工单超时，会优先提醒负责这一类的客服'
        + (r.auto_assign ? '；这几类的新工单会自动分给你（手上未结的最少的人先分）' : ''));
    } catch (err) { setError(apiErrorText(err)); }
  }

  const load = useCallback(async (limit = PAGE) => {
    // CI-002：响应不是数组时当作空表（此前 r.slice 在异步里抛错，没人接住）
    const r = asList<AdminTicketRow>(await client.adminTickets('open', limit + 1, 0, view).catch(() => []));
    // 多取一条来判断「还有没有」——这样「加载更多」不会在最后一页还挂着
    setMore(r.length > limit);
    setRows(r.slice(0, limit));
  }, [client, view]);
  useEffect(() => { void load(); }, [load]);

  async function claim(id: number) {
    setError('');
    try { await client.claimTicket(id); await load(); } catch (err) { setError(apiErrorText(err)); }
  }
  // ESCA-053 先回一句、不结单（157 号 spec）
  async function replyOnly(id: number) {
    setError('');
    try {
      const text = prompt('先回一句（不结单，会作为站内信发给提单人）：') ?? '';
      if (!text.trim()) return;
      await client.replyTicket(id, text);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }
  async function assign(id: number, assigneeId: number) {
    setError('');
    try { await client.assignTicket(id, assigneeId); await load(); } catch (err) { setError(apiErrorText(err)); }
  }

  async function reply(id: number) {
    setError('');
    try {
      const text = prompt('回复内容（会作为站内信发给提单人）：') ?? '';
      if (!text.trim()) return;
      await client.resolveTicket(id, text);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  // ESCA-058（221 号 spec）完整往来：列表只给最近一条补充，接手的人要先看懂前面说过什么
  const [detail, setDetail] = useState<AdminTicketDetail | null>(null);
  // ESCA-062（231 号 spec）在完整往来里回复、可附图（截图教用户点哪里）
  const [threadReply, setThreadReply] = useState('');
  const [threadImages, setThreadImages] = useState<string[]>([]);
  async function sendThreadReply(id: number) {
    setError('');
    try {
      await client.replyTicket(id, threadReply.trim(), threadImages);
      setThreadReply(''); setThreadImages([]);
      setDetail(await client.adminTicketDetail(id));
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }
  async function openThread(id: number) {
    setError('');
    if (detail?.id === id) { setDetail(null); return; }
    try { setDetail(await client.adminTicketDetail(id)); } catch (err) { setError(apiErrorText(err)); }
  }

  const filtered = view.escalated_only || view.mine;
  if (rows.length === 0 && !filtered) return null;
  return (
    <div className="card" aria-label="待处理工单">
      <h3>待处理工单（{rows.length}）</h3>
      <div className="row" style={{ flexWrap: 'wrap', gap: 12 }}>
        <label><input type="checkbox" checked={view.escalated_only} onChange={(e) => setView({ ...view, escalated_only: e.target.checked })} /> 只看已升级的</label>
        <label><input type="checkbox" checked={view.mine} onChange={(e) => setView({ ...view, mine: e.target.checked })} /> 只看我接手的</label>
        <label><input type="checkbox" checked={view.sort === 'urgent'} onChange={(e) => setView({ ...view, sort: e.target.checked ? 'urgent' : 'id' })} /> 最急的在前</label>
        {scope?.declared && <label><input type="checkbox" checked={!!view.my_categories} onChange={(e) => setView({ ...view, my_categories: e.target.checked })} /> 只看我负责的类别</label>}
      </div>
      {scope && (
        <div className="row" style={{ flexWrap: 'wrap', gap: 12 }} aria-label="我负责的类别">
          <span className="muted">我负责：{scope.declared ? '' : '（还没选，视为都管）'}</span>
          {(['funds', 'account', 'general'] as TicketCategory[]).map((c) => (
            <label key={c}><input type="checkbox" checked={scopeDraft.includes(c)}
              onChange={(e) => setScopeDraft(e.target.checked ? [...scopeDraft, c] : scopeDraft.filter((x) => x !== c))} /> {scope.labels[c] ?? c}</label>
          ))}
          {/* ESCA-064（237 号 spec）新工单按类别自动分，手上未结的最少的人先分 */}
          <label><input type="checkbox" checked={autoAssign} onChange={(e) => setAutoAssign(e.target.checked)} /> 新工单自动分给我</label>
          <button className="ghost" onClick={() => void saveScope()}>保存</button>
          {/* ESCA-065（240 号 spec）暂停接单 */}
          {scope.paused_until
            ? <span>暂停接单到 {formatDateTime(scope.paused_until)} <button className="ghost" onClick={() => void resume()}>恢复接单</button></span>
            : <span>
                <select aria-label="暂停多久" value={pauseHours} onChange={(e) => setPauseHours(Number(e.target.value))}>
                  <option value={2}>2 小时</option><option value={8}>8 小时（下班）</option>
                  <option value={24}>1 天</option><option value={72}>3 天</option><option value={168}>7 天</option>
                </select>
                <button className="ghost" onClick={() => void pause()}>暂停接单</button>
              </span>}
          {scopeNote && <span role="status">{scopeNote}</span>}
          <SupportScheduleEditor scope={scope} onSaved={(x) => { setScope(x); setScopeNote(''); }} />
        </div>
      )}
      {isSuper && <SupportAgentBoard />}
      {error && <p className="error">{error}</p>}
      {rows.length === 0 && <p className="muted">没有符合条件的工单。</p>}
      <div className="list" style={{ marginTop: 8 }}>
        {rows.map((t) => (
          <div className="task-item" key={t.id} data-testid={`ticket-${t.id}`}>
            <div>
              <strong>{t.subject}</strong> · 用户 #{t.user_id}
              {t.escalation_level > 0 && <span className="badge" data-testid={`ticket-level-${t.id}`}> {t.escalation_label}</span>}
              {t.priority === 'urgent' && <span className="badge warn" data-testid={`ticket-priority-${t.id}`}> 加急</span>}
              <p className="muted">{t.body} · {formatDateTime(t.created_at)}</p>
              <p className="muted" data-testid={`ticket-sla-${t.id}`}>
                已等 {t.waited_hours} 小时（承诺 {t.sla_hours} 小时{t.overdue_hours > 0 ? `，已超 ${t.overdue_hours} 小时` : ''}）
                · {t.assignee_id ? `接手人：${t.assignee_nickname || `#${t.assignee_id}`}` : '还没人接手'}
                {/* ESCA-053（157 号 spec）首次响应 */}
                {` · ${t.first_responded ? `已回复 ${t.replies_count} 次` : `还没回过（首次响应时限 ${t.first_response_hours} 小时）`}`}
                {t.awaiting_staff && <span className="badge warn"> 提单人补充了，等你回</span>}
                {t.last_user_reply && <span className="muted" style={{ display: 'block' }} data-testid={`ticket-user-reply-${t.id}`}>提单人补充（{t.last_user_reply_at ? formatDateTime(t.last_user_reply_at) : ''}）：{t.last_user_reply}</span>}
              </p>
              {t.first_response_overdue && <p className="error" data-testid={`ticket-fr-${t.id}`}>首次响应已超时：先回一句告诉对方在处理</p>}
              {/* ESCA-060（229 号 spec）这位用户自选加急的可信度 */}
              {(t.requester_downgraded_90d ?? 0) > 0 && (
                <p className="muted" data-testid={`ticket-urgent-record-${t.id}`}>提单人近 90 天自选加急 {t.requester_urgent_90d} 张，被改回一般 {t.requester_downgraded_90d} 张</p>
              )}
              {detail?.id === t.id && (
                <div data-testid={`ticket-thread-${t.id}`} style={{ marginTop: 6 }}>
                  <p className="muted">提单人：{detail.user_nickname || `#${detail.user_id}`} · {formatDateTime(detail.created_at)}</p>
                  <p>{detail.body || '（没写详细内容）'}</p>
                  <TicketImages urls={detail.images} label={`admin-ticket-images-${t.id}`} />
                  {detail.thread.length === 0 && <p className="muted">还没有往来。</p>}
                  <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    <input className="grow" aria-label={`回复工单 ${t.id}`} placeholder="回复（不结单），可附图" value={threadReply}
                           onChange={(e) => setThreadReply(e.target.value)} />
                    <PhotoPicker urls={threadImages} onChange={setThreadImages} max={4} />
                    <button className="ghost" disabled={!threadReply.trim()} onClick={() => void sendThreadReply(t.id)}>发送回复</button>
                  </div>
                  {detail.thread.map((m, i) => (
                    <p key={i} className={m.is_staff ? '' : 'muted'}>
                      <strong>{m.is_staff ? `客服 ${m.author}` : m.author}</strong>（{formatDateTime(m.created_at)}）：{m.body}
                      <TicketImages urls={m.images} label={`admin-thread-images-${t.id}-${i}`} />
                    </p>
                  ))}
                </div>
              )}
            </div>
            <button className="ghost" onClick={() => void openThread(t.id)}>{detail?.id === t.id ? '收起往来' : '看完整往来'}</button>
            <button className="ghost" onClick={() => void claim(t.id)}>{t.assignee_id ? '改由我处理' : '我来处理'}</button>
            {/* ESCA-052（172 号 spec）选错类别的改优先级，时限随之变化 */}
            <button className="ghost" onClick={() => {
              const next = t.priority === 'urgent' ? 'normal' : 'urgent';
              const reason = window.prompt(next === 'urgent' ? '改成加急的理由（例如：其实是钱没到账）' : '改回一般的理由');
              if (reason && reason.trim().length >= 2) void client.setTicketPriority(t.id, next, reason.trim()).then(() => load()).catch((e) => setError(apiErrorText(e)));
            }}>{t.priority === 'urgent' ? '改回一般' : '改成加急'}</button>
            <button className="ghost" onClick={() => void replyOnly(t.id)}>先回一句</button>
            {isSuper && agents.length > 0 && (
              <select aria-label={`指派工单 ${t.id}`} value="" onChange={(e) => { if (e.target.value) void assign(t.id, Number(e.target.value)); }}>
                <option value="">指派给…</option>
                {agents.map((a) => <option key={a.user_id} value={a.user_id}>{a.nickname || `#${a.user_id}`}</option>)}
              </select>
            )}
            <button onClick={() => reply(t.id)}>回复并结单</button>
          </div>
        ))}
      </div>
      {/* 只在**真的还有**的时候出现：一个永远挂着的「加载更多」等于没有信息 */}
      {more && (
        <button className="ghost" data-testid="tickets-more"
                onClick={() => void load(rows.length + PAGE)}>加载更多</button>
      )}
    </div>
  );
}

/** SECEV-030 安全看板与 IP 解封。误封一个公司的出口 IP，
 *  整栋楼的人都进不来——那条补救路径 V56 就建好了，入口在这里。 */
function SecurityBoard() {
  const { client } = useApp();
  const [board, setBoard] = useState<SecurityBoardView | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const b = await client.adminSecurity().catch(() => null);
    // 一个 section 的载荷不对，不该把整个后台页面白屏掉：
    // `.catch()` 只挡住了请求失败，挡不住「返回了别的形状」。
    setBoard(b && Array.isArray(b.banned) && Array.isArray(b.watching) ? b : null);
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function unban(ip: string) {
    setError('');
    try {
      await client.unbanIp(ip);
      await load();
    } catch (err) { setError(apiErrorText(err)); }
  }

  if (!board) return null;
  return (
    <div className="card">
      <h3>安全看板</h3>
      {error && <p className="error">{error}</p>}
      <div className="row" style={{ gap: 28, marginTop: 10, flexWrap: 'wrap' }}>
        <Stat label="当前封禁 IP" value={String(board.banned.length)} />
        <Stat label="观察名单" value={String(board.watching.length)} />
        <Stat label="窗口内触发人机验证" value={String(board.captcha_required_in_window)} />
        {/* 阈值来自服务端配置，不在界面上写死 */}
        <Stat label="封禁阈值 / 时长" value={`${board.threshold} 次 / ${board.ban_seconds}s`} />
      </div>
      {board.banned.length > 0 && (
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>IP</th><th>剩余</th><th>原因</th><th></th></tr></thead>
          <tbody>
            {board.banned.map((b) => (
              <tr key={b.ip}>
                <td>{b.ip}</td><td>{b.seconds_left}s</td><td>{b.reason}</td>
                <td>
                  <button className="ghost" style={{ padding: '2px 8px' }}
                          onClick={() => unban(b.ip)}>解封</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** GEO-030 城市与类目开通。线下任务只能发在已开通城市——
 *  没有这个界面，开城只能改库。 */
function CityAndCategory() {
  const { client } = useApp();
  const [cities, setCities] = useState<Array<{ id: number; name: string }>>([]);
  const [cats, setCats] = useState<Array<{ id: number; name: string; required_cert: string }>>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setCities(await client.cities().catch(() => []));
    setCats(await client.categories().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); } catch (err) { setError(apiErrorText(err)); }
  }

  return (
    <div className="card">
      <h3>城市与类目</h3>
      {error && <p className="error">{error}</p>}
      <div className="row" style={{ marginTop: 8, flexWrap: 'wrap' }}>
        <button className="ghost" onClick={() => {
          const name = prompt('新开通城市名：') ?? '';
          if (name.trim()) void act(() => client.createCity(name.trim()));
        }}>开通城市</button>
        <button className="ghost" onClick={() => {
          const name = prompt('新类目名：') ?? '';
          if (!name.trim()) return;
          const cert = prompt('需要的资质（留空表示不限）：') ?? '';
          void act(() => client.createCategory(name.trim(), cert.trim()));
        }}>新增类目</button>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>
        已开通城市（{cities.length}）：{cities.map((c) => c.name).join('、') || '无'}
      </p>
      <table style={{ marginTop: 8 }}>
        <thead><tr><th>类目</th><th>需要资质</th><th></th></tr></thead>
        <tbody>
          {cats.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td>{c.required_cert || '不限'}</td>
              <td>
                <button className="ghost" style={{ padding: '2px 8px' }}
                        onClick={() => void act(() => client.updateCategory(c.id, { active: false }))}>停用</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** QUEUE-011 人审队列概览（78 号 spec）。
 *
 * 排在首屏最前面：运营不该靠往下滚才发现有东西积压。
 * 超过 SLA 的行标红——SLA 此前只是配置里的一个数字，没有任何地方用它。
 */
function QueueOverview() {
  const { client } = useApp();
  const [view, setView] = useState<ReviewQueuesView | null>(null);

  useEffect(() => {
    void client.reviewQueues()
      .then((v) => setView(v && Array.isArray(v.queues) ? v : null))
      .catch(() => setView(null));
  }, [client]);

  if (!view || view.total_pending === 0) return null;
  return (
    <div className="card">
      <h3>人审队列（待处理 {view.total_pending}）</h3>
      <table style={{ marginTop: 8 }}>
        <thead><tr><th>队列</th><th>待处理</th><th>最久等待</th><th>SLA</th><th></th></tr></thead>
        <tbody>
          {view.queues.filter((q) => q.pending > 0).map((q) => (
            <tr key={q.key} data-testid={`queue-${q.key}`}>
              <td>{q.label}</td>
              <td>{q.pending}</td>
              <td>{q.oldest_wait_hours} 小时</td>
              <td className="muted">{q.sla_hours} 小时</td>
              <td>
                {q.breached
                  ? <span className="badge bad">已超 SLA</span>
                  : <span className="badge ok">在期内</span>}
                {/* 「这个队列有没有人盯」——答案可能是「有，在别处」 */}
                {q.chased_elsewhere && <span className="muted"> · 催办在别处</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const READINESS_LABELS: Record<string, string> = {
  production_environment: '生产运行模式', postgres: 'PostgreSQL 业务数据库', redis: '共享缓存与任务协调',
  jwt_secret: '登录令牌密钥', job_secret: '后台任务密钥', cors: '跨域访问限制', api_docs: '接口文档关闭', proxy_hops: '代理信任配置',
  provider_payment: '真实支付供应商', provider_sms: '真实短信供应商', provider_kyc: '真实实名核验',
  provider_moderation: '真实内容审核', provider_oauth: '可信第三方登录', custody: '资金存管通道',
  signature: '正式电子签约闭环', notary: '外部存证通道', tax_workflow: '税务与开票方案',
};
export function LaunchReadiness() {
  const { client } = useApp();
  const [data, setData] = useState<Awaited<ReturnType<typeof client.adminVendors>>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <section className="card"><h3>商用准备检查</h3>
    <p className="muted">读取服务器实际配置。通过项数量不是产品完成百分比，也不代表已获准开展真实交易。</p>
    <button disabled={busy} onClick={async () => {
      setBusy(true); setError('');
      try { setData(await client.adminVendors()); } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
    }}>{busy ? '检查中…' : '检查当前环境'}</button>
    {error && <p className="error" role="alert">{error}</p>}
    {data && <><p>当前环境：{data.commercial_readiness.environment} · 配置检查 {data.commercial_readiness.checks_passed}/{data.commercial_readiness.checks_total} 通过</p>
      <div className="list">{data.commercial_readiness.checks.filter(c => !c.passed).map(c => <div key={c.code} className="row">
        <span className="badge warn">待完成</span><strong>{READINESS_LABELS[c.code] || c.code}</strong>
        <span className="muted">{c.category === 'integration' ? '需要正式对接与验收' : c.category === 'business_decision' ? '需要业务方案确认' : '需要生产配置与验证'}</span>
      </div>)}</div>
      <h4>供应商对接情况</h4>{data.commercial_readiness.vendors.map(v => <p key={v.kind} className="muted">{READINESS_LABELS['provider_' + v.kind]}：当前 {v.configured_grade} · {v.registered_non_mock_implementations.length ? '已有非模拟适配实现，仍需真实联调验收' : '还没有正式适配实现，并非仅缺密钥'}</p>)}
      <p className="muted">此检查不覆盖供应商真实验收、主体与适法审核、域名 HTTPS、独立安全审计、恢复与压测演练、链上密钥运营及 App 上架。</p></>}
  </section>;
}
