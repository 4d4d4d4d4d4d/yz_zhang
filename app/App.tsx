// App 端（13 号 spec 五 Tab 信息架构）
// 复用 @platform/core SDK，与 Web 同一套后端 API。
// 运行：npm install && npx expo start（后端默认 http://localhost:8000）
import { DEPOSIT_STATUS_LABEL, IP_ASSIGNMENT_LABEL, PlatformClient, TASK_STATUS_LABEL, apiErrorText, fmtYuan, ledgerKindLabel, millisUntil, taskActions, type Contract, type Dispute, type DisputeStatement, type IpAssignment, type ChangeOrderView, type LedgerRow, type Me, type Notice, type PayoutAccountView, type Task, type Wallet } from '@platform/core';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { DiscoverScreen } from './Discover';
import { SUB_SCREEN_LABEL, SubScreenHost, type SubScreen } from './TeamCoopDev';
import { VideoFeedScreen } from './VideoFeed';
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

type Tab = 'tasks' | 'discover' | 'video' | 'publish' | 'wallet' | 'notices' | 'me';

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
            {/* APP-002 发现流：视差滚动，尊重系统「减弱动态效果」开关 */}
            {tab === 'discover' && <DiscoverScreen client={client} baseUrl={BASE_URL} />}
            {/* CNT-014 沉浸流：任何时刻有且只有一个 <Video> 在播 */}
            {tab === 'video' && <VideoFeedScreen client={client} baseUrl={BASE_URL} />}
            {tab === 'publish' && <PublishScreen client={client} onDone={() => setTab('tasks')} />}
            {tab === 'wallet' && <WalletScreen client={client} />}
            {tab === 'notices' && <NoticesScreen client={client} />}
            {tab === 'me' && <MeScreen client={client} me={me} refresh={() => client.me().then(setMe)} onLogout={() => setToken(null)} />}
          </>
        )}
      </View>
      {!activeTask && (
        <View style={styles.tabbar}>
          {([['tasks', '任务'], ['discover', '发现'], ['video', '视频'], ['publish', '＋发布'], ['wallet', '钱包'], ['notices', '通知'], ['me', '我的']] as [Tab, string][]).map(([key, label]) => (
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
      <ReportAndBlock client={client} task={task} meId={meId} />
      {contract && (
        <View style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>合约 #{contract.id} · {contract.status}</Text>
            <Text style={styles.mutedLeft}>
              金额 {fmtYuan(contract.amount_cents)} · 服务费 {(contract.fee_bps / 100).toFixed(1)}%
              {contract.deposit_cents > 0
                ? ` · 保证金 ${fmtYuan(contract.deposit_cents)}（${DEPOSIT_STATUS_LABEL[contract.deposit_status] ?? contract.deposit_status}）`
                : ''}
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
      {/* APP-066 人工核验入口。V90 给 AI 交付的待验收通知写了这句话：
          「如需人工把关，可在任务详情页申请人工核验」——而 requestVerification
          此前只在 web/src/AgentPanel.tsx 被调用过一次，**App 的任务详情页
          没有这个入口**。必达通知里指的路，必须在收到它的端上走得通。 */}
      {actions.includes('accept_delivery') && (
        <Button title="申请人工核验（平台付费）" color="#6b7280"
                onPress={() => act(() => client.requestVerification(task.id))} />
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
      {/* SC-007 变更单。「加了两个房间，多给你 100」——改造前这件事
          在产品里没有任何地方可以落地，双方只剩取消或纠纷两条对抗路径。 */}
      {contract && ['signed', 'funded'].includes(contract.status) && !contract.frozen && (
        <ChangeOrderBlock client={client} contract={contract} onChanged={reload} />
      )}
      {/* GEO-022/023 安全区块。求助与行程分享**在手机上才有意义**——
          上门、夜间、独自面对陌生人的是 App 上的这群人。 */}
      <SafetyBlock client={client} task={task} meId={meId} />
      {/* DSPR-010 纠纷区块。V61 只补了 Web，而线下服务的执行方主要在 App 上——
          最可能坐在被告席上的那群人，恰恰是唯一仍然开不了口的那群人。 */}
      <DisputeBlock client={client} taskId={task.id} meId={me ? me.id : null} />
    </ScrollView>
  );
}

/** 取当前坐标。拿不到定位时返回 0,0 交给服务端去判——
 *  **不因为定位失败就把人挡在门外**：求助与打卡都宁可被服务端拒，
 *  也不要在客户端先卡住。 */
async function currentPosition(): Promise<{ lat: number; lng: number }> {
  try {
    const Location = await import('expo-location');
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== 'granted') return { lat: 0, lng: 0 };
    const pos = await Location.getCurrentPositionAsync({});
    return { lat: pos.coords.latitude, lng: pos.coords.longitude };
  } catch {
    return { lat: 0, lng: 0 };
  }
}

/** SC-007 变更单。服务端连「列出变更单」的接口都没有（本批补上）——
 *  提案建得出来而对方拿不到 order_id，**有按钮也点不了**。 */
export function ChangeOrderBlock({ client, contract, onChanged }: {
  client: PlatformClient; contract: Contract; onChanged: () => Promise<void>;
}) {
  const [rows, setRows] = useState<ChangeOrderView[]>([]);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setRows(await client.changeOrders(contract.id).catch(() => []));
  }, [client, contract.id]);
  useEffect(() => { void load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setError('');
    try { await fn(); await load(); await onChanged(); }
    catch (e) { setError(apiErrorText(e)); }
  }

  const pending = rows.find((r) => r.status === 'pending');

  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.cardTitle}>变更单</Text>
      {rows.length === 0 && (
        <Text style={styles.mutedLeft}>没有变更单。范围或价格有调整时，从这里提出。</Text>
      )}
      {rows.map((r) => (
        <View key={r.id} style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>改为 {fmtYuan(r.new_amount_cents)}</Text>
            <Text style={styles.mutedLeft}>{r.status}{r.reason ? ` · ${r.reason}` : ''}</Text>
          </View>
          {/* 读服务端的 can_decide：提案人自己不能接受，客户端不重判 */}
          {r.can_decide && (
            <View style={{ gap: 6 }}>
              <Button title="接受" onPress={() => act(() => client.acceptChange(contract.id, r.id))} />
              <Button title="拒绝" color="#dc2626"
                      onPress={() => act(() => client.rejectChangeOrder(contract.id, r.id))} />
            </View>
          )}
        </View>
      ))}
      {!pending && (
        <>
          <TextInput style={styles.input} keyboardType="numeric" value={amount}
                     onChangeText={setAmount} placeholder="新金额（元）" />
          <TextInput style={styles.input} value={reason} onChangeText={setReason}
                     placeholder="事由（对方会看到）" />
          <Button title="提出变更" onPress={() => act(async () => {
            await client.proposeChange(contract.id, Math.round(parseFloat(amount || '0') * 100), reason);
            setAmount(''); setReason('');
          })} />
        </>
      )}
      <Text style={styles.mutedLeft}>
        当前金额 {fmtYuan(contract.amount_cents)}；对方接受后差额自动补托管或退回。
      </Text>
      {!!error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

/** GEO-023 一键求助 / GEO-022 行程分享。
 *
 * 服务端两条都早就实现了，`sos` 的注释甚至为了让按钮**不被合规弹窗挡住**
 * 特意去查了 PIPL 第十三条第(四)项——而那个按钮在任何一个端上都不存在。
 *
 * 只在**进行中**的任务上出现：任务还没开始、或者已经结束，
 * 摆一个求助按钮只会稀释它。
 */
export function SafetyBlock({ client, task, meId }: {
  client: PlatformClient; task: Task; meId: number | null;
}) {
  const [guidance, setGuidance] = useState('');
  const [error, setError] = useState('');
  const [shared, setShared] = useState<boolean | null>(null);
  const [checkin, setCheckin] = useState('');

  const live = ['in_progress', 'pending_acceptance'].includes(task.status);
  const isParty = meId === task.creator_id || meId === task.executor_id;
  if (!live || !isParty || task.is_remote) return null;

  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.cardTitle}>安全</Text>
      <Button title="🆘 一键求助" color="#dc2626" onPress={async () => {
        setError('');
        try {
          // 真机上这里换成 expo-location 的当前坐标；拿不到定位**也要照发**——
          // 求助不能因为定位失败而发不出去
          const pos = await currentPosition();
          const r = await client.sos(task.id, pos.lat, pos.lng);
          // 服务端给的指引原样显示：这一刻唯一对他有用的就是这句话
          setGuidance(r.guidance);
        } catch (e) {
          setError(apiErrorText(e));
        }
      }} />
      {!!guidance && <Text style={styles.error}>{guidance}</Text>}
      {meId === task.executor_id && (
        <Button title={shared ? '关闭行程分享' : '开启行程分享（让发布方看到我的轨迹）'}
                onPress={async () => {
                  setError('');
                  try {
                    const r = await client.setTripShare(task.id, !shared);
                    setShared(r.trip_share_enabled);
                  } catch (e) {
                    setError(apiErrorText(e));
                  }
                }} />
      )}
      {!!error && <Text style={styles.error}>{error}</Text>}
      {/* GEO-021 到场打卡。服务端带距离校验（探针实测 4205 米被拒），
          而此前**没有任何端能打卡**——到场证据链从来没有产生过一条。
          只做 App：浏览器里的定位在上门场景里没有意义。 */}
      {meId === task.executor_id && (
        <Button title="到场打卡" onPress={async () => {
          setError(''); setCheckin('');
          try {
            const pos = await currentPosition();
            const r = await client.checkin(task.id, pos.lat, pos.lng);
            setCheckin(`打卡成功，距任务地点 ${r.distance_m} 米`);
          } catch (e) {
            // too_far 时服务端会把**实际距离**写在消息里，原样显示——
            // 只说「超出范围」的话，他不知道是差 50 米还是差 5 公里
            setError(apiErrorText(e));
          }
        }} />
      )}
      {!!checkin && <Text style={styles.mutedLeft}>{checkin}</Text>}
      <Text style={styles.mutedLeft}>
        求助会立即通知任务对方与平台并留痕；遇到危险请先拨打 110。
      </Text>
    </View>
  );
}

/** APP-062/063 举报与拉黑。审核必查项里的两条，Web 上早就有。
 *
 * 举报**要能选类型**：`POST /reports` 收 target_type + target_id + reason，
 * 做成一个只发 reason 的按钮，运营侧收到的是一堆不知道在说什么的工单。
 */
function ReportAndBlock({ client, task, meId }: {
  client: PlatformClient; task: Task; meId: number | null;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');
  const other = meId === task.creator_id ? task.executor_id : task.creator_id;

  return (
    <View style={{ gap: 6 }}>
      <TouchableOpacity onPress={() => setOpen(!open)}>
        <Text style={styles.linkRow}>举报 / 拉黑</Text>
      </TouchableOpacity>
      {open && (
        <View style={{ gap: 6 }}>
          <TextInput style={styles.input} placeholder="说明问题（会进入人工审核队列）"
                     value={reason} onChangeText={setReason} />
          <Button title="举报这个任务" onPress={async () => {
            setNotice('');
            try {
              await client.report('task', task.id, reason || '内容不当');
              setNotice('已提交，运营会在审核队列里看到');
              setReason('');
            } catch (e) { setNotice(apiErrorText(e)); }
          }} />
          {other != null && (
            <Button title="拉黑对方（不再收到 TA 的私信）" onPress={async () => {
              setNotice('');
              try {
                const r = await client.toggleBlock(other);
                setNotice(r.blocked ? '已拉黑' : '已取消拉黑');
              } catch (e) { setNotice(apiErrorText(e)); }
            }} />
          )}
          {!!notice && <Text style={styles.mutedLeft}>{notice}</Text>}
        </View>
      )}
    </View>
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
    millisUntil(dispute.response_deadline) / 3_600_000,
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

/** APP-060 这个按钮此前**每次点击都返回 400**。
 *
 * V77 把 `ip_assignment` 改成必填时，Web、测试、四个闭环脚本都改了，
 * 唯独 App 没有——而 App 没有任何测试，CI 只做 `tsc`，
 * 漏一个字段在 `Partial<Task>` 面前不是类型错误。
 * 现在它是了（SDK 里改成必需参数），这段代码漏掉它就编译不过。
 */
function PublishScreen({ client, onDone }: { client: PlatformClient; onDone: () => void }) {
  const [title, setTitle] = useState('');
  const [budget, setBudget] = useState('200');
  // 没有默认值是有意的（IPC-001）：替发布方猜归属，对执行方不公平，
  // 对含第三方素材的交付物直接就是错的
  const [ip, setIp] = useState<IpAssignment | ''>('');
  const [error, setError] = useState('');
  return (
    <ScrollView contentContainerStyle={styles.center}>
      <Text style={styles.title}>发布任务</Text>
      <TextInput style={styles.input} placeholder="标题（如：帮忙取快递）" value={title} onChangeText={setTitle} />
      <TextInput style={styles.input} placeholder="预算（元）" value={budget} onChangeText={setBudget} keyboardType="numeric" />
      <Text style={styles.mutedLeft}>交付成果归谁（必选）</Text>
      {(Object.keys(IP_ASSIGNMENT_LABEL) as IpAssignment[]).map((key) => (
        <TouchableOpacity key={key} onPress={() => setIp(key)}>
          <Text style={ip === key ? styles.optionActive : styles.option}>
            {ip === key ? '● ' : '○ '}{IP_ASSIGNMENT_LABEL[key]}
          </Text>
        </TouchableOpacity>
      ))}
      {!!error && <Text style={styles.error}>{error}</Text>}
      <Button title="发布（线上任务）" onPress={async () => {
        setError('');
        if (!ip) { setError('请选择交付成果的知识产权归属'); return; }
        try {
          await client.createTask({
            title, category: '跑腿', task_type: 'event',
            budget_cents: Math.round(parseFloat(budget || '0') * 100),
            ip_assignment: ip,
            is_remote: true, publish_now: true,
          });
          onDone();
        } catch (e) {
          setError(apiErrorText(e));
        }
      }} />
    </ScrollView>
  );
}

/** APP-065 钱包。改造前这一页**只有充值，没有提现**——
 *  而 Web 的提现按钮每次点击都返回 400（没有任何端能绑收款账户）。
 *  合起来就是：**钱能进，不能出。**
 */
export function WalletScreen({ client }: { client: PlatformClient }) {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [rows, setRows] = useState<LedgerRow[]>([]);
  const [amount, setAmount] = useState('100');
  const [error, setError] = useState('');
  const [hint, setHint] = useState('');

  const load = useCallback(async () => {
    setWallet(await client.wallet());
    setRows(await client.ledger().catch(() => []));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  const cents = Math.round(parseFloat(amount || '0') * 100);

  async function act(fn: () => Promise<unknown>) {
    setError(''); setHint('');
    try {
      await fn();
      await load();
    } catch (e) {
      // CLI-064 拦截理由原样显示。「请先绑定收款账户」这句话只有配上
      // 下面那个绑定表单才有意义——光显示理由，用户照样无处可去。
      setError(apiErrorText(e));
    }
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }}>
      <Text style={styles.title}>我的钱包</Text>
      {wallet && (
        <View style={styles.cardRow}>
          <View style={{ flex: 1 }}><Text style={styles.mutedLeft}>可用</Text><Text style={styles.cardTitle}>{fmtYuan(wallet.available_cents)}</Text></View>
          <View style={{ flex: 1 }}><Text style={styles.mutedLeft}>托管中</Text><Text style={styles.cardTitle}>{fmtYuan(wallet.escrow_cents)}</Text></View>
          {/* SYNC-005 App 此前连「冻结中」都不显示：接单被冻结的保证金
              只表现为可用余额变少，全端**没有任何一处**提到这笔钱。 */}
          <View style={{ flex: 1 }}><Text style={styles.mutedLeft}>冻结中</Text><Text style={styles.cardTitle}>{fmtYuan(wallet.frozen_cents)}</Text></View>
        </View>
      )}
      <TextInput style={styles.input} keyboardType="numeric" value={amount}
                 onChangeText={setAmount} placeholder="金额（元）" />
      <Button title={`充值 ${fmtYuan(cents)}（模拟）`} onPress={() => act(() => client.topup(cents))} />
      <Button title={`提现 ${fmtYuan(cents)}`} color="#6b7280" onPress={() => act(async () => {
        const r = await client.withdraw(cents);
        // AML-030/031 tipping-off：大额进人审时**原样显示服务端的中性话术**，
        // 绝不能自己编一句「你的提现触发了风控」——那等于教他下次怎么规避。
        setHint(r.status === 'pending_review' ? (r.message ?? '提现申请已提交，等待处理') : '提现已受理');
      })} />
      {!!hint && <Text style={styles.mutedLeft}>{hint}</Text>}
      {!!error && <Text style={styles.error}>{error}</Text>}

      <PayoutAccountBlock client={client} />

      {/* APP-065 账单流水。此前这一页只有三个数字：「余额少了一百块」
          而看不到为什么，是最容易变成工单的一类问题。 */}
      <Text style={styles.cardTitle}>账单流水</Text>
      {rows.length === 0 && <Text style={styles.mutedLeft}>暂无流水</Text>}
      {rows.map((e) => (
        <View key={e.id} style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            {/* LEDG-004 科目中文名走共享 SDK，不在 App 里另写一份 */}
            <Text style={styles.cardTitle}>{ledgerKindLabel(e.kind)}</Text>
            <Text style={styles.mutedLeft}>{e.memo || '—'}</Text>
          </View>
          <Text style={[styles.cardTitle, { color: e.amount_cents >= 0 ? '#16a34a' : '#dc2626' }]}>
            {e.amount_cents >= 0 ? '+' : ''}{fmtYuan(e.amount_cents)}
          </Text>
        </View>
      ))}
    </ScrollView>
  );
}

/** PAY-030 收款账户绑定。**提现的前置条件，此前全仓没有任何界面能满足它。**
 *
 * 服务端 `POST /wallet/withdraw` 第一行就是「没绑收款账户就拒」，而
 * `bindPayoutAccount` 在 Web 和 App 上都没有被调用过一次。
 * 服务端的「请先 X」，如果 X 在客户端没有入口，那这句话不是提示，是死路。
 */
function PayoutAccountBlock({ client }: { client: PlatformClient }) {
  const [acct, setAcct] = useState<PayoutAccountView | null>(null);
  const [accountNo, setAccountNo] = useState('');
  const [holder, setHolder] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setAcct(await client.getPayoutAccount().catch(() => null));
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.cardTitle}>收款账户</Text>
      <Text style={styles.mutedLeft}>
        {acct?.bound
          // 服务端返回的就是脱敏卡号（6222****0000），照此显示，别试图拼回去
          ? `已绑定 · ${acct.kind === 'alipay' ? '支付宝' : '银行卡'} ${acct.account_no}（${acct.holder_name}）`
          : '未绑定收款账户，提现会被拒绝。'}
      </Text>
      <TextInput style={styles.input} value={accountNo} onChangeText={setAccountNo}
                 placeholder="银行卡号 / 支付宝账号" />
      <TextInput style={styles.input} value={holder} onChangeText={setHolder} placeholder="开户姓名" />
      {/* PAY-005 收款人须与实名一致（防代提/洗钱）。先说，别让他提交完才知道 */}
      <Text style={styles.mutedLeft}>收款人姓名须与实名认证一致，否则会被拒绝。</Text>
      <Button title={acct?.bound ? '更换收款账户' : '绑定收款账户'} onPress={async () => {
        setError('');
        try {
          await client.bindPayoutAccount(accountNo.trim(), holder.trim());
          setAccountNo('');
          await load();
        } catch (e) {
          // AML-012 账户聚集等风控拒绝：理由原样显示
          setError(apiErrorText(e));
        }
      }} />
      {!!error && <Text style={styles.error}>{error}</Text>}
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

/** APP-061~064 应用商店**审核必查项**：账号注销、举报、拉黑、协议入口。
 *
 * `STORE_CHECKLIST.md` 里这四行长期是「⚠️ 待接入」——它们不是「最好有」，
 * **缺任何一条会被直接打回**，而前三条在 Web 上早就有了，
 * 差的只是 App 上这几个按钮。
 */
function MeScreen({ client, me, refresh, onLogout }: {
  client: PlatformClient; me: Me | null; refresh: () => void; onLogout: () => void;
}) {
  // APP-069 三条线挂在「我的」下面，不再加 Tab——七个已经够多了
  const [sub, setSub] = useState<SubScreen | null>(null);
  const [notice, setNotice] = useState('');
  const [agreements, setAgreements] = useState<string[]>([]);
  const [docText, setDocText] = useState('');
  const [needsReconsent, setNeedsReconsent] = useState(false);
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');

  // 进页面就查一次：**协议更新是平台单方面发生的**，不该等用户先去点一下
  // 「用户协议」才发现自己已经被挡住了
  useEffect(() => {
    void client.myAgreements()
      .then((s) => setNeedsReconsent(s.documents.some((d) => d.needs_reconsent)))
      .catch(() => {});
  }, [client]);

  if (sub) return <SubScreenHost client={client} screen={sub} onBack={() => setSub(null)} />;
  if (!me) return <Text style={styles.muted}>加载中…</Text>;
  return (
    <ScrollView contentContainerStyle={styles.center}>
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

      {/* ACC-040 修改密码。服务端一直都在，**两端都没有入口**——
          用户怀疑密码泄露时，能做的只有注销账号。 */}
      <TextInput style={styles.input} secureTextEntry value={oldPw} onChangeText={setOldPw}
                 placeholder="当前密码" />
      <TextInput style={styles.input} secureTextEntry value={newPw} onChangeText={setNewPw}
                 placeholder="新密码（至少 8 位）" />
      <Button title="修改密码" onPress={async () => {
        setNotice('');
        try {
          await client.changePassword(oldPw, newPw);
          setOldPw(''); setNewPw('');
          // 服务端会换发 token（旧的失效）。App 这里如实告诉他要重新登录，
          // 而不是让他下一次点任何东西时莫名其妙 401
          setNotice('密码已修改，请重新登录');
        } catch (e) {
          setNotice(apiErrorText(e));
        }
      }} />

      {/* APP-069 团队 / 合作体 / 开发者。三条线此前**只有网页看得见**，
          而 V92 刚给团队审批加了通知——通知把人叫来、他点进去无路可走，
          比没有通知更糟（APP-066 同一条教训）。 */}
      {(['messages', 'invitations', 'applications', 'teams', 'ventures', 'developer'] as SubScreen[]).map((key) => (
        <TouchableOpacity key={key} onPress={() => setSub(key)}>
          <Text style={styles.linkRow}>{SUB_SCREEN_LABEL[key]} ›</Text>
        </TouchableOpacity>
      ))}

      {/* APP-064 协议与隐私政策：审核员会点开看 */}
      <TouchableOpacity onPress={async () => {
        const status = await client.myAgreements().catch(() => null);
        if (!status) { setDocText('暂时读取不到，请检查网络'); return; }
        setAgreements(status.documents.map(
          (d) => `${d.name}（当前 ${d.current_version}${d.needs_reconsent ? ' · 有更新待同意' : ''}）`,
        ));
        // LAW-032 数据主体权利入口一并列出——「有能力但用户找不到」等于没有
        setDocText(Object.entries(status.rights).map(([k, v]) => `${k}：${v}`).join('\n'));
      }}>
        <Text style={styles.linkRow}>用户协议与隐私政策 ›</Text>
      </TouchableOpacity>
      {agreements.map((t) => <Text key={t} style={styles.mutedLeft}>{t}</Text>)}
      {!!docText && <Text style={styles.mutedLeft}>{docText}</Text>}
      {/* LAW-030 协议更新后必须重新同意，否则**发布/接单/资金都会被 409 挡住**
          （`agreement_update_required`）。App 此前只能「看」协议状态，不能同意——
          一次协议更新就能把 App 用户卡成只读，而他在 App 上无处可点。 */}
      {needsReconsent && (
        <Button title="阅读并同意更新后的协议" onPress={async () => {
          setNotice('');
          try {
            await client.acceptAgreements();
            setNeedsReconsent(false);
            setNotice('已同意最新版本');
          } catch (e) {
            setNotice(apiErrorText(e));
          }
        }} />
      )}

      {/* APP-061 注销。**不能做成一个直接调接口的按钮**：服务端会拦
          （有钱、有在途合约、有纠纷），而用户看到的会是一个莫名其妙的报错。
          所以把服务端给的拦截理由原样显示出来（CLI-064 同一条）。 */}
      <TouchableOpacity onPress={async () => {
        setNotice('');
        try {
          await client.deactivateAccount();
          onLogout();
        } catch (e) {
          setNotice(apiErrorText(e));
        }
      }}>
        <Text style={styles.linkRow}>注销账号</Text>
      </TouchableOpacity>
      <Text style={styles.mutedLeft}>
        注销后实名与交易记录按法定要求脱敏保留，钱包余额需先提现、在途合约需先了结。
      </Text>
      {!!notice && <Text style={styles.error}>{notice}</Text>}

      <Button title="退出登录" onPress={onLogout} />
    </ScrollView>
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
  option: { color: '#1a1d24', paddingVertical: 6 },
  optionActive: { color: '#2f6fed', fontWeight: '600', paddingVertical: 6 },
  linkRow: { color: '#2f6fed', paddingVertical: 10 },
});
