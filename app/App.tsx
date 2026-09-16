// App 端（13 号 spec 五 Tab 信息架构）
// 复用 @platform/core SDK，与 Web 同一套后端 API。
// 运行：npm install && npx expo start（后端默认 http://localhost:8000）
import {
  PlatformClient, TASK_STATUS_LABEL, fmtYuan, taskActions,
  type Contract, type Dispute, type DisputeStatement,
  type Me, type Notice, type Task, type Wallet,
} from '@platform/core';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button, FlatList, Platform, RefreshControl, SafeAreaView, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';

/** 取推送令牌。接 expo-notifications 后替换为：
 *    const { data } = await Notifications.getExpoPushTokenAsync();
 *    return data;
 *  现在返回 null —— **如实返回「拿不到」，不编一个假令牌**，
 *  否则服务端会攒一堆永远推不到的死令牌，而通道按量计费。 */
async function getPushToken(): Promise<string | null> {
  return null;
}

const BASE_URL = 'http://localhost:8000'; // 真机调试改为局域网 IP

type Tab = 'tasks' | 'publish' | 'wallet' | 'notices' | 'me';

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<Tab>('tasks');
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  const client = useMemo(
    () => new PlatformClient({ baseUrl: BASE_URL, getToken: () => token }),
    [token],
  );

  useEffect(() => {
    if (token) client.me().then(setMe).catch(() => setToken(null));
    else setMe(null);
  }, [token, client]);

  // NTF-002 登录后注册推送令牌。站内信是「记录」，推送是「触达」——
  // 被诉方的答辩期只有 48 小时，逾期即缺席裁决；用户不主动打开 App，
  // 一条只存在于站内的答辩提醒和没有提醒差别不大。
  //
  // 真机上这里应换成 expo-notifications 取到的 Expo/APNs/FCM 令牌；
  // 取不到令牌**不能**影响登录流程，所以整段都吞掉错误。
  useEffect(() => {
    if (!token) return;
    void (async () => {
      try {
        const deviceToken = await getPushToken();
        if (deviceToken) await client.registerDevice(deviceToken, Platform.OS === 'ios' ? 'ios' : 'android');
      } catch {
        /* 推送注册失败不影响使用 */
      }
    })();
  }, [token, client]);

  if (!token) return <SafeAreaView style={styles.root}><LoginScreen client={client} onToken={setToken} /></SafeAreaView>;

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.body}>
        {activeTask ? (
          <TaskDetailScreen client={client} me={me} task={activeTask}
                            onBack={() => setActiveTask(null)}
                            onChanged={async () => setActiveTask(await client.getTask(activeTask.id))} />
        ) : (
          <>
            {tab === 'tasks' && <TasksScreen client={client} onOpen={setActiveTask} />}
            {tab === 'publish' && <PublishScreen client={client} onDone={() => setTab('tasks')} />}
            {tab === 'wallet' && <WalletScreen client={client} />}
            {tab === 'notices' && <NoticesScreen client={client} />}
            {tab === 'me' && <MeScreen client={client} me={me} refresh={() => client.me().then(setMe)} onLogout={() => setToken(null)} />}
          </>
        )}
      </View>
      {!activeTask && (
        <View style={styles.tabbar}>
          {([['tasks', '任务'], ['publish', '＋发布'], ['wallet', '钱包'], ['notices', '通知'], ['me', '我的']] as [Tab, string][]).map(([key, label]) => (
            <TouchableOpacity key={key} style={styles.tab} onPress={() => setTab(key)}>
              <Text style={[styles.tabText, tab === key && styles.tabActive]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </SafeAreaView>
  );
}

function LoginScreen({ client, onToken }: { client: PlatformClient; onToken: (t: string) => void }) {
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  return (
    <View style={styles.center}>
      <Text style={styles.title}>协作任务平台</Text>
      <TextInput style={styles.input} placeholder="手机号" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      <TextInput style={styles.input} placeholder="密码" value={password} onChangeText={setPassword} secureTextEntry />
      {!!error && <Text style={styles.error}>{error}</Text>}
      <Button title="登录 / 注册" onPress={async () => {
        setError('');
        try {
          const res = await client.login(phone, password).catch(() =>
            client.register(phone, password, `用户${phone.slice(-4)}`));
          onToken(res.token);
        } catch (e) {
          setError(e instanceof Error ? e.message : '网络错误');
        }
      }} />
    </View>
  );
}

function TasksScreen({ client, onOpen }: { client: PlatformClient; onOpen: (t: Task) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      // TODO(V2): expo-location 取定位后传 lat/lng/max_km（GEO-010 地图视图）
      setTasks(await client.listTasks());
    } finally {
      setRefreshing(false);
    }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  return (
    <FlatList
      data={tasks}
      keyExtractor={(t) => String(t.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load()} />}
      ListEmptyComponent={<Text style={styles.muted}>暂无任务，下拉刷新</Text>}
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.cardRow} onPress={() => onOpen(item)}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{item.title}</Text>
            <Text style={styles.mutedLeft}>
              {item.category} · {item.is_remote ? '线上' : `${item.city} ${item.address_hint}`}
            </Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={styles.price}>{fmtYuan(item.budget_cents)}</Text>
            <Text style={styles.badge}>{TASK_STATUS_LABEL[item.status]}</Text>
          </View>
        </TouchableOpacity>
      )}
    />
  );
}

type ApplicationRow = Awaited<ReturnType<PlatformClient['listApplications']>>[number];

function TaskDetailScreen({ client, me, task, onBack, onChanged }: {
  client: PlatformClient; me: Me | null; task: Task; onBack: () => void; onChanged: () => Promise<void>;
}) {
  const [error, setError] = useState('');
  const [contract, setContract] = useState<Contract | null>(null);
  const [apps, setApps] = useState<ApplicationRow[]>([]);
  const meId = me?.id ?? null;

  // 操作可见性由 SDK 单一事实来源决定（03/05 spec 角色×状态矩阵，与 Web 共用）
  const actions = taskActions(task, meId, contract);

  const reload = useCallback(async () => {
    if (['matched', 'in_progress', 'pending_acceptance'].includes(task.status)) {
      client.getContractByTask(task.id).then(setContract).catch(() => setContract(null));
    } else setContract(null);
    if (task.status === 'published' && meId === task.creator_id) {
      client.listApplications(task.id).then(setApps).catch(() => setApps([]));
    }
  }, [client, task, meId]);
  useEffect(() => { void reload(); }, [reload]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try {
      await fn();
      await onChanged();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败');
    }
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }}>
      <TouchableOpacity onPress={onBack}><Text style={{ color: '#2f6fed' }}>← 返回</Text></TouchableOpacity>
      <Text style={styles.title}>{task.title}</Text>
      <Text style={styles.mutedLeft}>
        {task.category} · {TASK_STATUS_LABEL[task.status]} · {fmtYuan(task.budget_cents)}
      </Text>
      {!!task.description && <Text>{task.description}</Text>}
      {!!task.address_exact && <Text style={styles.mutedLeft}>📍 {task.address_exact}</Text>}
      {contract && (
        <View style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>合约 #{contract.id} · {contract.status}</Text>
            <Text style={styles.mutedLeft}>
              金额 {fmtYuan(contract.amount_cents)} · 服务费 {(contract.fee_bps / 100).toFixed(1)}%
              {contract.deposit_cents > 0 ? ` · 保证金 ${fmtYuan(contract.deposit_cents)}` : ''}
            </Text>
            <Text style={styles.mutedLeft}>
              签署：发布方{contract.signed_by_requester ? '✓' : '…'} / 执行方{contract.signed_by_executor ? '✓' : '…'}
            </Text>
          </View>
        </View>
      )}
      {!!error && <Text style={styles.error}>{error}</Text>}

      {actions.includes('apply') && (
        <Button title="报名接单" onPress={() => act(() => client.apply(task.id, '我可以做'))} />
      )}
      {actions.includes('view_applications') && (
        <View style={{ gap: 8 }}>
          <Text style={styles.cardTitle}>报名列表（{apps.length}）</Text>
          {apps.length === 0 && <Text style={styles.mutedLeft}>暂无报名，可稍后下拉刷新</Text>}
          {apps.map((a) => (
            <View key={a.id} style={styles.cardRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{a.nickname} · 信用 {a.credit_score}</Text>
                <Text style={styles.mutedLeft}>报价 {fmtYuan(a.bid_cents)} · {a.message || '（无留言）'}</Text>
              </View>
              {a.status === 'pending' && (
                <Button title="选TA成交" onPress={() => act(() => client.acceptApplication(a.id))} />
              )}
            </View>
          ))}
        </View>
      )}
      {actions.includes('sign') && contract && (
        <Button title="签署合约" onPress={() => act(() => client.signContract(contract.id))} />
      )}
      {actions.includes('wait_counterparty') && (
        <Text style={styles.muted}>已签署，等待对方签字…</Text>
      )}
      {actions.includes('fund') && contract && (
        <Button title={`托管资金 ${fmtYuan(contract.amount_cents)}`}
                onPress={() => act(() => client.fundContract(contract.id))} />
      )}
      {actions.includes('deliver') && (
        <Button title="提交验收" onPress={() => act(() => client.deliver(task.id))} />
      )}
      {actions.includes('accept_delivery') && (
        <Button title="验收通过（放款）" onPress={() => act(() => client.acceptDelivery(task.id))} />
      )}
      {actions.includes('reject_delivery') && (
        <Button title="驳回返工" onPress={() => act(() => client.rejectDelivery(task.id, '不符合要求，请修改'))} />
      )}
      {actions.includes('open_dispute') && (
        <Button title="发起纠纷（冻结资金）" color="#dc2626"
                onPress={() => act(() => client.openDispute(task.id, '双方对交付结果有分歧，申请平台介入'))} />
      )}
      {actions.includes('cancel') && (
        <Button title="取消任务" color="#6b7280" onPress={() => act(() => client.cancelTask(task.id))} />
      )}
      {actions.includes('review') && (
        <Button title="给对方好评（5星）" onPress={() => act(() => client.review(task.id, 5))} />
      )}
      {/* DSPR-010 纠纷区块。V61 只补了 Web，而线下服务的执行方主要在 App 上——
          最可能坐在被告席上的那群人，恰恰是唯一仍然开不了口的那群人。 */}
      <DisputeBlock client={client} taskId={task.id} meId={me ? me.id : null} />
    </ScrollView>
  );
}

