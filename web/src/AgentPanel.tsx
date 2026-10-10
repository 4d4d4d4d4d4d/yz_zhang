import {
  apiErrorText, fmtYuan,
  type AgentProfileView, type AgentRunView, type EligibleAgent, type Task,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** CLI-063 任务详情页的「AI 助理」面板（发布方视角）。
 *
 * V73/V74 把整条 agent 链路做完了，**网页上一个入口都没有**：
 * 发布方无法邀请助理，也看不到它跑出了什么（57 号 spec）。
 *
 * 这个面板有一条贯穿始终的要求（CLI-064）：**服务端已经算好了
 * 「为什么不行」，界面就得原样显示它**。只显示一个空列表看起来更干净，
 * 但发布方不知道是因为要到场、还是金额超限，也就不知道该改什么。
 */
export function AgentPanel({ task, onChanged }: { task: Task; onChanged: () => void }) {
  const { client } = useApp();
  const [candidates, setCandidates] = useState<EligibleAgent[]>([]);
  const [agents, setAgents] = useState<AgentProfileView[]>([]);
  const [runs, setRuns] = useState<AgentRunView[]>([]);
  const [deliveryBlock, setDeliveryBlock] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const executorIsAgent = task.executor_id != null
    && agents.some((a) => a.user_id === task.executor_id);

  const load = useCallback(async () => {
    setAgents(await client.agents().catch(() => []));
    if (task.status === 'published') {
      setCandidates(await client.eligibleAgents(task.id).catch(() => []));
    }
    if (task.executor_id) {
      const r = await client.agentRuns(task.id).catch(() => null);
      if (r) { setRuns(r.runs); setDeliveryBlock(r.delivery_block); }
    }
  }, [client, task.id, task.status, task.executor_id]);

  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done = '') {
    setError(''); setNotice(''); setBusy(true);
    try {
      await fn();
      if (done) setNotice(done);
      await load();
      onChanged();
    } catch (err) {
      setError(apiErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  // 非远程任务根本不该出现这个面板：AGT-010 的第一条闸门就是
  // 「需到场完成的任务不能由 AI 助理执行」，在界面上先说清楚比让人点了再被拒好。
  if (!task.is_remote && !executorIsAgent) return null;
  if (!['published', 'matched', 'in_progress', 'pending_acceptance'].includes(task.status)) {
    return null;
  }

  const latest = runs.length > 0 ? runs[runs.length - 1] : null;

  return (
    <div className="card">
      <h3>AI 助理</h3>
      {error && <p className="error">{error}</p>}
      {notice && <p className="muted">{notice}</p>}

      {task.status === 'published' && (
        <>
          <p className="muted">
            由你主动邀请，平台不会自动派单——让 AI 接自己的活是一个需要知情的选择。
            助理走与人一样的报名、选人、签约、托管流程。
          </p>
          <div className="list">
            {candidates.length === 0 && <p className="muted">平台暂无在售助理。</p>}
            {candidates.map((a) => (
              <div className="task-item" key={a.user_id}>
                <div>
                  <strong>{a.name}</strong>{' '}
                  <span className="muted">
                    {a.domains.join(' / ')} · 承接上限 {fmtYuan(a.max_task_budget_cents)}
                  </span>
                  {/* CLI-064 不可用时显示服务端给的理由，不是把它吞掉 */}
                  {!a.eligible && <p className="error" data-testid="agent-reason">{a.reason}</p>}
                </div>
                <button disabled={!a.eligible || busy}
                        onClick={() => act(() => client.inviteAgent(task.id, a.user_id), '已邀请')}>
                  邀请
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {executorIsAgent && (
        <>
          <p className="muted">
            本任务由平台 AI 助理执行，<strong>平台是本任务履约的责任主体</strong>（合同里已写明）。
          </p>
          {task.status === 'in_progress' && (
            <button disabled={busy} onClick={() => act(() => client.runAgent(task.id))}>
              {runs.length === 0 ? '开始执行' : '重新执行'}
            </button>
          )}
          <div className="list" style={{ marginTop: 12 }}>
            {runs.length === 0 && <p className="muted">尚未执行。</p>}
            {runs.map((r) => <RunRow key={r.id} run={r} />)}
          </div>

          {deliveryBlock && (
            <>
              <p className="error" style={{ marginTop: 8 }} data-testid="delivery-block">{deliveryBlock}</p>
              <div className="row">
                <button className="ghost" disabled={busy}
                        onClick={() => act(() => client.requestVerification(task.id), '核验单已提交')}>
                  申请人工核验
                </button>
              </div>
              {/* VER-002 谁付费不是细节：平台自有 agent 没把握是平台的问题 */}
              <p className="muted">
                置信度不足导致的升级由平台承担核验费；你主动核验一个已成功的结果，费用由你承担。
              </p>
            </>
          )}
        </>
      )}

      {latest && latest.status === 'succeeded' && task.status === 'pending_acceptance' && (
        <p className="muted">助理已交付，请在上方验收或驳回。</p>
      )}
    </div>
  );
}

function RunRow({ run }: { run: AgentRunView }) {
  const label: Record<string, string> = {
    running: '执行中', succeeded: '已完成', escalated: '待人工核验', failed: '失败',
  };
  return (
    <div className="task-item" style={{ alignItems: 'flex-start' }}>
      <div className="grow">
        <span className={`badge ${run.status === 'succeeded' ? 'ok' : run.status === 'failed' ? 'bad' : 'warn'}`}>
          {label[run.status] ?? run.status}
        </span>{' '}
        {/* AGT-013 说清楚这是**自报**的置信度，不是平台的判断 */}
        <span className="muted">助理自报置信度 {(run.confidence_bps / 100).toFixed(1)}%</span>
        {run.error && <p className="error">{run.error}</p>}
        {run.output && <pre className="agent-output">{run.output}</pre>}
        {run.criteria_results.length > 0 && (
          <ul className="muted">
            {run.criteria_results.map((c, i) => (
              <li key={i}>
                {c.passed ? '✓' : '✗'} {c.text}
                {c.kind === 'manual' && <span className="badge">需人工判</span>}
              </li>
            ))}
          </ul>
        )}
        {run.moderation_status === 'review' && (
          <p className="muted">内容审核未给出明确结论，已转人工核验。</p>
        )}
      </div>
    </div>
  );
}
