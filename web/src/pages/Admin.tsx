// 管理后台（12.E）：指标看板 / 举报处置队列 / 用户管理
import { fmtYuan } from '@platform/core';
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
                            onClick={async () => { await client.banUser(u.id); await load(); }}>封禁</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