function DisputeBlock({ client, taskId, meId }: {
  client: PlatformClient; taskId: number; meId: number | null;
}) {
  const [dispute, setDispute] = useState<Dispute | null>(null);
  const [statements, setStatements] = useState<DisputeStatement[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      // DSPR-012 被诉方只知道任务 id——他收到的通知就只说「任务 #N 有纠纷」
      const d = await client.disputeByTask(taskId);
      setDispute(d);
      setStatements(await client.disputeStatements(d.id));
    } catch {
      setDispute(null);
    }
  }, [client, taskId]);

  useEffect(() => { void load(); }, [load]);
  if (!dispute) return null;

  const closed = dispute.status === 'resolved' || dispute.status === 'settled';
  const iAmRespondent = meId !== null && dispute.respondent_id === meId;
  // 截止时间由服务端给（DSPC-011）：答辩期长度是服务端配置，客户端不该自己算
  const hoursLeft = Math.floor(
    (new Date(dispute.response_deadline + 'Z').getTime() - Date.now()) / 3_600_000,
  );

  const run = async (fn: () => Promise<unknown>) => {
    setError('');
    try { await fn(); await load(); } catch (e) { setError((e as Error).message || '操作失败'); }
  };

  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.cardTitle}>纠纷 #{dispute.id} · {DISPUTE_STATUS_LABEL[dispute.status] ?? dispute.status}</Text>
      <Text style={styles.mutedLeft}>事由：{dispute.reason}</Text>
      {!closed && (
        <Text style={styles.mutedLeft}>
          {hoursLeft > 0 ? `答辩截止还有约 ${hoursLeft} 小时` : '答辩期已过，平台可缺席作出处理决定'}
        </Text>
      )}
      {/* DSPR-011 被诉方没说话时必须说清楚代价 */}
      {iAmRespondent && !dispute.respondent_spoke && !closed && (
        <Text style={styles.error}>
          你尚未答辩。逾期未答辩，平台可仅凭对方的陈述作出处理决定。
        </Text>
      )}
      {statements.length === 0 && <Text style={styles.mutedLeft}>还没有任何陈述。</Text>}
      {statements.map((s) => (
        <View key={s.id} style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{s.role === 'opener' ? '发起方' : '被诉方'}</Text>
            <Text style={styles.mutedLeft}>{s.content}</Text>
          </View>
        </View>
      ))}
      {/* DSPR-013 结案后收起：服务端本来就会 409，但不该让人在手机上打完一段话才被拒 */}
      {!closed && (
        <>
          <TextInput style={styles.input} placeholder="提交答辩与举证说明（至少 5 个字）"
                     value={draft} onChangeText={setDraft} multiline />
          <Button title="提交答辩" onPress={() => run(async () => {
            await client.addDisputeStatement(dispute.id, draft.trim());
            setDraft('');
          })} />
          {dispute.settlement_proposal && dispute.settlement_proposal.proposed_by !== meId && (
            <Button title={`接受和解（执行方 ${dispute.settlement_proposal.executor_share_bps / 100}%）`}
                    onPress={() => run(() => client.acceptSettlement(dispute.id))} />
          )}
        </>
      )}
      {dispute.status === 'resolved' && (
        <>
          <Text style={styles.mutedLeft}>
            处理决定：执行方分得 {(dispute.verdict_executor_share_bps ?? 0) / 100}%
            {dispute.verdict_reason ? `（${dispute.verdict_reason}）` : ''}
          </Text>
          {/* appealable 由服务端算，与端点准入是同一个判断（DSPC-030） */}
          {dispute.appealable && (
            <Button title="申诉复核（每案一次）" color="#6b7280"
                    onPress={() => run(() => client.appealDispute(dispute.id))} />
          )}
        </>
      )}
      {!!error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const DISPUTE_STATUS_LABEL: Record<string, string> = {
  open: '处理中',
  appealed: '申诉复核中',
  resolved: '平台已作出处理决定',
  settled: '双方已和解',
};

function PublishScreen({ client, onDone }: { client: PlatformClient; onDone: () => void }) {
  const [title, setTitle] = useState('');
  const [budget, setBudget] = useState('200');
  const [error, setError] = useState('');
  return (
    <View style={styles.center}>
      <Text style={styles.title}>发布任务</Text>
      <TextInput style={styles.input} placeholder="标题（如：帮忙取快递）" value={title} onChangeText={setTitle} />
      <TextInput style={styles.input} placeholder="预算（元）" value={budget} onChangeText={setBudget} keyboardType="numeric" />
      {!!error && <Text style={styles.error}>{error}</Text>}
      <Button title="发布（线上任务）" onPress={async () => {
        setError('');
        try {
          await client.createTask({
            title, category: '跑腿', task_type: 'event',
            budget_cents: Math.round(parseFloat(budget || '0') * 100),
            is_remote: true, publish_now: true,
          });
          onDone();
        } catch (e) {
          setError(e instanceof Error ? e.message : '发布失败');
        }
      }} />
    </View>
  );
}

function WalletScreen({ client }: { client: PlatformClient }) {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const load = useCallback(async () => setWallet(await client.wallet()), [client]);
  useEffect(() => { void load(); }, [load]);
  return (
    <View style={{ gap: 12 }}>
      <Text style={styles.title}>我的钱包</Text>
      {wallet && (
        <View style={styles.cardRow}>
          <View style={{ flex: 1 }}><Text style={styles.mutedLeft}>可用</Text><Text style={styles.cardTitle}>{fmtYuan(wallet.available_cents)}</Text></View>
          <View style={{ flex: 1 }}><Text style={styles.mutedLeft}>托管中</Text><Text style={styles.cardTitle}>{fmtYuan(wallet.escrow_cents)}</Text></View>
        </View>
      )}
      <Button title="充值 ¥100（模拟）" onPress={async () => { await client.topup(10000); await load(); }} />
    </View>
  );
}

function NoticesScreen({ client }: { client: PlatformClient }) {
  const [notes, setNotes] = useState<Notice[]>([]);
  useEffect(() => { void client.notifications().then(setNotes); }, [client]);
  return (
    <FlatList
      data={notes}
      keyExtractor={(n) => String(n.id)}
      ListEmptyComponent={<Text style={styles.muted}>暂无通知</Text>}
      renderItem={({ item }) => (
        <View style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>{item.title}</Text>
            <Text style={styles.mutedLeft}>{item.body}</Text>
          </View>
        </View>
      )}
    />
  );
}

function MeScreen({ client, me, refresh, onLogout }: {
  client: PlatformClient; me: Me | null; refresh: () => void; onLogout: () => void;
}) {
  if (!me) return <Text style={styles.muted}>加载中…</Text>;
  return (
    <View style={styles.center}>
      <Text style={styles.title}>{me.nickname}</Text>
      <Text style={styles.muted}>
        信用分 {me.credit_score} · 已完成 {me.tasks_completed} 单 · {me.is_verified ? '已实名' : '未实名'}
      </Text>
      {!me.is_verified && (
        <Button title="一键实名认证（模拟）" onPress={async () => {
          await client.verifyIdentity('测试用户', '110101199001011234');
          refresh();
        }} />
      )}
      <Button title="退出登录" onPress={onLogout} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#f5f6f8' },
  body: { flex: 1, padding: 12 },
  center: { flex: 1, justifyContent: 'center', padding: 24, gap: 12 },
  title: { fontSize: 22, fontWeight: '700', color: '#2f6fed', textAlign: 'center' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  cardRow: { flexDirection: 'row', backgroundColor: '#fff', borderRadius: 10, padding: 14, marginBottom: 10 },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  price: { color: '#dc2626', fontWeight: '700' },
  badge: { color: '#2f6fed', fontSize: 12 },
  muted: { color: '#6b7280', fontSize: 13, textAlign: 'center', marginTop: 8 },
  mutedLeft: { color: '#6b7280', fontSize: 13 },
  error: { color: '#dc2626' },
  tabbar: { flexDirection: 'row', backgroundColor: '#fff', borderTopWidth: 1, borderColor: '#e5e7eb' },
  tab: { flex: 1, padding: 14, alignItems: 'center' },
  tabText: { color: '#6b7280' },
  tabActive: { color: '#2f6fed', fontWeight: '700' },
});
