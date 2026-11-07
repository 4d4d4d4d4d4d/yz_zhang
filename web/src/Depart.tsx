/** SCN-122c（364 号 spec）接单人「出发了」：选预计多少分钟到，发单人收到通知，服务对象的进度链接页也显示。 */
import { DEPART_ETA_MINUTES, apiErrorText, formatDateTime, type DepartResult, type Task } from '@platform/core';
import { useState } from 'react';
import { useApp } from './store';

export function canDepart(task: Pick<Task, 'is_remote' | 'status' | 'executor_id'>, meId: number | null | undefined): boolean {
  return !task.is_remote && meId != null && task.executor_id === meId && ['matched', 'in_progress'].includes(task.status);
}

export function DepartPanel({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [minutes, setMinutes] = useState<number>(30);
  const [done, setDone] = useState<DepartResult | null>(null);
  const [error, setError] = useState('');
  return (
    <div aria-label="出发了" className="card" style={{ marginTop: 8 }}>
      <label>预计
        <select aria-label="预计多少分钟到" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
          {DEPART_ETA_MINUTES.map((m) => <option key={m} value={m}>{m} 分钟</option>)}
        </select>
        到
      </label>
      <button type="button" onClick={() => {
        setError('');
        client.departTask(taskId, minutes).then(setDone).catch((e) => setError(apiErrorText(e)));
      }}>{done ? '改一下预计时间' : '出发了'}</button>
      {done && <p role="status">已告诉发单人：预计 {formatDateTime(done.eta_at)} 到{done.updated ? '（已更新时间）' : ''}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
