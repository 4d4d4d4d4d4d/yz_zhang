import { useEffect, useState } from 'react';
import { View,Text,TextInput,Button } from 'react-native';
import { apiErrorText,fmtYuan,type PlatformClient,type PayoutProposalView } from '@platform/core';
export default function PayoutGovernance({client,ventureId}:{client:PlatformClient;ventureId:number}) {
 const [rows,setRows]=useState<PayoutProposalView[]>([]),[amount,setAmount]=useState(''),[memo,setMemo]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let live=true;client.payoutProposals(ventureId).then(r=>{if(live)setRows(r);}).catch(e=>{if(live)setError(apiErrorText(e));});return()=>{live=false;};},[client,ventureId]);
 async function act(fn:()=>Promise<unknown>){setBusy(true);setError('');try{await fn();setRows(await client.payoutProposals(ventureId));}catch(e){setError(apiErrorText(e));}finally{setBusy(false);}}
 return <View style={{gap:8,paddingVertical:12}}><Text>收益分配共同确认</Text>
 <Text>全体成员确认同一金额和贡献份额后执行。7 天有效，成员或贡献依据变化需重提。仅分配已到账资金；不替代法定公司或合伙决议。</Text>
 {!!error&&<Text accessibilityRole="alert">{error}</Text>}
 <TextInput accessibilityLabel="分配金额（元）" placeholder="分配金额（元）" keyboardType="decimal-pad" value={amount} onChangeText={setAmount}/>
 <TextInput accessibilityLabel="分配说明" placeholder="分配说明" maxLength={200} value={memo} onChangeText={setMemo}/>
 <Button title="发起并确认提案" disabled={busy||!(Number(amount)>0)} onPress={()=>act(()=>client.proposePayout(ventureId,Math.round(Number(amount)*100),memo))}/>
 <Button title="刷新提案" disabled={busy} onPress={()=>act(async()=>{})}/>
 {rows.map(r=><View key={r.id} style={{gap:4}}><Text>#{r.id} · {fmtYuan(r.amount_cents)} · {r.status==='executed'?'已执行':r.status==='rejected'?'已拒绝':'待确认'}</Text>
 <Text>{r.memo} · 到期 {r.expires_at} · 确认 {r.approvals.length}/{r.member_ids.length} 人</Text>
 {r.share_snapshot.map(s=><Text key={s.user_id}>接收方 #{s.user_id} · {(s.share_bps/100).toFixed(2)}%</Text>)}
 {r.status==='pending'&&<><Button title="确认此分配" disabled={busy} onPress={()=>act(()=>client.votePayout(ventureId,r.id,true))}/>
 <Button title="拒绝／撤回提案" disabled={busy} onPress={()=>act(()=>client.votePayout(ventureId,r.id,false))}/>
 <Button title="执行已确认分配" disabled={busy||r.approvals.length!==r.member_ids.length} onPress={()=>act(()=>client.distributeVenture(ventureId,r.amount_cents,r.memo,r.id))}/></>}
 </View>)}
 </View>;
}
