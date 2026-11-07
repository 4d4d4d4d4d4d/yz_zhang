import { apiErrorText, fmtYuan, formatDateTime, type PlatformClient, type MachineMandateView, type MachineActionView } from '@platform/core';
import { useEffect, useState } from 'react';

export default function MachineMandate({ client, keyId }: { client: PlatformClient; keyId: number }) {
  const [grant, setGrant] = useState<MachineMandateView | null>(null);
  const [actions, setActions] = useState<MachineActionView[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [category, setCategory] = useState('');
  const [per, setPer] = useState('100');
  const [total, setTotal] = useState('500');
  const [days, setDays] = useState('7');
  const [operations, setOperations] = useState<Array<'publish' | 'apply' | 'deliver'>>([]);
  const [consent, setConsent] = useState(false);
  useEffect(() => {
    let alive = true;
    Promise.all([client.machineMandate(keyId), client.machineActions(keyId)]).then(([g, a]) => {
      if (alive) { setGrant(g); setActions(a); setLoaded(true); }
    }).catch(e => { if (alive) setError(apiErrorText(e)); });
    return () => { alive = false; };
  }, [client, keyId]);
  const valid = Number.isFinite(Number(per)) && Number(per) > 0 && Number(total) >= Number(per)
    && Number.isInteger(Number(days)) && Number(days) >= 1 && Number(days) <= 90;
  async function submit() {
    setBusy(true); setError('');
    try {
      setGrant(await client.grantMachineMandate(keyId, {
        operations, categories: category.split(/[,，]/).map(x => x.trim()).filter(Boolean),
        per_task_cents: Math.round(Number(per)*100), total_cents: Math.round(Number(total)*100),
        valid_days: Number(days), acknowledge_responsibility: true,
      }));
    } catch (e) { setError(apiErrorText(e)); } finally { setBusy(false); }
  }
  return <details className="card"><summary>机器任务授权与记录</summary>
    {error && <p role="alert">{error}</p>}
    {grant ? <>
      <p>责任账户 #{grant.principal_id} · 到期 {formatDateTime(grant.expires_at)}</p>
      <p>操作：{grant.operations.join(' / ')} · 类目：{grant.categories.join(' / ')}</p>
      <p>单笔 {fmtYuan(grant.per_task_cents)} · 累计已用 {fmtYuan(grant.used_cents)} / {fmtYuan(grant.total_cents)}</p>
      <p className="muted">额度记录发布预算或承接报价，不代表实际扣款；不会因任务结束自动返还。扩权请重新创建并授权，吊销密钥立即停止后续调用。</p>
      {actions.map(a => <p key={a.id}>{formatDateTime(a.created_at)} · {a.operation} · 任务 #{a.task_id} · 责任账户 #{a.principal_id}</p>)}
      {!actions.length && <p>暂无机器操作。</p>}
    </> : loaded && <>
      <p>此密钥尚未获准写任务。授权后，机器以你的账户发布、报名或交付；交付会进入任务验收流程。</p>
      <div className="row">{(['publish','apply','deliver'] as const).map((op, i) => <label key={op}>
        <input type="checkbox" checked={operations.includes(op)} onChange={e => setOperations(e.target.checked ? [...operations,op] : operations.filter(x=>x!==op))} />
        {['发布任务','报名任务','提交交付'][i]}</label>)}</div>
      <label>允许类目（逗号分隔）<input value={category} onChange={e=>setCategory(e.target.value)} placeholder="软件开发,设计" /></label>
      <div className="row"><label>单笔额度（元）<input type="number" value={per} onChange={e=>setPer(e.target.value)} /></label>
        <label>累计额度（元）<input type="number" value={total} onChange={e=>setTotal(e.target.value)} /></label>
        <label>有效天数（1—90）<input type="number" value={days} onChange={e=>setDays(e.target.value)} /></label></div>
      <label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)} />我确认上述范围，并承担该账户授权机器操作的责任；本授权不包含签约、付款、验收放款或提现。</label>
      <button disabled={busy || !consent || !valid || !category.trim() || !operations.length} onClick={()=>void submit()}>确认授权</button>
    </>}
  </details>;
}
