// XAPP 跨 App 助手在 Web 上（161 号 spec）：看授权与执行记录、确认、叫停、撤销。
// 执行在本人的设备上（手机或桌面执行器）进行；网页负责管理与回看。
import {
  apiErrorText, formatDateTime, type XappCatalog, type XappGrant, type XappRun, type XappRunDetail,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';

const STATUS: Record<string, string> = { running: '执行中', needs_human: '交还给你了', stopped: '已叫停', done: '完成', failed: '失败' };
const STEP_STATUS: Record<string, string> = { pending: '待执行', dispatched: '执行中', done: '完成', done_by_user: '你已亲手完成', failed: '失败', skipped: '跳过' };
const CHANNEL: Record<string, string> = { api: '官方接口', deeplink: '深链', a11y: '读取控件', vision: '看屏幕' };

export default function Xapp() {
  const { client } = useApp();
  const [cat, setCat] = useState<XappCatalog | null>(null);
  const [grants, setGrants] = useState<XappGrant[]>([]);
  const [runs, setRuns] = useState<XappRun[]>([]);
  const [open, setOpen] = useState<XappRunDetail | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      setCat(await client.xappCatalog());
      setGrants(await client.xappGrants());
      setRuns(await client.xappRuns());
    } catch (e) { setError(apiErrorText(e)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done = '') {
    setError(''); setNotice('');
    try { await fn(); if (done) setNotice(done); await load(); } catch (e) { setError(apiErrorText(e)); }
  }
  const view = async (id: number) => setOpen(await client.xappRun(id));

  return (
    <div className="page">
      <h2>跨 App 助手</h2>
      {cat && <p className="muted" data-testid="xapp-notice">{cat.notice} 执行在你自己的设备上进行（手机或桌面执行器），这里管理授权、确认与回看。</p>}
      <div className="card" aria-label="授权">
        <h3>授权</h3>
        {grants.length === 0 && <p className="muted">还没有授权。请在手机 App「我的 → 跨 App 助手」里授权这台设备。</p>}
        {grants.map((g) => (
          <div className="task-item" key={g.id}>
            <div>
              <strong>{g.device_label || `设备 #${g.id}`}</strong> · {g.apps.join('、')}
              <p className="muted">{g.active ? `生效中，${formatDateTime(g.expires_at)} 到期` : '已失效'}{g.allow_cloud_vision ? ' · 允许云端看屏幕' : ' · 屏幕只在本机处理'}</p>
            </div>
            {g.active && <button className="ghost" onClick={() => void act(() => client.revokeXappGrant(g.id), '已撤销，正在跑的执行一起停了')}>撤销</button>}
          </div>
        ))}
      </div>
      <div className="card" aria-label="执行记录">
        <h3>执行记录</h3>
        {runs.length === 0 && <p className="muted">还没有执行过。</p>}
        {runs.map((r) => (
          <div className="task-item" key={r.id}>
            <div><strong>{r.goal}</strong> <span className="badge">{STATUS[r.status] ?? r.status}</span>
              <p className="muted">{formatDateTime(r.created_at)}{r.stop_reason ? ` · ${r.stop_reason}` : ''}</p></div>
            <button className="ghost" onClick={() => void act(() => view(r.id))}>看步骤</button>
          </div>
        ))}
      </div>
      {open && (
        <div className="card" aria-label="执行详情">
          <h3>{open.goal}（{STATUS[open.status] ?? open.status}）</h3>
          <ol>
            {open.steps.map((st) => (
              <li key={st.id} data-testid={`xapp-step-${st.seq}`}>
                {st.intent}（{st.action_label} · {st.app} · {CHANNEL[st.channel] ?? st.channel}）· {STEP_STATUS[st.status] ?? st.status}
                {st.red_line && <span className="badge warn"> 要你亲手完成</span>}
                {st.result && <span className="muted"> · {st.result}</span>}
                {open.status === 'running' && st.needs_confirm && !st.confirmed && !['done', 'done_by_user'].includes(st.status) && (
                  <button className="ghost" onClick={() => void act(async () => { await client.confirmXappStep(open.id, st.id); await view(open.id); })}>
                    {st.red_line ? '我已亲手完成' : '确认'}
                  </button>
                )}
              </li>
            ))}
          </ol>
          {open.status === 'running' && (
            <button onClick={() => void act(async () => { await client.stopXappRun(open.id, '本人叫停'); await view(open.id); }, '已叫停')}>一键叫停</button>
          )}
        </div>
      )}
      {notice && <p className="muted" role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
