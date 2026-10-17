import { apiErrorText, fmtYuan, type PlatformClient, type MachineMandateView, type MachineActionView } from '@platform/core';
import { useEffect, useState } from 'react';
import { Button, Switch, Text, TextInput, View } from 'react-native';

export default function MachineMandate({ client, keyId }: { client: PlatformClient; keyId: number }) {
  const [grant, setGrant] = useState<MachineMandateView | null>(null);
  const [actions, setActions] = useState<MachineActionView[]>([]);
  const [ready,setReady] = useState(false);
  const [error,setError] = useState('');
  const [categories,setCategories] = useState('');
  const [per,setPer] = useState('100');
  const [total,setTotal] = useState('500');
  const [days,setDays] = useState('7');
  const [ops,setOps] = useState<Array<'publish'|'apply'|'deliver'>>([]);
  const [agreed,setAgreed] = useState(false);
  const [busy,setBusy] = useState(false);
  useEffect(()=>{
    let alive=true;
    Promise.all([client.machineMandate(keyId),client.machineActions(keyId)]).then(([g,a])=>{
      if(alive){setGrant(g);setActions(a);setReady(true);}
    }).catch(e=>{if(alive)setError(apiErrorText(e));});
    return ()=>{alive=false;};
  },[client,keyId]);
  async function submit(){
    setBusy(true);setError('');
    try { setGrant(await client.grantMachineMandate(keyId,{
      operations:ops,categories:categories.split(/[,，]/).map(x=>x.trim()).filter(Boolean),
      per_task_cents:Math.round(Number(per)*100),total_cents:Math.round(Number(total)*100),
      valid_days:Number(days),acknowledge_responsibility:true,
    })); }catch(e){setError(apiErrorText(e));}finally{setBusy(false);}
  }
  const valid=Number.isFinite(Number(per))&&Number(per)>0&&Number(total)>=Number(per)
    &&Number.isInteger(Number(days))&&Number(days)>=1&&Number(days)<=90;
  return <View style={{gap:8,padding:8}}>
    <Text>机器任务授权</Text>
    {!!error&&<Text accessibilityRole="alert">{error}</Text>}
    {grant?<>
      <Text>责任账户 #{grant.principal_id} · 有效至 {grant.expires_at}</Text>
      <Text>{grant.operations.join(' / ')} · {grant.categories.join(' / ')}</Text>
      <Text>单笔 {fmtYuan(grant.per_task_cents)}，累计已用 {fmtYuan(grant.used_cents)} / {fmtYuan(grant.total_cents)}</Text>
      <Text>累计授权不自动返还；不代表实际扣款。吊销密钥停止调用，轮换后需重新授权。</Text>
      {actions.map(a=><Text key={a.id}>{a.operation} · 任务 #{a.task_id} · {a.created_at}</Text>)}
    </>:ready&&<>
      {(['publish','apply','deliver'] as const).map((op,i)=><View key={op} style={{flexDirection:'row',alignItems:'center'}}>
        <Switch value={ops.includes(op)} onValueChange={on=>setOps(on?[...ops,op]:ops.filter(x=>x!==op))}/>
        <Text>{['发布任务','报名任务','提交交付'][i]}</Text>
      </View>)}
      <TextInput accessibilityLabel="允许类目" placeholder="类目，逗号分隔" value={categories} onChangeText={setCategories}/>
      <Text>单笔额度（元）</Text><TextInput accessibilityLabel="单笔额度" keyboardType="decimal-pad" value={per} onChangeText={setPer}/>
      <Text>累计额度（元）</Text><TextInput accessibilityLabel="累计额度" keyboardType="decimal-pad" value={total} onChangeText={setTotal}/>
      <Text>有效天数 1—90</Text><TextInput accessibilityLabel="有效天数" keyboardType="number-pad" value={days} onChangeText={setDays}/>
      <Text>机器以我的账户操作，交付会进入验收流程；我承担授权责任。本授权不包含签约、付款、验收放款、提现。</Text>
      <Switch accessibilityLabel="确认机器授权责任" value={agreed} onValueChange={setAgreed}/>
      <Button title="确认授权" disabled={busy||!agreed||!valid||!ops.length||!categories.trim()} onPress={()=>void submit()}/>
    </>}
  </View>;
}
