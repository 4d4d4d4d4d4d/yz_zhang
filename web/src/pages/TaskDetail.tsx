import { DEPOSIT_STATUS_LABEL, IP_ASSIGNMENT_LABEL, TASK_STATUS_LABEL, apiErrorText, fmtYuan, formatDateTime, type ChangeOrderView, type Contract, type Recommendation, type Task, type TaskTree } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AgentPanel } from '../AgentPanel';
import { DisputePanel } from '../DisputePanel';
import PhotoPicker from '../PhotoPicker';
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
  const [progress, setProgress] = useState<
    Array<{ id: number; kind: string; content: string; images?: string[]; created_at: string }>
  >([]);
  const [note, setNote] = useState('');
  const [shots, setShots] = useState<string[]>([]);
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
      setError(apiErrorText(err));
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
        {/* TASK-060/061 这两条此前服务端根本不返回：执行方看到「浮动对价」
            却看不到浮动多少，被强制选定的知识产权归属他也看不见。
            必须选 ≠ 看得见——只做前一件，公平没有兑现。 */}
        <p className="muted" data-testid="task-terms">
          {task.pricing === 'outcome' && (
            <>达标可加付至多 <span className="price">{fmtYuan(task.bonus_cents)}</span>（按验收指标判定） · </>
          )}
          交付成果归属：{task.ip_assignment
            ? IP_ASSIGNMENT_LABEL[task.ip_assignment]
            : '未声明'}
        </p>
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
            <>
              <button onClick={() => {
                const stars = Number(prompt('评分 1-5：', '5'));
                if (stars >= 1 && stars <= 5) void act(() => client.review(taskId, stars));
              }}>评价对方</button>
              {isExecutor && (
                <button className="ghost" onClick={() => {
                  const body = prompt('写一篇完成复盘（将发布为案例帖，为你带来新订单）：');
                  if (body) void act(() => client.createExperiencePost(taskId, body));
                }}>发经验帖</button>
              )}
            </>
          )}
        </div>
      </div>

      {/* CLI-063 AI 助理面板：邀请、执行、交付闸门与人工核验入口。
          V73/V74 把服务端做完了，网页上此前一个入口都没有。 */}
      {isCreator && <AgentPanel task={task} onChanged={() => void load()} />}

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
            <h3>报名列表（{apps.length}）{task.pricing === 'bidding' && <span className="badge warn">竞价比选：按报价升序</span>}</h3>
            <div className="list">
              {apps.length === 0 && <p className="muted">暂无报名</p>}
              {(task.pricing === 'bidding' ? [...apps].sort((a, b) => a.bid_cents - b.bid_cents) : apps).map((a) => (
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
          {/* SYNC-005 保证金此前在网页上**一个字都没有**：执行方接单时 wallet
              会把这笔钱从可用余额划到冻结，而合约页不提、钱包页只给一个
              「冻结中」的数字。钱不见了却没有解释，是这一批最该修的一条。 */}
          {contract.deposit_cents > 0 && (
            <p className={contract.deposit_status === 'forfeited' ? 'error' : 'muted'}>
              执行方保证金 {fmtYuan(contract.deposit_cents)} ·{' '}
              {DEPOSIT_STATUS_LABEL[contract.deposit_status] ?? contract.deposit_status}
              {contract.deposit_status === 'held' && '（完成或正常取消后退还，违约取消则罚没给发布方）'}
            </p>
          )}
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
            <button className="ghost" style={{ padding: '4px 10px' }} onClick={async () => {
              const exp = await client.exportContract(contract.id);
              const blob = new Blob([exp.text], { type: 'text/plain;charset=utf-8' });
              const a = document.createElement('a');
              a.href = URL.createObjectURL(blob);
              a.download = `contract-${contract.id}.txt`;
              a.click();
              URL.revokeObjectURL(a.href);
            }}>导出合约凭证</button>
          </div>
          {/* SC-007 变更单。任务范围一变（「加了两个房间，多给你 100」），
              改造前这件事在产品里**没有任何地方可以落地**——双方只剩
              取消（要按违约规则算补偿）或发起纠纷两条对抗路径。 */}
          {(isCreator || isExecutor) && ['signed', 'funded'].includes(contract.status)
            && !contract.frozen && (
            <ChangeOrders contractId={contract.id} amountCents={contract.amount_cents}
                          onChanged={async () => setContract(await client.getContract(contract.id))} />
          )}
          {/* SC-004 分期定义。窗口**只在双签前**：签署后服务端会回
              `milestones_locked`（改价要走变更单）。此前没有任何端能定义分期，
              于是生产环境里每一份合约都只有一期——下面那张表的渲染条件
              `length > 1` 永远不成立，是一段跑不到的代码。 */}
          {isCreator && contract.status === 'pending_signatures' && (
            <DefineMilestones contractId={contract.id} amountCents={contract.amount_cents}
                              onDefined={async () => setContract(await client.getContract(contract.id))} />
          )}
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
              <div key={p.id}>
                <p className="muted">[{p.kind}] {p.content} · {formatDateTime(p.created_at)}</p>
                {!!p.images?.length && (
                  <div className="row" style={{ gap: 6, marginTop: 4 }}>
                    {p.images.map((u) => (
                      <a key={u} href={u} target="_blank" rel="noreferrer">
                        <img src={u} alt="凭证" width={72} height={72}
                             style={{ objectFit: 'cover', borderRadius: 8 }} />
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          {task.status === 'in_progress' && (
            <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
              <div className="row">
                <input className="grow" placeholder="进度说明…" value={note} onChange={(e) => setNote(e.target.value)} />
                <button onClick={() => act(async () => {
                  await client.addProgress(taskId, note, shots);
                  setNote('');
                  setShots([]);
                })}>更新进度</button>
              </div>
              {/* MOB-021 拍照留证：纠纷时最有力的证据往往是现场照片 */}
              <PhotoPicker urls={shots} onChange={setShots} />
            </div>
          )}
        </div>
      )}
      {/* GEO-023/022 安全区块。服务端两条都早就实现了——`sos` 的注释甚至
          为了让按钮**不被合规弹窗挡住**特意去查了 PIPL 第十三条第(四)项——
          而这个按钮在任何一个端上都不存在。 */}
      {(isCreator || isExecutor) && task
        && ['in_progress', 'pending_acceptance'].includes(task.status) && !task.is_remote && (
        <SafetyPanel taskId={taskId} isExecutor={!!isExecutor} />
      )}
      {/* DSPC-021 纠纷面板。当事人（含被诉方）从这里答辩、和解、申诉——
          此前这三件事在任何客户端上都做不了，唯一能做的动作是发起纠纷 */}
      {(isCreator || isExecutor) && (
        <DisputePanel client={client} taskId={taskId} meId={me ? me.id : null} />
      )}
    </div>
  );
}


/** GEO-023 一键求助 / GEO-022 行程分享。
 *
 * 只在**进行中**的线下任务上出现：任务没开始或已结束时摆一个求助按钮，
 * 只会稀释它。 */
function SafetyPanel({ taskId, isExecutor }: { taskId: number; isExecutor: boolean }) {
  const { client } = useApp();
  const [guidance, setGuidance] = useState('');
  const [shared, setShared] = useState<boolean | null>(null);
  const [error, setError] = useState('');

  return (
    <div className="card">
      <h3>安全</h3>
      <div className="row">
        <button className="danger" onClick={async () => {
          setError('');
          try {
            // 浏览器上拿不到可靠定位时也要照发：求助不能因为定位失败而发不出去
            const r = await client.sos(taskId, 0, 0);
            setGuidance(r.guidance);   // 服务端给的指引原样显示
          } catch (err) {
            setError(apiErrorText(err));
          }
        }}>🆘 一键求助</button>
        {isExecutor && (
          <button className="ghost" onClick={async () => {
            setError('');
            try {
              const r = await client.setTripShare(taskId, !shared);
              setShared(r.trip_share_enabled);
            } catch (err) {
              setError(apiErrorText(err));
            }
          }}>{shared ? '关闭行程分享' : '开启行程分享'}</button>
        )}
      </div>
      {guidance && <p className="error" data-testid="sos-guidance">{guidance}</p>}
      {error && <p className="error">{error}</p>}
      <p className="muted">求助会立即通知任务对方与平台并留痕；遇到危险请先拨打 110。</p>
    </div>
  );
}


/** SC-007 变更单：提案 / 接受 / 拒绝。
 *
 * 服务端做得很完整（改价、差额多退少补、版本 +1、任务预算同步，
 * 还有多轮随机改价的资金守恒测试），而整条路对用户不存在——
 * 而且缺的**不只是按钮**：连「列出变更单」的接口都没有，
 * 对方拿不到 `order_id`，有按钮也点不了。三层一起补才通。
 */
function ChangeOrders({ contractId, amountCents, onChanged }: {
  contractId: number; amountCents: number; onChanged: () => Promise<void>;
}) {
  const { client } = useApp();
  const [rows, setRows] = useState<ChangeOrderView[]>([]);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.changeOrders(contractId).catch(() => []));
  }, [client, contractId]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); await onChanged(); }
    catch (err) { setError(apiErrorText(err)); }
  }

  const pending = rows.find((r) => r.status === 'pending');

  return (
    <div style={{ marginTop: 12 }}>
      <h4>变更单</h4>
      {rows.length === 0 && <p className="muted">没有变更单。范围或价格有调整时，从这里提出。</p>}
      {rows.map((r) => (
        <p key={r.id} className="muted">
          #{r.id} 改为 <strong>{fmtYuan(r.new_amount_cents)}</strong> · {r.status}
          {r.reason && ` · ${r.reason}`}
          {/* 读服务端的 can_decide：提案人自己不能接受，客户端不重判 */}
          {r.can_decide && (
            <span className="row" style={{ display: 'inline-flex', marginLeft: 8 }}>
              <button style={{ padding: '2px 10px' }}
                      onClick={() => act(() => client.acceptChange(contractId, r.id))}>接受</button>
              <button className="danger" style={{ padding: '2px 10px' }}
                      onClick={() => act(() => client.rejectChangeOrder(contractId, r.id))}>拒绝</button>
            </span>
          )}
        </p>
      ))}
      {!pending && (
        <div className="row">
          <input style={{ width: 130 }} type="number" min={0.01} step={0.01} placeholder="新金额（元）"
                 value={amount} onChange={(e) => setAmount(e.target.value)} />
          <input className="grow" placeholder="事由（对方会看到）" value={reason}
                 onChange={(e) => setReason(e.target.value)} />
          <button disabled={!amount} onClick={() => act(async () => {
            await client.proposeChange(contractId, Math.round(parseFloat(amount) * 100), reason);
            setAmount(''); setReason('');
          })}>提出变更</button>
        </div>
      )}
      <p className="muted">当前金额 {fmtYuan(amountCents)}；对方接受后差额自动补托管或退回。</p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** SC-004 双签前定义分期。合计必须等于合约金额——**服务端会拒**，
 *  这里把「还差多少」实时算给用户看，但**判定仍以服务端为准**。 */
function DefineMilestones({ contractId, amountCents, onDefined }: {
  contractId: number; amountCents: number; onDefined: () => Promise<void>;
}) {
  const { client } = useApp();
  const [items, setItems] = useState<Array<{ title: string; amount: string }>>([
    { title: '第一期', amount: '' }, { title: '第二期', amount: '' },
  ]);
  const [error, setError] = useState('');

  const cents = items.map((i) => Math.round(parseFloat(i.amount || '0') * 100));
  const total = cents.reduce((a, b) => a + b, 0);

  return (
    <div style={{ marginTop: 12 }}>
      <h4>分期（只能在双签前设置）</h4>
      {items.map((it, idx) => (
        <div className="row" key={idx}>
          <input className="grow" value={it.title} placeholder="这一期交付什么"
                 onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, title: e.target.value } : x))} />
          <input style={{ width: 120 }} type="number" min={0.01} step={0.01} placeholder="金额（元）"
                 value={it.amount}
                 onChange={(e) => setItems(items.map((x, i) => i === idx ? { ...x, amount: e.target.value } : x))} />
        </div>
      ))}
      <div className="row" style={{ marginTop: 6 }}>
        <button className="ghost" onClick={() => setItems([...items, { title: `第${items.length + 1}期`, amount: '' }])}>
          加一期
        </button>
        <button onClick={async () => {
          setError('');
          try {
            await client.defineMilestones(contractId, items.map((it, i) => ({
              title: it.title || `第${i + 1}期`, amount_cents: cents[i],
            })));
            await onDefined();
          } catch (err) {
            setError(apiErrorText(err));   // amount_mismatch 的理由原样显示
          }
        }}>保存分期</button>
        <span className="muted" data-testid="milestone-sum">
          合计 {fmtYuan(total)} / 合约 {fmtYuan(amountCents)}
          {total !== amountCents && `（还差 ${fmtYuan(amountCents - total)}）`}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
