// APP-079 找合作者——App 这一端（110 号 spec）。
//
// 用户复述的六条愿景里，「AI 协助找合作者」是最后一条只有网页有的：
// 发布方在网页任务详情能看到 AI 推荐人选并邀约、能邀请平台 AI 助理并看它跑出了什么，
// 而 App 的任务详情一个入口都没有——发布方主要在手机上，等于这条愿景在他手里不存在。
//
// 两块都照网页的规矩来，规则不在这里另写一份：
// - 推荐人选给**理由**（技能、信用、评分），不是只给一个分数；邀约是请他来报名，不是替他接单。
// - 助理不可用时**原样显示服务端算好的理由**（CLI-064）；邀请由发布方主动发，平台不自动派单；
//   置信度写明是助理**自报**的（AGT-013）；交付被平台判据拦下时给出人工核验入口。
import {
  apiErrorText, fmtYuan, type AgentProfileView, type AgentRunView, type EligibleAgent,
  type PlatformClient, type Recommendation, type Task,
} from '@platform/core';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

/** MATCH-001/002 AI 推荐人选：发布方、已发布的任务。 */
export function RecommendationsBlock({ client, task }: { client: PlatformClient; task: Task }) {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [invited, setInvited] = useState<Record<number, boolean>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    client.recommendations(task.id)
      .then((r) => setRecs(Array.isArray(r) ? r : []))
      .catch(() => setRecs([]));
  }, [client, task.id]);

  if (recs.length === 0) return null;
  return (
    <View style={s.card}>
      <Text style={s.title}>AI 推荐人选</Text>
      <Text style={s.muted}>邀约是请对方来报名，最后选谁、签不签仍由你定。</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {recs.slice(0, 5).map((r) => (
        <View key={r.user_id} style={s.item}>
          <Text style={s.name}>{r.nickname}  <Text style={s.badge}>匹配 {(r.score * 100).toFixed(0)}%</Text></Text>
          {/* 只给分数不给理由，发布方没法判断这个推荐靠不靠谱 */}
          <Text style={s.muted}>{r.reasons.join(' · ')}</Text>
          {invited[r.user_id] ? (
            <Text style={s.ok}>已邀约</Text>
          ) : (
            <TouchableOpacity style={s.ghost} onPress={async () => {
              setError('');
              try {
                await client.inviteToTask(task.id, r.user_id, '诚邀接单');
                setInvited((m) => ({ ...m, [r.user_id]: true }));
              } catch (e) {
                setError(apiErrorText(e));
              }
            }}>
              <Text>邀约 {r.nickname}</Text>
            </TouchableOpacity>
          )}
        </View>
      ))}
    </View>
  );
}

const RUN_LABEL: Record<string, string> = {
  running: '执行中', succeeded: '已完成', escalated: '待人工核验', failed: '失败',
};

