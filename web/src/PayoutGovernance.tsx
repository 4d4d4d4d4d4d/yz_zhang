import { useEffect, useState } from 'react';
import { apiErrorText, fmtYuan, type PlatformClient, type PayoutProposalView } from '@platform/core';
export default function PayoutGovernance({client,ventureId,onChanged}:{client:PlatformClient;ventureId:number;onChanged?:()=>Promise<void>}) {
 const [rows,setRows]=useState<PayoutProposalView[]>([]),[amount,setAmount]=useState(''),[memo,setMemo]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let live=true;client.payoutProposals(ventureId).then(r=>{if(live)setRows(r);}).catch(e=>{if(live)setError(apiErrorText(e));});return()=>{live=false;};},[client,ventureId]);
 async function act(fn:()=>Promise<unknown>){setBusy(true);setError('');try{await fn();await onChanged?.();setRows(await client.payoutProposals(ventureId));}catch(e){setError(apiErrorText(e));}finally{setBusy(false);}}
 return <section className="card"><h3>收益分配共同确认</h3>
 <p>全体当前成员确认同一金额和贡献份额后才能执行。提案有效期 7 天，成员或贡献依据变化需重新发起。仅分配已到账资金；此确认不替代公司或合伙企业法定决议。</p>
 {error&&<p role="alert">{error}</p>}
 <label>金额（元）<input type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label>
 <label>分配说明<input maxLength={200} value={memo} onChange={e=>setMemo(e.target.value)}/></label>
 <button disabled={busy||!(Number(amount)>0)} onClick={()=>act(()=>client.proposePayout(ventureId,Math.round(Number(amount)*100),memo))}>发起并确认提案</button>
 <button disabled={busy} onClick={()=>act(async()=>{})}>刷新提案</button>
 {rows.map(r=><article className="card" key={r.id}><h4>#{r.id} · {fmtYuan(r.amount_cents)} · {r.status==='executed'?'已执行':r.status==='rejected'?'已拒绝':'待确认'}</h4>
 <p>{r.memo||'未填写说明'} · 到期 {r.expires_at}</p>
 <p>确认 {r.approvals.length}/{r.member_ids.length} 人：{r.approvals.map(a=>`#${a.user_id}`).join('、')}</p>
 {r.share_snapshot.map(s=><p key={s.user_id}>接收方 #{s.user_id} · {(s.share_bps/100).toFixed(2)}%</p>)}
 {r.status==='pending'&&<div className="row"><button disabled={busy} onClick={()=>act(()=>client.votePayout(ventureId,r.id,true))}>确认此分配</button>
 <button disabled={busy} onClick={()=>act(()=>client.votePayout(ventureId,r.id,false))}>拒绝／撤回提案</button>
 <button disabled={busy||r.approvals.length!==r.member_ids.length} onClick={()=>act(()=>client.distributeVenture(ventureId,r.amount_cents,r.memo,r.id))}>执行已确认分配</button></div>}
 </article>)}
 </section>;
}
