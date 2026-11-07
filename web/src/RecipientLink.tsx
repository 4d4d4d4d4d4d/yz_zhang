/** SCN-122（356 号 spec）服务对象自己看进度：任务详情里发单人的链接面板 + 免登录的进度页（/r/令牌）。 */
import { RECIPIENT_LINK_DAYS, apiErrorText, recipientLinkLine, recipientLinkUrl, recipientProgressLines,
  type RecipientLinkStatus, type RecipientProgress } from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useApp } from './store';

/** 任务详情：替别人发的单、发单人本人、单子还没结束时出现。令牌只在生成后显示这一次。 */
export function RecipientLinkPanel({ taskId }: { taskId: number }) {
  const { client } = useApp();
  const [status, setStatus] = useState<RecipientLinkStatus | null>(null);
  const [url, setUrl] = useState('');
  const [days, setDays] = useState<number>(7);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    client.recipientLink(taskId).then(setStatus).catch((e) => setError(apiErrorText(e)));
  }, [client, taskId]);
  useEffect(load, [load]);
  const create = () => {
    setError('');
    client.createRecipientLink(taskId, days).then((r) => {
      setStatus(r);
      setUrl(recipientLinkUrl(window.location.origin, r.path));
    }).catch((e) => setError(apiErrorText(e)));
  };
  const revoke = () => {
    setError('');
    client.revokeRecipientLink(taskId).then((r) => { setStatus(r); setUrl(''); }).catch((e) => setError(apiErrorText(e)));
  };
  const active = status?.state === 'active';
  return (
    <div aria-label="服务对象进度链接" className="card" style={{ marginTop: 8 }}>
      <strong>给服务对象一条进度链接</strong>
      <p className="muted">{recipientLinkLine(status)}</p>
      <p className="muted">对方只看得到：谁来、哪天几点、到没到；看不到电话、地址、价钱和照片。</p>
      {url && (
        <p role="status">
          把这条链接发给服务对象（只显示这一次）：<code aria-label="进度链接">{url}</code>
          {typeof navigator !== 'undefined' && navigator.clipboard && (
            <button type="button" className="ghost" onClick={() => void navigator.clipboard.writeText(url)}>复制</button>
          )}
        </p>
      )}
      <label>有效
        <select aria-label="有效天数" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {RECIPIENT_LINK_DAYS.map((d) => <option key={d} value={d}>{d} 天</option>)}
        </select>
      </label>
      <button type="button" onClick={create}>{active ? '重新生成（旧的作废）' : '生成链接'}</button>
      {active && <button type="button" className="ghost" onClick={revoke}>作废链接</button>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** /r/:token —— 服务对象打开的页面：不用登录，字大、只有几行。 */
export function RecipientProgressPage() {
  const { token = '' } = useParams();
  const { client } = useApp();
  const [p, setP] = useState<RecipientProgress | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    client.recipientProgress(token).then(setP).catch((e) => setError(apiErrorText(e)));
  }, [client, token]);
  if (error) return <div className="page"><p className="error" role="alert">{error}</p></div>;
  if (!p) return <div className="page"><p className="muted">正在加载进度…</p></div>;
  const lines = recipientProgressLines(p);
  // APP-091 响应畸形：说清看不了、找谁，不白屏
  if (!lines.length) return <div className="page"><p className="error" role="alert">进度暂时看不了，请稍后再打开，或直接问发单的家人</p></div>;
  return (
    <div className="page" aria-label="服务进度" style={{ fontSize: '1.15em' }}>
      <h1>{p.title}</h1>
      <ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul>
      <p className="muted">这是家人替你发的单。有疑问请直接联系发单的家人；不要把验证码、银行卡号告诉任何人。</p>
    </div>
  );
}