/** CLI-063 AI 助理（发布方视角）：邀请、执行、交付闸门与人工核验入口。 */
export function AgentBlock({ client, task, onChanged }: {
  client: PlatformClient; task: Task; onChanged: () => void;
}) {
  const [agents, setAgents] = useState<AgentProfileView[]>([]);
  const [candidates, setCandidates] = useState<EligibleAgent[]>([]);
  const [runs, setRuns] = useState<AgentRunView[]>([]);
  const [deliveryBlock, setDeliveryBlock] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    const a = await client.agents().catch(() => []);
    setAgents(Array.isArray(a) ? a : []);
    if (task.status === 'published') {
      const c = await client.eligibleAgents(task.id).catch(() => []);
      setCandidates(Array.isArray(c) ? c : []);
    }
    if (task.executor_id) {
      const r = await client.agentRuns(task.id).catch(() => null);
      if (r && Array.isArray(r.runs)) { setRuns(r.runs); setDeliveryBlock(r.delivery_block ?? ''); }
    }
  }, [client, task.id, task.status, task.executor_id]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done = '') {
    setError(''); setNotice(''); setBusy(true);
    try {
      await fn();
      if (done) setNotice(done);
      await load();
      onChanged();
    } catch (e) {
      setError(apiErrorText(e));
    } finally {
      setBusy(false);
    }
  }

  const executorIsAgent = task.executor_id != null && agents.some((a) => a.user_id === task.executor_id);
  // AGT-010 需到场完成的任务不能由助理执行：先说清楚，比让人点了再被拒好——所以干脆不出现
  if (!task.is_remote && !executorIsAgent) return null;
  if (!['published', 'matched', 'in_progress', 'pending_acceptance'].includes(task.status)) return null;
  if (task.status !== 'published' && !executorIsAgent) return null;

  return (
    <View style={s.card}>
      <Text style={s.title}>AI 助理</Text>
      {!!error && <Text style={s.error}>{error}</Text>}
      {!!notice && <Text style={s.ok}>{notice}</Text>}

      {task.status === 'published' && (
        <>
          <Text style={s.muted}>
            由你主动邀请，平台不会自动派单。助理走与人一样的报名、选人、签约、托管流程。
          </Text>
          {candidates.length === 0 && <Text style={s.muted}>平台暂无在售助理。</Text>}
          {candidates.map((a) => (
            <View key={a.user_id} style={s.item}>
              <Text style={s.name}>{a.name}</Text>
              <Text style={s.muted}>{a.domains.join(' / ')} · 承接上限 {fmtYuan(a.max_task_budget_cents)}</Text>
              {/* CLI-064 不可用时显示服务端给的理由，不是把它吞掉 */}
              {!a.eligible && <Text style={s.error} testID="agent-reason">{a.reason}</Text>}
              <TouchableOpacity style={[s.ghost, (!a.eligible || busy) && s.disabled]} disabled={!a.eligible || busy}
                                accessibilityState={{ disabled: !a.eligible || busy }}
                                onPress={() => act(() => client.inviteAgent(task.id, a.user_id), `已邀请 ${a.name}`)}>
                <Text>邀请 {a.name}</Text>
              </TouchableOpacity>
            </View>
          ))}
        </>
      )}

      {executorIsAgent && (
        <>
          <Text style={s.muted}>本任务由平台 AI 助理执行，平台是本任务履约的责任主体（合同里已写明）。</Text>
          {task.status === 'in_progress' && (
            <TouchableOpacity style={[s.primary, busy && s.disabled]} disabled={busy}
                              onPress={() => act(() => client.runAgent(task.id))}>
              <Text style={s.primaryText}>{runs.length === 0 ? '开始执行' : '重新执行'}</Text>
            </TouchableOpacity>
          )}
          {runs.length === 0 && <Text style={s.muted}>尚未执行。</Text>}
          {runs.map((r) => (
            <View key={r.id} style={s.item}>
              {/* AGT-013 这是**自报**的置信度，不是平台的判断 */}
              <Text style={s.name}>{RUN_LABEL[r.status] ?? r.status} · 助理自报置信度 {(r.confidence_bps / 100).toFixed(1)}%</Text>
              {!!r.error && <Text style={s.error}>{r.error}</Text>}
              {!!r.output && <Text selectable>{r.output}</Text>}
              {(r.criteria_results ?? []).map((c, i) => (
                <Text key={i} style={s.muted}>{c.passed ? '✓' : '✗'} {c.text}{c.kind === 'manual' ? '（需人工判）' : ''}</Text>
              ))}
              {r.moderation_status === 'review' && <Text style={s.muted}>内容审核未给出明确结论，已转人工核验。</Text>}
            </View>
          ))}
          {!!deliveryBlock && (
            <>
              <Text style={s.error} testID="delivery-block">{deliveryBlock}</Text>
              <TouchableOpacity style={[s.ghost, busy && s.disabled]} disabled={busy}
                                onPress={() => act(() => client.requestVerification(task.id), '核验单已提交')}>
                <Text>申请人工核验</Text>
              </TouchableOpacity>
              {/* VER-002 谁付费不是细节 */}
              <Text style={s.muted}>置信度不足导致的升级由平台承担核验费；你主动核验一个已成功的结果，费用由你承担。</Text>
            </>
          )}
        </>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 14, gap: 6, borderWidth: 1, borderColor: '#dce5de' },
  item: { gap: 4, paddingVertical: 6, borderTopWidth: 1, borderTopColor: '#eef2ef' },
  title: { fontSize: 15, fontWeight: '600' },
  name: { fontSize: 15, fontWeight: '500' },
  muted: { color: '#6b7280', fontSize: 13 },
  error: { color: '#b91c1c', fontSize: 13 },
  ok: { color: '#166534', fontSize: 13 },
  badge: { color: '#166534', fontSize: 12 },
  ghost: { borderRadius: 10, padding: 10, borderWidth: 1, borderColor: '#cbd5e1', alignItems: 'center' },
  primary: { backgroundColor: '#275c52', borderRadius: 10, padding: 12, alignItems: 'center' },
  primaryText: { color: '#fff', fontWeight: '600' },
  disabled: { opacity: 0.4 },
});
