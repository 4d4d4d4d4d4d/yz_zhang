import ContractEvidence from '../ContractEvidence';
import { TaskProfilePanel } from '../Profiles';
import { OperationKey, minorTaskLine, DEPOSIT_STATUS_LABEL, IP_ASSIGNMENT_LABEL, TASK_STATUS_LABEL, apiErrorText, asList, daySummaryLine, daysStillShort, dayShiftChangeLine, shiftEditableDays, raiseToCents, REBOOST_INVITE_COUNT, reboostLine, describeChangeOrder, hasChildTasks, shiftLabel, visitPresence, visitShortfall, fmtYuan, formatDateTime, localInputToServerTime, type ChangeOrderView, type Cockpit, type PlatformClient, type Contract, type Recommendation, type ApplyDaysResult, type DayApplicant, type Task, type TaskTree, type TaskVisits } from '@platform/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AgentPanel } from '../AgentPanel';
import { DisputePanel } from '../DisputePanel';
import { ExperienceTools } from '../ExperienceUnits';
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
      // APP-090 列表响应不是数组时当作空表（不把详情页带崩）
      setApps(asList(await client.listApplications(taskId)));
      setRecs(asList(await client.recommendations(taskId)));
    }
    // SCN-116：多人、多天的母任务也拉（以前只有项目型，名额在详情页上看不到）
    if (hasChildTasks(t)) {
      setTree(await client.taskTree(taskId).catch(() => null));
    }
    if (me && (t.creator_id === me.id || t.executor_id === me.id)) {
      if (!['draft', 'published'].includes(t.status)) {
        setProgress(asList(await client.listProgress(taskId).catch(() => [])));
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

  // SC-016（225 号 spec）批量放款的幂等键：网络断了再点一次是重试，服务端回放第一次的结果
  const releaseKey = useRef(new OperationKey());
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
        {/* SCN-117 每天几点到几点 */}
        {shiftLabel(task) && <p className="muted" aria-label="时段">🕘 {shiftLabel(task)}（北京时间）</p>}
        {/* SCN-118 名额是某一天的：回到整单，一次报多天 */}
        {task.parent_id !== null && task.work_date && (task.status === 'published') && (
          <p><Link to={`/tasks/${task.parent_id}`}>这单一共好几天：回到整单，一次报多天 →</Link></p>
        )}
        {/* SCN-144 服务对象是未成年人：安排方式与要求的证明 */}
        {minorTaskLine(task) && <p className="muted" aria-label="未成年人服务">{minorTaskLine(task)}</p>}
        {/* SCN-119 替别人发的单：谁都看得到是替别人发的；称呼与到场联系只给成交双方 */}
        {task.on_behalf && (
          <p className="muted" aria-label="服务对象">
            替别人发的单{task.recipient_label ? `：服务对象「${task.recipient_label}」` : '（服务对象与到场联系方式成交后可见）'}
            {task.onsite_contact ? ` · 到场联系 ${task.onsite_contact}` : ''}
          </p>
        )}
        {/* SCN-123 发单后改服务对象（197 号 spec）：不用取消重发 */}
        {task.on_behalf && isCreator && !['completed', 'cancelled', 'disputed'].includes(task.status) && (
          <RecipientEditor taskId={taskId} label={task.recipient_label ?? ''} contact={task.onsite_contact ?? ''} onSaved={setTask} />
        )}
        {/* SCN-156（278 号 spec）已完成的单：发单人允许接单人把这一单放进作品集，随时撤回 */}
        {task.status === 'completed' && isCreator && task.executor_id !== null && (
          <p aria-label="作品展示授权">
            {task.showcase_consent_at ? '你已允许接单人把这一单放进作品集。' : '接单人想把这一单（前后对比照、成品）放进作品集，要你同意。'}
            <button className="ghost" onClick={() => void act(async () => {
              if (task.showcase_consent_at) await client.withdrawShowcaseConsent(taskId);
              else await client.grantShowcaseConsent(taskId);
            })}>{task.showcase_consent_at ? '撤回展示授权' : '允许展示这一单'}</button>
          </p>
        )}
        {error && <p className="error">{error}</p>}

        {/* 状态驱动的操作区（TASK-021） */}
        <div className="row" style={{ marginTop: 12 }}>
          {task.status === 'published' && !isCreator && (
            <button onClick={() => act(() => client.apply(taskId, '我可以做'))}>报名接单</button>
          )}
          {task.status === 'published' && !isCreator && me && <QuoteToCreator taskId={taskId} creatorId={task.creator_id} />}
          {task.status === 'in_progress' && isExecutor && (
            <button onClick={() => act(() => client.deliver(taskId))}>提交验收</button>
          )}
          {task.status === 'pending_acceptance' && isCreator && (
            <>
              <button onClick={async () => {
                // SCN-125（179 号 spec）上门回报比计划少或有漏项：先说清差多少，不拦（钱的事由发单人定）
                if ((task.visits_planned ?? 0) > 0 || (task.visit_checklist ?? []).length > 0) {
                  const warn = visitShortfall(await client.taskVisits(taskId).catch(() => null));
                  if (warn && !confirm(`${warn}\n\n仍然验收通过（放款）？`)) return;
                }
                // SC-013 整单验收会放掉**剩余全部**期（服务端如此设计，93 号 spec）。
                // 发布方当初定分期，正是为了不一次付完——在一个只写
                // 「验收通过（放款）」的按钮上一次放光，他失去的是自己设的那道保护。
                // 所以还有未放期时，把「几期、多少钱」说清再让他点。
                const pending = (contract?.milestones ?? []).filter(m => m.status !== 'released');
                if (pending.length > 1) {
                  const sum = pending.reduce((n, m) => n + m.amount_cents, 0);
                  if (!confirm(
                    `这一步会放掉剩余 ${pending.length} 期、共 ${fmtYuan(sum)}。\n\n`
                    + '如果只想付已完成的那一期，请改用下面分期列表里的「验收本期」。\n\n确认整单放款？',
                  )) return;
                }
                void act(() => client.acceptDelivery(taskId));
              }}>验收通过（放款）</button>
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
      {/* PROF-103 报名前看一眼这单的画像：风险、技能、价格位置（126 号 spec） */}
      {task.status !== 'draft' && <TaskProfilePanel taskId={taskId} isCreator={task.creator_id === me?.id}
        onApplyWithQuestions={task.status === 'published' && !isCreator && me ? (m) => void act(() => client.apply(taskId, m)) : undefined} />}

      {isCreator && <AgentPanel task={task} onChanged={() => void load()} />}

      {/* AGT-080~083 经验工具：双方都能用，只出草稿（109 号 spec） */}
      {(isCreator || isExecutor) && <ExperienceTools task={task} />}

      {/* AI-DEC-041 项目型草稿还没拆完：回到拆解页接着拆（106 号 spec） */}
      {isCreator && task.task_type === 'project' && task.parent_id === null && task.status === 'draft'
        && !(tree && Array.isArray(tree.children) && tree.children.length > 0) && (
        <div className="card">
          <h3>还没拆完</h3>
          <p className="muted">这是一个项目型任务，拆成能开工的步骤并确认后，才会发布出去。</p>
          <Link to={`/tasks/${task.id}/decompose`}>继续拆解 →</Link>
        </div>
      )}

      {/* 母任务驾驶舱（AI-DEC-021/TASK-036） */}
      {tree && Array.isArray(tree.children) && tree.children.length > 0 && (
        <div className="card">
          <h3>子任务进度 {tree.progress_pct}%</h3>
          <div className="progress-bar"><div style={{ width: `${tree.progress_pct}%` }} /></div>
          {/* SCN-116 多天名额按天汇总（174 号 spec）：哪天还缺几个人 */}
          {Array.isArray(tree.by_day) && tree.by_day.length > 0 && (
            <div aria-label="按天看名额" style={{ marginTop: 12 }}>
              <p className={daysStillShort(tree.by_day).length ? 'error' : 'muted'}>
                {daysStillShort(tree.by_day).length
                  ? `还有 ${daysStillShort(tree.by_day).length} 天缺人`
                  : '每天的名额都招到人了'}
              </p>
              <ul>
                {tree.by_day.map((d) => <li key={d.date}>{daySummaryLine(d)}</li>)}
              </ul>
              {/* SCN-118 一个人一次报多天（177 号 spec）：不是发单人才有 */}
              {me && !isCreator && <ApplyDaysBox taskId={taskId} days={daysStillShort(tree.by_day).map((d) => d.date)} />}
              {/* SCN-126 发单人按人选：一次选同一个人的多天（181 号 spec） */}
              {isCreator && <PersonPicker taskId={taskId} onDone={() => void load()} />}
              {/* SCN-121 缺人的那天一键补招（196 号 spec） */}
              {isCreator && <ReboostBox taskId={taskId} days={daysStillShort(tree.by_day).map((d) => d.date)} onDone={() => void load()} />}
              {/* SCN-138 发布后改某一天的时段（202 号 spec） */}
              {isCreator && <DayShiftEditor taskId={taskId} days={shiftEditableDays(tree.by_day)} onDone={() => void load()} />}
            </div>
          )}
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

      {/* SPACE-024 合作驾驶舱：只给发布方（公开的进度仍是上面那块） */}
      {isCreator && tree && Array.isArray(tree.children) && tree.children.length > 0 && <CockpitPanel taskId={taskId} />}

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
          <h3>协作合约 #{contract.id}</h3>
          <ContractEvidence contractId={contract.id} />
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
          {isCreator && contract.status === 'pending_signatures' && !contract.signed_by_requester && !contract.signed_by_executor && (
            <DefineMilestones contractId={contract.id} amountCents={contract.amount_cents}
                              onDefined={async () => setContract(await client.getContract(contract.id))} />
          )}
          {/* SC-014 只放已交付的那几期（146 号 spec）：与「整单验收」不同，没交付的一期也不会动 */}
          {isCreator && contract.status === 'funded' && !contract.frozen && (() => {
            const delivered = (contract.milestones ?? []).filter((m) => m.status === 'delivered');
            if (delivered.length < 2) return null;
            const sum = delivered.reduce((n, m) => n + m.amount_cents, 0);
            return (
              <button style={{ marginTop: 10 }} onClick={() => {
                if (!confirm(`只放这 ${delivered.length} 期已交付的：\n${delivered.map((m) => `第 ${m.idx} 期 ${m.title} ${fmtYuan(m.amount_cents)}`).join('\n')}\n合计 ${fmtYuan(sum)}。\n\n还没交付的期不会动。确认放款？`)) return;
                const idxs = delivered.map((m) => m.idx);
                void act(async () => setContract(await releaseKey.current.run(`${contract.id}:${idxs.join(',')}:${sum}`,
                  (key) => client.releaseDelivered(contract.id, idxs, sum, key))));
              }}>放款已交付的 {delivered.length} 期（共 {fmtYuan(sum)}）</button>
            );
          })()}
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
      {/* SCN-120 一单多次上门的逐次回报（176 号 spec）：写了上门次数或清单的单才有 */}
      {(isCreator || isExecutor) && task && ((task.visits_planned ?? 0) > 0 || (task.visit_checklist ?? []).length > 0)
        && !['draft', 'published'].includes(task.status) && (
        <VisitsPanel task={task} isExecutor={!!isExecutor} />
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
/** SCN-126 按人选：谁报了哪几天，一次选上这几天（每个名额各一份合约，签署与托管仍逐份确认）。 */
function PersonPicker({ taskId, onDone }: { taskId: number; onDone: () => void }) {
  const { client } = useApp();
  const [people, setPeople] = useState<DayApplicant[]>([]);
  const [msg, setMsg] = useState('');
  const load = useCallback(() => {
    client.dayApplicants(taskId).then((r) => setPeople(Array.isArray(r) ? r : [])).catch(() => setPeople([]));
  }, [client, taskId]);
  useEffect(() => { load(); }, [load]);
  if (people.length === 0 && !msg) return null;
  async function pick(p: DayApplicant) {
    setMsg('');
    try {
      const r = await client.acceptPerson(taskId, p.applicant_id);
      setMsg(`已选 ${p.nickname}：${r.accepted.map((a) => a.date.slice(5)).join('、')}（每天一份合约，去各名额签署、托管）`
        + (r.skipped.length ? `；没选上：${r.skipped.map((s) => `${s.date.slice(5)}（${s.reason}）`).join('、')}` : ''));
      load();
      onDone();
    } catch (e) { setMsg(apiErrorText(e)); }
  }
  return (
    <div aria-label="按人选" style={{ marginTop: 8 }}>
      <p className="muted">谁报了哪几天：</p>
      {people.map((p) => (
        <div key={p.applicant_id} className="task-item">
          <span>{p.nickname} · {p.days.map((d) => d.date.slice(5)).join('、')}</span>
          <button onClick={() => void pick(p)}>选 TA 的这 {p.days.length} 天</button>
        </div>
      ))}
      {msg && <p className="muted">{msg}</p>}
    </div>
  );
}

/** SCN-118 一次报多天：勾还缺人的那几天，每天报一个名额；报不了的逐日说清。 */
/** SCN-123 改服务对象：换人、改联系方式都要重新确认问过本人 */
function RecipientEditor({ taskId, label, contact, onSaved }: {
  taskId: number; label: string; contact: string; onSaved: (t: Task) => void;
}) {
  const { client } = useApp();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(label);
  const [phone, setPhone] = useState(contact);
  const [consented, setConsented] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  if (!open) return (
    <p><button className="text-link" onClick={() => { setOpen(true); setMsg(''); }}>改服务对象</button>{msg && <span className="muted"> {msg}</span>}</p>
  );
  async function save() {
    setError('');
    try {
      onSaved(await client.changeRecipient(taskId, { recipient_label: name, onsite_contact: phone, recipient_consented: consented }));
      setOpen(false); setConsented(false); setMsg('已改好，接单的人会收到通知');
    } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="改服务对象" className="card">
      <input aria-label="服务对象怎么称呼" value={name} onChange={(e) => setName(e.target.value)} />
      <input aria-label="到场联系方式" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <label className="row"><input type="checkbox" aria-label="已经问过本人" checked={consented}
                                    onChange={(e) => setConsented(e.target.checked)} />已经问过本人（换了人或改了联系方式，要再问一次）</label>
      <button onClick={() => void save()}>保存</button> <button className="ghost" onClick={() => setOpen(false)}>取消</button>
      {msg && <p className="muted">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** SCN-138 发单人：改某一天的时段（只改还在招的名额；有人接的要走变更单） */
function DayShiftEditor({ taskId, days, onDone }: { taskId: number; days: string[]; onDone: () => void }) {
  const { client } = useApp();
  const [day, setDay] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [propose, setPropose] = useState(false);   // SCN-139 有人接的名额顺带发变更单
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  if (days.length === 0) return null;
  const target = days.includes(day) ? day : days[0];
  async function submit() {
    setError(''); setMsg('');
    try { setMsg(dayShiftChangeLine(await client.changeDayShift(taskId, target, start, end, propose))); onDone(); }
    catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="改某天的时段" style={{ marginTop: 8 }}>
      <p className="muted">某一天的时间变了？只改还在招的名额；已经有人接的要和对方走合约变更单。</p>
      <div className="row">
        <select aria-label="改哪天的时段" value={target} onChange={(e) => setDay(e.target.value)}>
          {days.map((d) => <option key={d} value={d}>{d.slice(5)}</option>)}
        </select>
        <input type="time" aria-label="这天几点开始" value={start} onChange={(e) => setStart(e.target.value)} />
        <input type="time" aria-label="这天几点结束" value={end} onChange={(e) => setEnd(e.target.value)} />
        <label><input type="checkbox" checked={propose} onChange={(e) => setPropose(e.target.checked)} /> 已经有人接的，顺带给对方发变更单</label>
        <button onClick={() => void submit()}>改这天的时段</button>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** SCN-121 发单人：缺人的那天再推一次，可选每个名额加价（只许上调；钱在签约托管时才冻结） */
function ReboostBox({ taskId, days, onDone }: { taskId: number; days: string[]; onDone: () => void }) {
  const { client } = useApp();
  const [day, setDay] = useState('');
  const [yuan, setYuan] = useState('');
  const [invite, setInvite] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  if (days.length === 0) return null;
  const target = days.includes(day) ? day : days[0];
  async function submit() {
    setError(''); setMsg('');
    const cents = raiseToCents(yuan);
    if (cents === null) { setError('加价写一个正数（元），最多两位小数；不加价就空着'); return; }
    try {
      setMsg(reboostLine(await client.reboostDay(taskId, target, cents, invite ? REBOOST_INVITE_COUNT : 0), invite));
      setYuan(''); onDone();
    }
    catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="补招" style={{ marginTop: 8 }}>
      <p className="muted">缺人的那天再推一次：还在招的名额会推给附近有空、订阅了这个类目的人。</p>
      <div className="row">
        <select aria-label="补招哪天" value={target} onChange={(e) => setDay(e.target.value)}>
          {days.map((d) => <option key={d} value={d}>{d.slice(5)}</option>)}
        </select>
        <input aria-label="每个名额加价（元）" placeholder="每个名额加价（元，可不填）" value={yuan} onChange={(e) => setYuan(e.target.value)} />
        {/* SCN-137（206 号 spec）顺带邀请几个做过这类活、那天正好有空的人 */}
        <label><input type="checkbox" checked={invite} onChange={(e) => setInvite(e.target.checked)} /> 顺带邀请 {REBOOST_INVITE_COUNT} 个做过这类活、那天有空的人</label>
        <button onClick={() => void submit()}>补招这天</button>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function ApplyDaysBox({ taskId, days }: { taskId: number; days: string[] }) {
  const { client } = useApp();
  const [picked, setPicked] = useState<string[]>([]);
  const [result, setResult] = useState<ApplyDaysResult | null>(null);
  const [error, setError] = useState('');
  if (days.length === 0) return null;
  async function submit() {
    setError(''); setResult(null);
    try { setResult(await client.applyDays(taskId, picked)); setPicked([]); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div aria-label="一次报多天" style={{ marginTop: 8 }}>
      <p className="muted">这几天你都能来？勾上一次报完（每天报一个名额，发单人逐天选人）：</p>
      {days.map((d) => (
        <label key={d} className="row">
          <input type="checkbox" aria-label={`报 ${d}`} checked={picked.includes(d)}
                 onChange={(e) => setPicked((p) => e.target.checked ? [...p, d] : p.filter((x) => x !== d))} />
          {d.slice(5)}
        </label>
      ))}
      <button disabled={picked.length === 0} onClick={() => void submit()}>报这几天</button>
      {result && (
        <p className="muted">
          已报：{result.applied.map((a) => a.date.slice(5)).join('、') || '无'}
          {result.skipped.length ? `；没报：${result.skipped.map((s) => `${s.date.slice(5)}（${s.reason}）`).join('、')}` : ''}
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** SCN-120 上门回报：接单人每次勾清单、写备注、附照片；双方都看得到计划几次、回报几次、每次漏了什么。 */
function VisitsPanel({ task, isExecutor }: { task: Task; isExecutor: boolean }) {
  const { client } = useApp();
  const [data, setData] = useState<TaskVisits | null>(null);
  const [done, setDone] = useState<string[]>([]);
  const [note, setNote] = useState('');
  const [shots, setShots] = useState<string[]>([]);
  const [error, setError] = useState('');
  const load = useCallback(() => { client.taskVisits(task.id).then(setData).catch(() => setData(null)); }, [client, task.id]);
  useEffect(() => { load(); }, [load]);
  const checklist = task.visit_checklist ?? [];
  async function submit() {
    setError('');
    try {
      await client.reportVisit(task.id, { done, note, images: shots });
      setDone([]); setNote(''); setShots([]);
      load();
    } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card" aria-label="上门回报">
      <h3>上门回报{data ? ` · ${data.reported}${data.planned ? `/${data.planned}` : ''} 次` : ''}</h3>
      {data && data.missed_total > 0 && <p className="error">一共有 {data.missed_total} 项没做（见下面每次的记录）</p>}
      {/* SCN-136（204 号 spec）几次回报带了到场打卡 */}
      {visitPresence(data) && <p className="muted" aria-label="到场次数">{visitPresence(data)}</p>}
      {/* SCN-125 发单人验收前看一眼差多少 */}
      {!isExecutor && task.status === 'pending_acceptance' && visitShortfall(data) && (
        <p className="error" aria-label="验收前提醒">{visitShortfall(data)}</p>
      )}
      {data && Array.isArray(data.visits) && data.visits.map((v) => (
        <div key={v.id} className="task-item">
          <span>第 {v.n} 次 · {formatDateTime(v.created_at)}</span>
          <span className="muted">
            {v.done.length ? `已做：${v.done.join('、')}` : '清单没勾'}{v.missed.length ? `；没做：${v.missed.join('、')}` : ''}
            {v.note ? ` · ${v.note}` : ''}{v.images.length ? ` · ${v.images.length} 张照片` : ''}
            {typeof v.at_site_m === 'number' ? ` · 到场（距 ${v.at_site_m} 米）` : ''}
          </span>
        </div>
      ))}
      {isExecutor && task.status === 'in_progress' && (
        <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
          {checklist.map((item) => (
            <label key={item} className="row">
              <input type="checkbox" aria-label={`做了：${item}`} checked={done.includes(item)}
                     onChange={(e) => setDone((d) => e.target.checked ? [...d, item] : d.filter((x) => x !== item))} />
              {item}
            </label>
          ))}
          <input aria-label="这次的备注" placeholder="这次的备注（宠物状态、异常情况…）" value={note} onChange={(e) => setNote(e.target.value)} />
          <PhotoPicker urls={shots} onChange={setShots} />
          {error && <p className="error">{error}</p>}
          <button onClick={() => void submit()}>交这次的上门回报</button>
        </div>
      )}
    </div>
  );
}

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
  const [deadline, setDeadline] = useState('');
  const [scope, setScope] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(asList(await client.changeOrders(contractId).catch(() => [])));
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
          #{r.id} <strong>{describeChangeOrder(r, amountCents, (t) => formatDateTime(t))}</strong> · {r.status}
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
                 aria-label="新金额" value={amount} onChange={(e) => setAmount(e.target.value)} />
          {/* SC-007b 改期、改范围：真实的「加了两个房间」通常同时要改期 */}
          <input type="datetime-local" aria-label="新的截止时间" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          <input className="grow" aria-label="范围调整" placeholder="范围调整（如：增加两个卧室）" maxLength={1000}
                 value={scope} onChange={(e) => setScope(e.target.value)} />
          <input className="grow" placeholder="事由（对方会看到）" value={reason}
                 onChange={(e) => setReason(e.target.value)} />
          <button disabled={!amount && !deadline && !scope.trim()} onClick={() => act(async () => {
            await client.proposeChangeOrder(contractId, {
              new_amount_cents: amount ? Math.round(parseFloat(amount) * 100) : undefined,
              new_deadline: deadline ? localInputToServerTime(deadline) : undefined,
              scope_change: scope.trim() || undefined, reason,
            });
            setAmount(''); setReason(''); setDeadline(''); setScope('');
          })}>提出变更</button>
        </div>
      )}
      <p className="muted">当前金额 {fmtYuan(amountCents)}；金额、截止时间、范围可以一起改，对方接受后差额自动补托管或退回、任务截止与说明同步更新。</p>
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


/** IM-009 私信报价：不急着报名，先把价格和说明发给发布方，在私聊里谈。 */
function QuoteToCreator({ taskId, creatorId }: { taskId: number; creatorId: number }) {
  const { client } = useApp();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  if (!open) return <button className="ghost" onClick={() => setOpen(true)}>私信报价</button>;
  return (
    <span className="row" aria-label="私信报价">
      <input type="number" min={1} aria-label="报价（元）" placeholder="报价（元）" value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: 120 }} />
      <input aria-label="报价说明" placeholder="含哪些、多久完成" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
      <button disabled={!(parseFloat(price) > 0)} onClick={async () => {
        setError('');
        try {
          const conv = await client.openDirect(creatorId);
          await client.sendQuoteCard(conv.id, taskId, Math.round(parseFloat(price) * 100), note);
          nav(`/messages?conversation=${conv.id}`);
        } catch (e) { setError(apiErrorText(e)); }
      }}>发给发布方</button>
      {error && <span className="error">{error}</span>}
    </span>
  );
}


type FinalReport = Awaited<ReturnType<PlatformClient['finalReport']>>;

/** AGT-090 结项报告：花了多少（按实际放款）、多久、谁交付了什么。只有发布者看得到。 */
function FinalReportBox({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [r, setR] = useState<FinalReport | null>(null);
  const [error, setError] = useState('');
  if (!r) return <p><button className="ghost" onClick={() => void client.finalReport(taskId).then(setR).catch((e) => setError(apiErrorText(e)))}>看结项报告</button>{error && <span className="error"> {error}</span>}</p>;
  return (
    <div className="card" aria-label="结项报告">
      <h4>结项报告</h4>
      <p>{r.summary}</p>
      <p className="muted">实付（按合约放款）{fmtYuan(r.paid_cents)} · 计划 {fmtYuan(r.planned_budget_cents)}{r.duration_days !== null ? ` · 用时 ${r.duration_days} 天` : ''}</p>
      <ul className="list">{r.deliverables.map((d) => <li key={d.task_id}><Link to={`/tasks/${d.task_id}`}>{d.title}</Link> <span className="muted">· {fmtYuan(d.cost_cents)} · {d.status === 'completed' ? '已完成' : d.status}</span></li>)}</ul>
    </div>
  );
}

/** SPACE-024 / AI-DEC-021 合作驾驶舱：现在做到哪、卡在谁那里、钱花了多少、哪里要我出手。 */
function CockpitPanel({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [data, setData] = useState<Cockpit | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { client.cockpit(taskId).then(setData).catch((e) => setError(apiErrorText(e))); }, [client, taskId]);
  if (error) return <div className="card"><p className="error">{error}</p></div>;
  // 驾驶舱是详情页上的一块：响应不像预期时不画，不许把整页带崩（与 App 的 CockpitBlock 同一条）
  if (!data || !Array.isArray(data.nodes) || !data.budget) return null;
  const title = (id: number) => data.nodes.find((n) => n.id === id)?.title ?? `#${id}`;
  const b = data.budget;
  return (
    <div className="card" aria-label="合作驾驶舱">
      <h3>合作驾驶舱 · {data.steps_done}/{data.steps_total} 步完成</h3>
      <div className="row">
        <span>计划 <strong>{fmtYuan(b.planned_cents)}</strong></span>
        <span>已托管 <strong>{fmtYuan(b.committed_cents)}</strong></span>
        <span>已付 <strong>{fmtYuan(b.paid_cents)}</strong></span>
        <span>还剩 <strong>{fmtYuan(b.remaining_cents)}</strong></span>
      </div>
      {data.alerts.length > 0 && (
        <ul className="list" aria-label="需要你出手">
          {data.alerts.map((a, i) => <li key={i} className={a.kind === 'dispute' || a.kind === 'overdue' ? 'error' : ''}>
            <Link to={`/tasks/${a.task_id}`}>{a.text}</Link></li>)}
        </ul>
      )}
      {data.critical_path.length > 0 && (
        <p><span className="muted">关键路径（剩余步骤最多的一条，任何一步拖一天，整件事就晚一天）：</span>
          {data.critical_path.map(title).join(' → ')}</p>
      )}
      {/* AGT-090 全部步骤完成后：结项报告（132 号 spec） */}
      {data.steps_total > 0 && data.steps_done === data.steps_total && <FinalReportBox taskId={taskId} />}
      <table aria-label="每一步">
        <thead><tr><th>步骤</th><th>谁在做</th><th>状态</th><th>预算</th><th>截止</th><th>卡在</th></tr></thead>
        <tbody>
          {data.nodes.filter((n) => !n.is_container).map((n) => (
            <tr key={n.id} data-critical={n.on_critical_path || undefined}>
              <td><Link to={`/tasks/${n.id}`}>{n.on_critical_path ? '★ ' : ''}{n.title}</Link></td>
              <td>{n.executor_nickname ?? <span className="muted">还没人</span>}</td>
              <td>{n.in_dispute ? '纠纷中' : n.status_name}</td>
              <td>{fmtYuan(n.budget_cents)}</td>
              <td className={n.overdue ? 'error' : ''}>{n.deadline ? formatDateTime(n.deadline) : '—'}{n.overdue ? '（已逾期）' : ''}</td>
              <td>{n.blocked_by.length ? n.blocked_by.map(title).join('、') : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
