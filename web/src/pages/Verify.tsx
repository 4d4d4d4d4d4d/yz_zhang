import {
  apiErrorText, fmtYuan,
  type VerificationOrderDetail, type VerificationOrderView,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

type OpenOrder = VerificationOrderView & {
  category: string; task_title: string; claimable: boolean; reason: string;
};

/** CLI-063 核验台（核验人视角）。
 *
 * V74 把「AI 干不了的活交给人来判」整条做完了，**网页上没有任何入口**：
 * 没人能看到核验单，也就没人能接（57 号 spec）。
 *
 * CLI-064：不能接的单子要显示**服务端给的资格原因**。VER 自己的话是
 * 「只显示空列表，核验人不知道是资格不够还是真没单」。
 */
export default function Verify() {
  const { client } = useApp();
  const [orders, setOrders] = useState<OpenOrder[]>([]);
  const [detail, setDetail] = useState<VerificationOrderDetail | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setOrders(await client.openVerificationOrders().catch(() => []));
  }, [client]);

  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError(''); setBusy(true);
    try {
      await fn();
      await load();
    } catch (err) {
      setError(apiErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="card">
        <h3>核验台</h3>
        <p className="muted">
          AI 助理没把握、或者判据没过的任务会到这里，由人来判它做得对不对。
          核验是「看一遍」不是「重做」，报酬按原任务金额的一个比例计。
        </p>
        {error && <p className="error">{error}</p>}
        <div className="list">
          {orders.length === 0 && <p className="muted">当前没有待核验的任务。</p>}
          {orders.map((o) => (
            <div className="task-item" key={o.id}>
              <div>
                <strong>{o.task_title}</strong>{' '}
                <span className="muted">{o.category} · 报酬 {fmtYuan(o.fee_cents)}</span>
                <p className="muted">
                  {o.trigger === 'escalation' ? '助理置信度不足，自动升级（平台付费）' : '发布方主动申请核验'}
                </p>
                {/* CLI-064 不能接时把资格原因显示出来 */}
                {!o.claimable && <p className="error" data-testid="verify-reason">{o.reason}</p>}
              </div>
              <button disabled={!o.claimable || busy}
                      onClick={() => act(async () => {
                        await client.claimVerificationOrder(o.id);
                        setDetail(await client.verificationOrder(o.id));
                      })}>
                接下
              </button>
            </div>
          ))}
        </div>
      </div>

      {detail && <OrderDetail detail={detail} onDone={() => { setDetail(null); void load(); }} />}
    </div>
  );
}

function OrderDetail({ detail, onDone }: { detail: VerificationOrderDetail; onDone: () => void }) {
  const { client } = useApp();
  const [outcome, setOutcome] = useState<'approved' | 'revised' | 'rejected'>('approved');
  const [comment, setComment] = useState('');
  const [revised, setRevised] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(''); setBusy(true);
    try {
      await client.submitVerificationOutcome(detail.id, outcome, comment, revised);
      onDone();
    } catch (err) {
      setError(apiErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>核验 #{detail.id}：{detail.task_title}</h3>
      <p className="muted">{detail.task_description}</p>

      <h4>验收标准</h4>
      <ul className="muted">
        {detail.acceptance_criteria.map((c, i) => (
          <li key={i}>{c.text} {c.kind === 'auto' && <span className="badge">平台自动判</span>}</li>
        ))}
      </ul>

      <h4>AI 产出</h4>
      <pre className="agent-output">{detail.agent_output}</pre>
      <p className="muted">
        助理自报置信度{' '}
        {detail.agent_confidence_bps === null ? '—' : `${(detail.agent_confidence_bps / 100).toFixed(1)}%`}
        {/* 说明它是自报的：正因为自报，才需要平台判据压在它上面 */}
        （自报值，仅供参考）
      </p>
      {detail.agent_criteria_results.length > 0 && (
        <ul className="muted">
          {detail.agent_criteria_results.map((c, i) => (
            <li key={i}>{c.passed ? '✓' : '✗'} {c.text}</li>
          ))}
        </ul>
      )}

      <h4>你的结论</h4>
      <div className="row">
        {([['approved', '通过'], ['revised', '已修正'], ['rejected', '不通过']] as const).map(([v, label]) => (
          <label key={v} className="row" style={{ gap: 4 }}>
            <input type="radio" name="outcome" value={v} checked={outcome === v}
                   onChange={() => setOutcome(v)} />
            {label}
          </label>
        ))}
      </div>
      <textarea placeholder="核验说明（发布方与平台都会看到）" value={comment}
                onChange={(e) => setComment(e.target.value)} />
      {outcome === 'revised' && (
        <>
          <textarea placeholder="修正稿正文（它会成为交付物，而不是 AI 的原始产出）"
                    value={revised} onChange={(e) => setRevised(e.target.value)} />
          {/* VER-030 修正稿要重新过一遍平台判据，不过就交不上去 */}
          <p className="muted">修正稿会重新跑一遍平台的自动判据，不通过会被退回。</p>
        </>
      )}
      {error && <p className="error">{error}</p>}
      <button disabled={busy} onClick={() => void submit()}>提交结论</button>
    </div>
  );
}
