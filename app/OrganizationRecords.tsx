import { apiErrorText, type PlatformClient, type OrganizationRecordInput, type OrganizationRecordView, type OrganizationRightInput } from '@platform/core';
import { useEffect,useState } from 'react';
import { View,Text,TextInput,Button,Switch } from 'react-native';
const FORMS={project_cooperation:'项目合作',sole_proprietor:'个体／独资经营',limited_company:'有限责任公司',joint_stock_company:'股份有限公司',general_partnership:'普通合伙',limited_partnership:'有限合伙',other:'其他'};
const emptyRight:OrganizationRightInput={holder_name:'',role:'cooperator',subscribed_cents:0,paid_cents:0,interest_description:'',source_document:''};
export default function OrganizationRecords({client,ventureId}:{client:PlatformClient;ventureId:number}){
 const [records,setRecords]=useState<OrganizationRecordView[]>([]);const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [agreed,setAgreed]=useState(false);const [editing,setEditing]=useState(false);
 const [form,setForm]=useState<OrganizationRecordInput>({entity_type:'project_cooperation',jurisdiction:'',registered_name:'',registration_number:'',representative_user_id:0,governance_basis:'',document_references:[],rights:[],acknowledge_record_only:true,acknowledge_member_visibility:true});
 const [right,setRight]=useState<OrganizationRightInput>({...emptyRight});
 useEffect(()=>{let alive=true;client.organizationRecords(ventureId).then(r=>{if(alive)setRecords(r);}).catch(e=>{if(alive)setError(apiErrorText(e));});return()=>{alive=false;};},[client,ventureId]);
 async function submit(){setBusy(true);setError('');try{const r=await client.addOrganizationRecord(ventureId,form);setRecords(rs=>[r,...rs]);setAgreed(false);setEditing(false);}catch(e){setError(apiErrorText(e));}finally{setBusy(false);}}
 return <View style={{gap:8,paddingVertical:12}}>
  <Text>法律主体与权益记录</Text><Text>独立于项目贡献账。此处不办理登记、确权或签约。</Text>
  {!!error&&<Text accessibilityRole="alert">{error}</Text>}
  {records.map(r=><View key={r.id} style={{gap:4}}><Text>第 {r.revision} 版 · {r.registered_name} · 待核验</Text><Text>{r.jurisdiction} · {r.registration_number}</Text><Text>{r.notice}</Text><Text>{r.governance_basis}</Text><Text>{r.document_references.join('；')}</Text>{r.rights.map((x,i)=><Text key={i}>{x.holder_name} · {x.role} · {x.interest_description} · 依据：{x.source_document}</Text>)}</View>)}
  <Button title={editing?'收起草稿':'新增资料版本'} onPress={()=>setEditing(!editing)}/>
  {editing&&<>
   <Text>组织形式：{FORMS[form.entity_type]}</Text>
   <View style={{flexDirection:'row',flexWrap:'wrap'}}>{Object.entries(FORMS).map(([v,l])=><Button key={v} title={l} onPress={()=>setForm({...form,entity_type:v as OrganizationRecordInput['entity_type']})}/>)}</View>
   <TextInput placeholder="司法辖区" accessibilityLabel="司法辖区" value={form.jurisdiction} onChangeText={v=>setForm({...form,jurisdiction:v})}/>
   <TextInput placeholder="登记／合作名称" accessibilityLabel="登记名称" value={form.registered_name} onChangeText={v=>setForm({...form,registered_name:v})}/>
   <TextInput placeholder="登记编号（项目合作可不填）" value={form.registration_number} onChangeText={v=>setForm({...form,registration_number:v})}/>
   <TextInput placeholder="经办责任账户 ID" keyboardType="number-pad" value={form.representative_user_id?String(form.representative_user_id):''} onChangeText={v=>setForm({...form,representative_user_id:Number(v)})}/>
   <TextInput placeholder="章程／合伙协议及决策、签约授权依据" multiline value={form.governance_basis} onChangeText={v=>setForm({...form,governance_basis:v})}/>
   <TextInput placeholder="文件名称及版本，每行一项" multiline value={form.document_references.join('\n')} onChangeText={v=>setForm({...form,document_references:v.split('\n')})}/>
   <Text>录入权益（可多条）</Text>
   <TextInput placeholder="权益人名称" value={right.holder_name} onChangeText={v=>setRight({...right,holder_name:v})}/>
   <Text>角色：{right.role}</Text>
   <View style={{flexDirection:'row',flexWrap:'wrap'}}>{Object.entries({cooperator:'合作人',shareholder:'股东',general_partner:'普通合伙人',limited_partner:'有限合伙人',proprietor:'经营者'}).map(([v,l])=><Button key={v} title={l} onPress={()=>setRight({...right,role:v as OrganizationRightInput['role']})}/>)}</View>
   <Text>认缴金额（分）</Text><TextInput keyboardType="number-pad" value={String(right.subscribed_cents)} onChangeText={v=>setRight({...right,subscribed_cents:Number(v)})}/>
   <Text>实缴金额（分）</Text><TextInput keyboardType="number-pad" value={String(right.paid_cents)} onChangeText={v=>setRight({...right,paid_cents:Number(v)})}/>
   <TextInput placeholder="文件记载的权益及条件" value={right.interest_description} onChangeText={v=>setRight({...right,interest_description:v})}/>
   <TextInput placeholder="依据文件与条款" value={right.source_document} onChangeText={v=>setRight({...right,source_document:v})}/>
   <Button title="加入本版本" disabled={!right.holder_name||!right.interest_description||!right.source_document} onPress={()=>{setForm({...form,rights:[...form.rights,right]});setRight({...emptyRight});}}/>
   {form.rights.map((r,i)=><View key={i}><Text>{r.holder_name} · {r.role}</Text><Button title="移除草稿项" onPress={()=>setForm({...form,rights:form.rights.filter((_,n)=>n!==i)})}/></View>)}
   <Text>我有权向本合作体成员披露资料，并确认这些资料仅为待核验记录，不产生登记或确权效力。</Text>
   <Switch accessibilityLabel="确认记录与披露范围" value={agreed} onValueChange={setAgreed}/>
   <Button title="保存新版本" disabled={busy||!agreed||form.governance_basis.length<10||!form.registered_name||!form.jurisdiction||!form.representative_user_id||!form.document_references.length} onPress={()=>void submit()}/>
  </>}
 </View>;
}
