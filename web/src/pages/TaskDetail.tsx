import {
  ApiError, TASK_STATUS_LABEL, fmtYuan,
  type Contract, type Recommendation, type Task, type TaskTree,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useApp } from '../store';

type AppRow = { id: number; applicant_id: number; nickname: string; credit_score: number; rating_avg: number; bid_cents: number; message: string; status: string };

export default function TaskDetail() {
  const { id } = useParams();
  const taskId = Number(id);
  const { client, me } = useApp();
  const [task, setTask] = useState<Task | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [tree, setTree] = useState<TaskTree | null>(null);
  const [progress, setProgress] = useState<Array<{ id: number; kind: string; content: string; created_at: string }>>([]);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const isCreator = me && task?.creator_id === me.id;
  const isExecutor = me && task?.executor_id === me.id;

  const load = useCallback(async () => {
    const t = await client.getTask(taskId);
    setTask(t);
    if (me && t.creator_id === me.id && t.status === 'published') {
      setApps(await client.listApplications(taskId));
      setRecs(await client.recommendations(taskId));
    }
    if (t.parent_id === null && t.task_type === 'project') {
      setTree(await client.taskTree(taskId).catch(() => null));
    }
    if (me && (t.creator_id === me.id || t.executor_id === me.id)) {
      if (!['draft', 'published'].includes(t.status)) {
        setProgress(await client.listProgress(taskId).catch(() => []));
      }
    }
  }, [client, me, taskId]);

  useEffect(() => { void load(); }, [load]);

  // matched 之后按任务查合约，刷新后仍能展示签署/托管入口
  useEffect(() => {
    if (!task || !me || ['draft', 'published'].includes(task.status)) return;
    if (task.creator_id !== me.id && task.executor_id !== me.id) return;
    client.getContractByTask(taskId).then(setContract).catch(() => setContract(null));
  }, [task, me, client, taskId]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '网络错误');
    }
  }

  if (!task) return <div className="page"><p className="muted">加载中…</p></div>;

  return (
    <div className="page">
      <div className="card">
        <div className="row">
          <h2 className="grow">{task.title}</h2>
          <span className={`badge ${task.status === 'completed' ? 'ok' : task.status === 'disputed' ? 'bad' : ''}`}>
            {TASK_STATUS_LABEL[task.status]}
          </span>
        </div>
        <p className="muted">{task.category} · {task.is_remote ? '线上' : `${task.city} ${task.address_hint}`} · 预算 <span className="price">{fmtYuan(task.budget_cents)}</span></p>
        {task.description && <p style={{ marginTop: 8 }}>{task.description}</p>}
        {task.address_exact && <p className="muted">📍 详细地址（当事人可见）：{task.address_exact}</p>}
        {error && <p className="error">{error}</p>}

        {/* 状态驱动的操作区（TASK-021） */}
        <div className="row" style={{ marginTop: 12 }}>
          {task.status === 'published' && !isCreator && (
            <button onClick={() => act(() => client.apply(taskId, '我可以做'))}>报名接单</button>
          )}
          {task.status === 'in_progress' && isExecutor && (
            <button onClick={() => act(() => client.deliver(taskId))}>提交验收</button>
          )}
          {task.status === 'pending_acceptance' && isCreator && (
            <>
              <button onClick={() => act(() => client.acceptDelivery(taskId))}>验收通过（放款）</button>
              <button className="danger" onClick={() => {
                const reason = prompt('驳回理由：');
                if (reason) void act(() => client.rejectDelivery(taskId, reason));
              }}>驳回</button>
            </>
          )}
          {['matched', 'in_progress'].includes(task.status) && (isCreator || isExecutor) && (
            <>
              <button className="danger" onClick={() => {
                if (confirm('确认取消？托管后取消将按规则计算补偿')) void act(() => client.cancelTask(taskId));
              }}>取消任务</button>
              <button className="ghost" onClick={() => {
                const reason = prompt('纠纷说明（资金将被冻结，进入协商/仲裁）：');
                if (reason) void act(() => client.openDispute(taskId, reason));
              }}>发起纠纷</button>
            </>
          )}
          {task.status === 'completed' && (isCreator || isExecutor) && (
            <button onClick={() => {
              const stars = Number(prompt('评分 1-5：', '5'));
              if (stars >= 1 && stars <= 5) void act(() => client.review(taskId, stars));
            }}>评价对方</button>
          )}
        </div>
      </div>

      {/* 母任务驾驶舱（AI-DEC-021/TASK-036） */}
      {tree && tree.children.length > 0 && (
        <div className="card">
          <h3>子任务进度 {tree.progress_pct}%</h3>
          <div className="progress-bar"><div style={{ width: `${tree.progress_pct}%` }} /></div>
          <div className="list" style={{ marginTop: 12 }}>
            {tree.children.map((c) => (
              <div className="task-item" key={c.id}>
                <Link to={`/tasks/${c.id}`}>{c.title}</Link>
                <span>
                  <span className="muted">{fmtYuan(c.budget_cents)} </span>
                  <span className={`badge ${c.status === 'completed' ? 'ok' : ''}`}>{TASK_STATUS_LABEL[c.status]}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 发布者视图：AI 推荐 + 报名列表（MATCH-001/002） */}
      {isCreator && task.status === 'published' && (
        <>
          {recs.length > 0 && (
            <div className="card">
              <h3>AI 推荐人选</h3>
              <div className="list">
                {recs.slice(0, 5).map((r) => (
                  <div className="task-item" key={r.user_id}>
                    <div>
                      <strong>{r.nickname}</strong>
                      <p className="muted">{r.reasons.join(' · ')}</p>
                    </div>
                    <span className="row">
                      <span className="badge">匹配 {(r.score * 100).toFixed(0)}%</span>
                      <button className="ghost" style={{ padding: '4px 10px' }}
                              onClick={() => act(() => client.inviteToTask(taskId, r.user_id, '诚邀接单'))}>
                        邀约
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="card">
            <h3>报名列表（{apps.length}）</h3>
            <div className="list">
              {apps.length === 0 && <p className="muted">暂无报名</p>}
              {apps.map((a) => (
                <div className="task-item" key={a.id}>
                  <div>
                    <strong>{a.nickname}</strong> <span className="muted">信用 {a.credit_score} · 评分 {a.rating_avg}</span>
                    <p className="muted">{a.message} · 报价 {fmtYuan(a.bid_cents)}</p>
                  </div>
                  {a.status === 'pending' && (
                    <button onClick={() => act(async () => {
                      const res = await client.acceptApplication(a.id);
                      setContract(await client.getContract(res.contract_id));
                    })}>选 TA</button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 合约卡片（SC-002/003） */}
      {contract && (
        <div className="card">
          <h3>智能合约 #{contract.id}</h3>
          <pre className="muted" style={{ whiteSpace: 'pre-wrap' }}>{contract.terms}</pre>
          <div className="row">
            {((isCreator && !contract.signed_by_requester) || (isExecutor && !contract.signed_by_executor)) && (
              <button onClick={() => act(async () => setContract(await client.signContract(contract.id)))}>签署合约</button>
            )}
            {isCreator && contract.status === 'signed' && (
              <button onClick={() => act(async () => setContract(await client.fundContract(contract.id)))}>
                托管资金 {fmtYuan(contract.amount_cents)}
              </button>
            )}
            <span className="badge">{contract.status}{contract.frozen ? '（冻结）' : ''} · v{contract.version}</span>
          </div>
          {/* SC-004 里程碑分期 */}
          {contract.milestones && contract.milestones.length > 1 && (
            <table style={{ marginTop: 10 }}>
              <thead><tr><th>里程碑</th><th>金额</th><th>状态</th><th></th></tr></thead>
              <tbody>
                {contract.milestones.map((m) => (
                  <tr key={m.idx}>
                    <td>{m.idx}. {m.title}</td>
                    <td>{fmtYuan(m.amount_cents)}</td>
                    <td><span className={`badge ${m.status === 'released' ? 'ok' : m.status === 'delivered' ? 'warn' : ''}`}>
                      {m.status === 'released' ? '已放款' : m.status === 'delivered' ? '待验收' : '进行中'}
                    </span></td>
                    <td>
                      {isExecutor && m.status === 'pending' && contract.status === 'funded' && (
                        <button className="ghost" style={{ padding: '2px 10px' }}
                                onClick={() => act(async () => setContract(await client.deliverMilestone(contract.id, m.idx)))}>
                          交付本期
                        </button>
                      )}
                      {isCreator && m.status === 'delivered' && (
                        <button style={{ padding: '2px 10px' }}
                                onClick={() => act(async () => setContract(await client.acceptMilestone(contract.id, m.idx)))}>
                          验收放款
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* 执行留痕（TASK-022） */}
      {(isCreator || isExecutor) && !['draft', 'published'].includes(task.status) && (
        <div className="card">
          <h3>执行动态</h3>
          <div className="list">
            {progress.map((p) => (
              <p key={p.id} className="muted">[{p.kind}] {p.content} · {new Date(p.created_at).toLocaleString()}</p>
            ))}
          </div>
          {task.status === 'in_progress' && (
            <div className="row" style={{ marginTop: 8 }}>
              <input className="grow" placeholder="进度说明…" value={note} onChange={(e) => setNote(e.target.value)} />
              <button onClick={() => act(async () => { await client.addProgress(taskId, note); setNote(''); })}>更新进度</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
