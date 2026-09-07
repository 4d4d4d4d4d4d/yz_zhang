// DSPC-021 纠纷面板：把「答辩 / 和解 / 申诉」这三件当事人本来就有权做、
// 却在任何客户端上都做不了的事，接到界面上。
//
// 改造前，纠纷开出来之后当事人在客户端上是哑的：唯一能做的动作是发起纠纷。
// 服务端把「两造兼听」当作裁决的硬性前置（DSP-005），而没有任何客户端能
// 写入陈述——那道前置永远只能靠等答辩期超时来满足，也就是说平台上线后的
// 每一份处理决定都会是缺席裁决。
import { useCallback, useEffect, useState } from 'react';
import { ApiError, type Dispute, type DisputeStatement, type PlatformClient } from '@platform/core';

const STATUS_LABEL: Record<string, string> = {
  open: '处理中',
  appealed: '申诉复核中',
  resolved: '平台已作出处理决定',
  settled: '双方已和解',
};

function deadlineText(iso: string): string {
  const left = new Date(iso + 'Z').getTime() - Date.now();
  if (left <= 0) return '答辩期已过，平台可缺席作出处理决定';
  const hours = Math.floor(left / 3_600_000);
  return hours >= 1 ? `答辩截止还有约 ${hours} 小时` : '答辩截止不足 1 小时';
}

export function DisputePanel({ client, taskId, meId }: {
  client: PlatformClient;
  taskId: number;
  meId: number | null;
}) {
  const [dispute, setDispute] = useState<Dispute | null>(null);
  const [statements, setStatements] = useState<DisputeStatement[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      // DSPC-010 被诉方只知道任务 id——他收到的通知就只说「任务 #N 有纠纷」
      const d = await client.disputeByTask(taskId);
      setDispute(d);
      setStatements(await client.disputeStatements(d.id));
    } catch {
      setDispute(null);   // 该任务没有纠纷，面板不渲染
    }
  }, [client, taskId]);

  useEffect(() => { void load(); }, [load]);

  if (!dispute) return null;

  const closed = dispute.status === 'resolved' || dispute.status === 'settled';
  const iAmRespondent = meId !== null && dispute.respondent_id === meId;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>纠纷 #{dispute.id} · {STATUS_LABEL[dispute.status] ?? dispute.status}</h3>
      <p className="muted">事由：{dispute.reason}</p>
      {/* 服务端算出来的截止时间。客户端不该自己拿 48 硬编码—— */}
      {/* 答辩期长度是 PLATFORM_DISPUTE_RESPONSE_HOURS，运维随时可以改 */}
      {!closed && <p className="muted">{deadlineText(dispute.response_deadline)}</p>}
      {iAmRespondent && !dispute.respondent_spoke && !closed && (
        <p className="error">你尚未答辩。逾期未答辩，平台可仅凭对方的陈述作出处理决定。</p>
      )}

      <div className="list">
        {statements.length === 0 && <p className="muted">还没有任何陈述。</p>}
        {statements.map((s) => (
          <div key={s.id} className="row">
            <span className="badge">{s.role === 'opener' ? '发起方' : '被诉方'}</span>
            <span>{s.content}</span>
            <span className="muted">{s.created_at.slice(0, 16).replace('T', ' ')}</span>
          </div>
        ))}
      </div>

      {/* DSPC-022 结案后输入框消失：服务端本来就会 409， */}
      {/* 但不该让用户写完一整段陈述才被拒 */}
      {!closed && (
        <div className="row">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="提交答辩与举证说明（至少 5 个字）"
            rows={3}
          />
          <button
            disabled={busy || draft.trim().length < 5}
            onClick={() => run(async () => {
              await client.addDisputeStatement(dispute.id, draft.trim());
              setDraft('');
            })}
          >提交答辩</button>
        </div>
      )}

      {!closed && (
        <div className="row">
          <button className="ghost" disabled={busy} onClick={() => run(async () => {
            const raw = prompt('和解提案：执行方分得的比例（0~100）');
            if (raw === null) return;
            const pct = Number(raw);
            if (!Number.isFinite(pct) || pct < 0 || pct > 100) throw new ApiError(400, 'bad', '比例需在 0~100 之间');
            await client.proposeSettlement(dispute.id, Math.round(pct * 100));
          })}>提出和解</button>
          {dispute.settlement_proposal && dispute.settlement_proposal.proposed_by !== meId && (
            <button disabled={busy} onClick={() => run(() => client.acceptSettlement(dispute.id))}>
              接受和解（执行方 {dispute.settlement_proposal.executor_share_bps / 100}%）
            </button>
          )}
        </div>
      )}

      {dispute.status === 'resolved' && (
        <div className="row">
          <span className="muted">
            处理决定：执行方分得 {(dispute.verdict_executor_share_bps ?? 0) / 100}%
            {dispute.verdict_reason && `（${dispute.verdict_reason}）`}
          </span>
          {/* appealable 由服务端算，与 POST /appeal 的准入是同一个判断—— */}
          {/* 不允许客户端把那三条规则再实现一遍，画出一个必然 409 的按钮 */}
          {dispute.appealable && (
            <button className="ghost" disabled={busy}
              onClick={() => run(() => client.appealDispute(dispute.id))}>申诉复核（每案一次）</button>
          )}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
