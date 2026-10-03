import { apiErrorText, fmtYuan, type PlatformClient, type OrganizationRecordInput, type OrganizationRecordView, type OrganizationRightInput } from '@platform/core';
import { useEffect, useState } from 'react';
const FORMS = { project_cooperation:'项目合作',sole_proprietor:'个体／独资经营',limited_company:'有限责任公司',joint_stock_company:'股份有限公司',general_partnership:'普通合伙',limited_partnership:'有限合伙',other:'其他组织形式' };
const emptyRight:OrganizationRightInput={holder_name:'',role:'cooperator',subscribed_cents:0,paid_cents:0,interest_description:'',source_document:''};
export default function OrganizationRecords({client,ventureId}:{client:PlatformClient;ventureId:number}){
 const [records,setRecords]=useState<OrganizationRecordView[]>([]);
 const [error,setError]=useState(''); const [busy,setBusy]=useState(false); const [consent,setConsent]=useState(false);
 const [form,setForm]=useState<OrganizationRecordInput>({entity_type:'project_cooperation',jurisdiction:'',registered_name:'',registration_number:'',representative_user_id:0,governance_basis:'',document_references:[],rights:[],acknowledge_record_only:true,acknowledge_member_visibility:true});
 const [right,setRight]=useState<OrganizationRightInput>({...emptyRight});
 useEffect(()=>{let alive=true;client.organizationRecords(ventureId).then(r=>{if(alive)setRecords(r);}).catch(e=>{if(alive)setError(apiErrorText(e));});return()=>{alive=false;};},[client,ventureId]);
 async function submit(){setBusy(true);setError('');try{const r=await client.addOrganizationRecord(ventureId,form);setRecords(rs=>[r,...rs]);setConsent(false);}catch(e){setError(apiErrorText(e));}finally{setBusy(false);}}
 return <details className="card"><summary>法律主体与权益文件记录</summary>
  <p>项目贡献、合同收益、公司股权及合伙权益分别记载。提交不会自动登记主体、签约、确权或调整贡献份额。</p>
  {error&&<p role="alert">{error}</p>}
  {records.map(r=><details key={r.id}><summary>第 {r.revision} 版 · {r.registered_name} · 尚未核验</summary>
    <p>{r.notice}</p><p>{r.jurisdiction} · 登记编号 {r.registration_number||'未声明登记'} · 经办责任账户 #{r.representative_user_id}</p>
    <p>{r.governance_basis}</p><p>文件依据：{r.document_references.join('；')}</p>
    {r.rights.map((x,i)=><p key={i}>{x.holder_name} · {x.role} · 认缴 {fmtYuan(x.subscribed_cents)} / 实缴 {fmtYuan(x.paid_cents)} · {x.interest_description} · 依据 {x.source_document}</p>)}
    <p className="muted">记录摘要 {r.record_hash}</p></details>)}
  <h4>新增版本（保留全部历史）</h4>
  <label>组织形式<select value={form.entity_type} onChange={e=>setForm({...form,entity_type:e.target.value as OrganizationRecordInput['entity_type']})}>{Object.entries(FORMS).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
  <label>司法辖区<input value={form.jurisdiction} onChange={e=>setForm({...form,jurisdiction:e.target.value})} placeholder="例如：中国大陆／上海"/></label>
  <label>登记名称／合作名称<input value={form.registered_name} onChange={e=>setForm({...form,registered_name:e.target.value})}/></label>
  <label>登记编号<input value={form.registration_number} onChange={e=>setForm({...form,registration_number:e.target.value})}/></label>
  <label>经办责任人账户 ID<input type="number" value={form.representative_user_id||''} onChange={e=>setForm({...form,representative_user_id:Number(e.target.value)})}/></label>
  <label>章程／合伙协议与授权规则<textarea value={form.governance_basis} onChange={e=>setForm({...form,governance_basis:e.target.value})} placeholder="说明决策、表决、执行事务与签约授权依据，不使用平台积分替代法定权益"/></label>
  <label>外部文件名称与版本（每行一项）<textarea value={form.document_references.join('\n')} onChange={e=>setForm({...form,document_references:e.target.value.split('\n')})}/></label>
  <details><summary>录入文件记载的权益（可多条）</summary>
    <input aria-label="权益人名称" placeholder="自然人或主体名称" value={right.holder_name} onChange={e=>setRight({...right,holder_name:e.target.value})}/>
    <select aria-label="权益角色" value={right.role} onChange={e=>setRight({...right,role:e.target.value as OrganizationRightInput['role']})}>{Object.entries({cooperator:'项目合作人',shareholder:'股东',general_partner:'普通合伙人',limited_partner:'有限合伙人',proprietor:'经营者'}).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>
    <label>认缴金额（分）<input type="number" value={right.subscribed_cents} onChange={e=>setRight({...right,subscribed_cents:Number(e.target.value)})}/></label>
    <label>实缴金额（分）<input type="number" value={right.paid_cents} onChange={e=>setRight({...right,paid_cents:Number(e.target.value)})}/></label>
    <input aria-label="权益说明" placeholder="文件记载的权益、比例及条件" value={right.interest_description} onChange={e=>setRight({...right,interest_description:e.target.value})}/>
    <input aria-label="权益文件依据" placeholder="依据文件与条款" value={right.source_document} onChange={e=>setRight({...right,source_document:e.target.value})}/>
    <button disabled={!right.holder_name||!right.interest_description||!right.source_document} onClick={()=>{setForm({...form,rights:[...form.rights,right]});setRight({...emptyRight});}}>加入本版本</button>
    {form.rights.map((x,i)=><p key={i}>{x.holder_name} · {x.role} <button className="ghost" onClick={()=>setForm({...form,rights:form.rights.filter((_,n)=>n!==i)})}>移除草稿项</button></p>)}
  </details>
  <label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>我有权向本合作体成员披露这些资料，并确认它们仅为待核验文件记录，不产生登记或确权效力。</label>
  <button disabled={busy||!consent||form.governance_basis.length<10||!form.jurisdiction||!form.registered_name||!form.representative_user_id||!form.document_references.length} onClick={()=>void submit()}>保存新版本</button>
 </details>;
}
