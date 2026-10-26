// AI-DEC-024（321 号 spec）跨子任务产出共享：前一步的交付人授权后，后一步的执行者才看得到。
// 开不开放是交付人的权利：默认谁也看不到，交了之后才能开、只能开给依赖这一步的那几步、随时收回；
// 开放的是交付说明与预览图，原图不在里面。
import { apiErrorText, formatDateTime, TASK_STATUS_LABEL, type SubtaskInput, type SubtaskShareView } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from './store';

/** 前一步的执行者：把成果开放给依赖这一步的后一步 */
export function ShareToNextSteps({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [view, setView] = useState<SubtaskShareView | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    client.subtaskShares(taskId).then(setView).catch(() => setView(null));
  }, [client, taskId]);
  useEffect(() => { load(); }, [load]);
  const steps = Array.isArray(view?.next_steps) ? view.next_steps : [];
  if (!view || steps.length === 0) return null;
  async function run(fn: () => Promise<SubtaskShareView>) {
    setError('');
    try { setView(await fn()); } catch (e) { setError(apiErrorText(e)); }
  }
  return (
    <div className="card" aria-label="开放给下一步">
      <h3>把成果开放给下一步</h3>
      <p className="muted">
        {view.delivered
          ? '下面这几步要等你这一步。开不开放由你定：开了，那一步的执行者能看你的交付说明和预览图（原图不在里面），随时可以收回。'
          : '交付之后，可以把交付说明和预览图开放给要等你这一步的人。'}
      </p>
      <div className="list">
        {steps.map((s) => (
          <div className="task-item" key={s.task_id}>
            <div>
              <strong>{s.title}</strong>{' '}
              <span className="muted">{TASK_STATUS_LABEL[s.status] ?? s.status} · {s.executor_nickname ?? '还没人接'}</span>
              {s.shared && <span className="badge">已开放</span>}
            </div>
            {view.delivered && (s.shared && s.share_id
              ? <button onClick={() => void run(() => client.revokeSubtaskShare(taskId, s.share_id as number))}>收回</button>
              : <button onClick={() => void run(() => client.shareToNextStep(taskId, s.task_id))}>开放给这一步</button>)}
          </div>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** 后一步的执行者：前一步的交付人开放给这一步的成果 */
export function PreviousStepInputs({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [rows, setRows] = useState<SubtaskInput[]>([]);
  useEffect(() => {
    client.subtaskInputs(taskId).then((r) => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]));
  }, [client, taskId]);
  if (rows.length === 0) return null;
  return (
    <div className="card" aria-label="前一步的成果">
      <h3>前一步的成果</h3>
      <p className="muted">前一步的交付人开放给你的交付说明与预览图；对方可以随时收回，需要留底的请和发单人确认。</p>
      {rows.map((r) => (
        <div key={r.from_task_id} style={{ marginTop: 8 }}>
          <strong>{r.title}</strong> <span className="muted">开放于 {formatDateTime(r.shared_at)}</span>
          {(Array.isArray(r.deliveries) ? r.deliveries : []).map((d, i) => (
            <div key={i}>
              <p>{d.content}</p>
              {(Array.isArray(d.images) ? d.images : []).map((u) => <img key={u} src={u} alt="交付凭证" width={72} height={72} style={{ objectFit: 'cover' }} />)}
            </div>
          ))}
          <div className="row">
            {(Array.isArray(r.previews) ? r.previews : []).map((p) => <img key={p.id} src={p.url} alt="前一步的预览图" width={96} height={96} style={{ objectFit: 'cover', borderRadius: 8 }} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
