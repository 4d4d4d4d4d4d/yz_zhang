import { TeamReturnsBlock } from './teamReturns';
import { ChainEntry } from './ChainEntry';
import { EvidenceExportButton, InvoicesBlock } from './appGaps';
import { MilestonesBlock } from './milestones';
import { DeliverablesList } from './deliverables';
import { DraftHints, PriceRefBlock, TaskProfileBlock } from './profiles';
import { ContractEvidence } from './ContractEvidence';
// App 端（13 号 spec 五 Tab 信息架构）
// 复用 @platform/core SDK，与 Web 同一套后端 API。
// 运行：npm install && npx expo start（后端默认 http://localhost:8000）
import { DEPOSIT_STATUS_LABEL, IP_ASSIGNMENT_LABEL, OperationKey, PlatformClient, TASK_STATUS_LABEL, apiErrorText, dayLabel, dayShiftsPayload, describeChangeOrder, fmtYuan, formatDateTime, hasChildTasks, isAuthRejection, shiftLabel, templatePrefill, GUARDIAN_MODE_LABEL, minorPayload, minorTaskLine, visitShortfall, localInputToServerTime, ledgerKindLabel, millisUntil, taskActions, type Contract, type Dispute, type DisputeStatement, type IpAssignment, type ChangeOrderView, type DayShiftInput, type LedgerRow, type Me, type PackTaskTemplateBrief, type GuardianMode, type Notice, type PayoutAccountView, type Task, type Wallet } from '@platform/core';
import { isSandbox, loadSandbox } from './sandboxState';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CockpitBlock, DecomposeScreen, TaskTreeBlock } from './decompose';
import { VisitsBlock, hasVisits } from './visits';
import { ScreenBoundary } from './ScreenBoundary';
import { RecipientEditorBlock, canChangeRecipient } from './recipient';
import { ShowcaseConsentBlock, canGrantShowcase } from './showcase';
import { canRequestInvoice } from './invoiceEntry';
import { DiscoverScreen } from './Discover';
import { AgentBlock, RecommendationsBlock } from './collaborators';
import { ExperienceToolsBlock } from './experience';
import { MessagesScreen } from './MessagesAndInvites';
import { MySpaceScreen, PublicSpaceScreen, SpacesDiscoverScreen } from './spaces';
import { SearchScreen } from './search';
import { SUB_SCREEN_LABEL, SubScreenHost, type SubScreen } from './TeamCoopDev';
import { VideoFeedScreen } from './VideoFeed';
import {
  Button, FlatList, Linking, Platform, RefreshControl, SafeAreaView, ScrollView, StyleSheet,
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

const BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

// SPACE-010 四入口：发现 / 合作 / 消息 / 我的空间。
//
// 与 web 的导航对齐（`web/src/App.tsx` 的 nav-links 就是这四个），而**通知与
// 账户不进 Tab、改成常驻顶栏**——web 也是这么做的（🔔 与账户在 nav-account 里）。
// 这一点是刻意的：V100 那一批的催办、临期、预警全靠用户看见通知，
// **把通知折进二级页面，等于把那一批的价值折掉一半**。
//
// 原来的七个 Tab（任务/发现流/视频/发布/钱包/通知/我的）一个都没有删，
// 只是换了入口：发布在「合作」页顶部，内容流与视频在「发现」页的分段里，
// 钱包与通知在顶栏，其余在「我的」。
type Tab = 'spaces' | 'cooperate' | 'messages' | 'myspace';
type Overlay =
  | { kind: 'notices' }
  | { kind: 'account' }
  | { kind: 'wallet' }
  | { kind: 'space'; userId: number };

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<Tab>('spaces');
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [conversation, setConversation] = useState<number | null>(null);

  const client = useMemo(
    // SBX-102 隐私沙箱开着：把原文交给云端 AI 的请求在发出之前就拦下（128 号 spec）
    () => new PlatformClient({ baseUrl: BASE_URL, getToken: () => token, sandbox: isSandbox }),
    [token],
  );

  useEffect(() => { void loadSandbox(); }, []);

  useEffect(() => {
    // REG-002（222 号 spec）只有服务端明确不认这个登录才清；手机信号一抖就登出是不对的
    if (token) client.me().then(setMe).catch((e) => { if (isAuthRejection(e)) setToken(null); });
    else setMe(null);
  }, [token, client]);

  // SPACE-028 进站深链：`https://.../people/9` 或 `taskplat://people/9`
  // 直接打开那个人的空间。
  //
  // 为什么这件事必须做：空间的用处是**给别人看**。没有深链，分享出去的链接
  // 在装了 App 的手机上会被系统拦进 App，然后落在首页——**分享越成功，
  // 落空越多**。app.json 里原来只声明了 /tasks 的 intentFilter，
  // 也就是说这个新入口在 Android 上压根不会被路由过来。
  //
  // 两个来源都要接：冷启动（`getInitialURL`）与运行中（`url` 事件）。
  // 只接一个的后果很具体：App 在后台时点链接没反应，而用户会以为链接坏了。
  useEffect(() => {
    function open(url: string | null) {
      const m = url && /\/people\/(\d+)/.exec(url);
      if (m) setOverlay({ kind: 'space', userId: Number(m[1]) });
    }
    void Linking.getInitialURL().then(open).catch(() => {});
    const sub = Linking.addEventListener('url', (e) => open(e.url));
    return () => sub.remove();
  }, []);

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
      {/* 通知与钱包不进 Tab，但**一跳可达**：V100 的催办/临期/预警全靠用户
          看见通知，钱包是钱的入口。折进二级页面等于把那两批的价值折掉。 */}
      <View style={styles.topbar}>
        <TouchableOpacity onPress={() => setOverlay({ kind: 'notices' })}>
          <Text style={styles.topbarItem}>通知</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setOverlay({ kind: 'wallet' })}>
          <Text style={styles.topbarItem}>钱包</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setOverlay({ kind: 'account' })}>
          <Text style={styles.topbarItem}>{me?.nickname || '账户'}</Text>
        </TouchableOpacity>
      </View>
      <View style={styles.body}>
        {/* APP-092 一屏出错只坏这一屏：顶栏、Tab 还在，换成说明（183 号 spec）；换一屏自动复位 */}
        <ScreenBoundary key={activeTask ? `task-${activeTask.id}` : overlay ? `overlay-${overlay.kind}` : `tab-${tab}`}
                        onBack={() => { setActiveTask(null); setOverlay(null); }}
                        onError={(kind) => {
                          // APP-094 屏名不带任务 id
                          const screenName = activeTask ? 'task' : overlay ? `overlay-${overlay.kind}` : `tab-${tab}`;
                          void client.reportRenderError('app', screenName, kind).catch(() => {});
                        }}>
        {activeTask ? (
          <TaskDetailScreen client={client} me={me} task={activeTask}
                            onBack={() => setActiveTask(null)}
                            onOpenTask={setActiveTask}
                            onChanged={async () => setActiveTask(await client.getTask(activeTask.id))} />
        ) : overlay ? (
          <>
            <TouchableOpacity onPress={() => setOverlay(null)}>
              <Text style={styles.linkRow}>← 返回</Text>
            </TouchableOpacity>
            {overlay.kind === 'notices' && <NoticesScreen client={client} />}
            {overlay.kind === 'wallet' && <WalletScreen client={client} />}
            {overlay.kind === 'account' && (
              <MeScreen client={client} me={me} refresh={() => client.me().then(setMe)}
                        onLogout={() => setToken(null)} />
            )}
            {overlay.kind === 'space' && (
              <PublicSpaceScreen client={client} userId={overlay.userId}
                                 onBack={() => setOverlay(null)}
                                 onOpenConversation={(id) => {
                                   setConversation(id); setOverlay(null); setTab('messages');
                                 }} />
            )}
          </>
        ) : (
          <>
            {/* SPACE-004 以人为中心的发现。内容流与视频流没有删，挪到这一页的
                分段里——「发现优先展示人、作品、生活和正在发生的合作」。 */}
            {tab === 'spaces' && (
              <DiscoverHost client={client} baseUrl={BASE_URL}
                            onOpenSpace={(userId) => setOverlay({ kind: 'space', userId })}
                            onOpenTask={(taskId) => {
                              // 搜索结果只带摘要，详情页要完整的 Task
                              void client.getTask(taskId).then(setActiveTask).catch(() => {});
                            }} />
            )}
            {tab === 'cooperate' && (
              <CooperateHost client={client} onOpen={setActiveTask} />
            )}
            {tab === 'messages' && (
              <MessagesScreen client={client} initialConversationId={conversation} />
            )}
            {tab === 'myspace' && (
              <MySpaceScreen client={client} me={me}
                             refreshMe={() => { void client.me().then(setMe); }}
                             onPreview={(userId) => setOverlay({ kind: 'space', userId })} />
            )}
          </>
        )}
        </ScreenBoundary>
      </View>
      {!activeTask && !overlay && (
        <View style={styles.tabbar}>
          {([['spaces', '发现'], ['cooperate', '合作'], ['messages', '消息'], ['myspace', '我的空间']] as [Tab, string][]).map(([key, label]) => (
            <TouchableOpacity key={key} style={styles.tab} onPress={() => setTab(key)}>
              <Text style={[styles.tabText, tab === key && styles.tabActive]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </SafeAreaView>
  );
}

/** 「发现」页：人在前，内容与视频在后。
 *
 * 旧的发现流（视差内容）与视频流**一个都没删**，只是不再各占一个 Tab：
 * 新定位里发现的主体是人与作品，而内容消费是其中一种形式。
 * 分段切换比塞进「我的」合理——它们本来就是「发现」这件事。
 */
export function DiscoverHost({ client, baseUrl, onOpenSpace, onOpenTask }: {
  client: PlatformClient; baseUrl: string; onOpenSpace: (userId: number) => void;
  onOpenTask: (taskId: number) => void;
}) {
  const [seg, setSeg] = useState<'people' | 'search' | 'feed' | 'video'>('people');
  return (
    <>
      <View style={styles.segbar}>
        {([['people', '人与空间'], ['search', '搜索'], ['feed', '内容'], ['video', '视频']] as const).map(([k, label]) => (
          <TouchableOpacity key={k} onPress={() => setSeg(k)}>
            <Text style={[styles.seg, seg === k && styles.segOn]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {seg === 'people' && <SpacesDiscoverScreen client={client} onOpen={onOpenSpace} />}
      {/* SRCH-001 全站搜索（V127）：任务、人、内容、圈层一次查。
          找不到东西的平台等于没有内容（72 号台账 SEARCH-050 的原话）。 */}
      {seg === 'search' && <SearchScreen client={client} onOpenSpace={onOpenSpace} onOpenTask={onOpenTask} />}
      {/* APP-002 发现流：视差滚动，尊重系统「减弱动态效果」开关 */}
      {seg === 'feed' && <DiscoverScreen client={client} baseUrl={baseUrl} />}
      {/* CNT-014 沉浸流：任何时刻有且只有一个 <Video> 在播 */}
      {seg === 'video' && <VideoFeedScreen client={client} baseUrl={baseUrl} />}
    </>
  );
}

/** 「合作」页：正在发生的合作 + 发起一个。
 *
 * 发布从 Tab 挪到这里顶部——它是「合作」的一个动作，而不是与合作并列的
 * 一个地方。任务列表与发布表单都没有改。
 */
export function CooperateHost({ client, onOpen }: {
  client: PlatformClient; onOpen: (t: Task) => void;
}) {
  const [publishing, setPublishing] = useState(false);
  if (publishing) {
    return (
      <>
        <TouchableOpacity onPress={() => setPublishing(false)}>
          <Text style={styles.linkRow}>← 返回合作</Text>
        </TouchableOpacity>
        <PublishScreen client={client} allowProject
                       onDone={(created) => {
                         setPublishing(false);
                         // APP-077 项目型任务建好后直接到它的详情页，那里接着拆
                         if (created && created.task_type === 'project') onOpen(created);
                       }} />
      </>
    );
  }
  return (
    <>
      <TouchableOpacity onPress={() => setPublishing(true)}>
        <Text style={styles.linkRow}>＋ 发起一个合作</Text>
      </TouchableOpacity>
      <TasksScreen client={client} onOpen={onOpen} />
    </>
  );
}

/** ACC-041 登录、注册、验证码登录与忘记密码（77 号 spec）。
 *
 * 改造前这里是一行 `login().catch(() => register())`，两个毛病：
 *
 * 1. **密码打错会走到注册**，注册又因手机号已存在而失败，于是用户看到的是
 *    「该手机号已注册」——他输错的是密码，平台告诉他的是手机号的事。
 * 2. **手机号打错一位会静默注册出一个新账号**，而他以为自己登录成功了，
 *    然后发现钱包是空的、任务不见了。
 *
 * 所以登录是登录、注册是注册；失败原样显示服务端文案，
 * 并把「验证码登录」「忘记密码」摆在旁边——忘了密码的人此前**进不来**。
 */
export function LoginScreen({ client, onToken }: { client: PlatformClient; onToken: (t: string) => void }) {
  const [mode, setMode] = useState<'login' | 'register' | 'sms' | 'reset'>('login');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const titles = { login: '登录', register: '注册', sms: '验证码登录', reset: '重置密码' } as const;

  async function sendCode() {
    setError(''); setInfo('');
    try {
      const r = await client.sendSmsCode(phone, mode === 'reset' ? 'reset' : mode === 'register' ? 'verify' : 'login');
      if (r.dev_code) setSmsCode(r.dev_code);
      setInfo(`验证码已发送，${r.expires_in} 秒内有效`);
    } catch (e) {
      setError(apiErrorText(e));
    }
  }

  async function submit() {
    setError(''); setInfo('');
    try {
      if (mode === 'reset') {
        await client.resetPassword(phone, smsCode, password);
        setMode('login');
        setInfo('密码已重置，请用新密码登录');
        return;
      }
      const res =
        mode === 'login' ? await client.login(phone, password)
        : mode === 'sms' ? await client.smsLogin(phone, smsCode)
        : await client.register(phone, password, `用户${phone.slice(-4)}`, smsCode);
      onToken(res.token);
    } catch (e) {
      // 原样显示服务端文案：密码错就是密码错，不要替它猜成「去注册」
      setError(apiErrorText(e));
    }
  }

  return (
    <View style={styles.center}>
      <Text style={styles.title}>协作任务平台</Text>
      <TextInput style={styles.input} placeholder="手机号" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      {mode !== 'sms' && (
        <TextInput style={styles.input} placeholder={mode === 'reset' ? '新密码' : '密码'}
                   value={password} onChangeText={setPassword} secureTextEntry />
      )}
      {(mode === 'sms' || mode === 'reset' || mode === 'register') && (
        <>
          <TextInput style={styles.input} placeholder="短信验证码" value={smsCode}
                     onChangeText={setSmsCode} keyboardType="number-pad" />
          <Button title="获取验证码" onPress={() => void sendCode()} />
        </>
      )}
      {!!error && <Text style={styles.error}>{error}</Text>}
      {!!info && <Text style={styles.muted}>{info}</Text>}
      <Button title={titles[mode]} onPress={() => void submit()} />
      {mode !== 'login' && <Button title="用密码登录" onPress={() => setMode('login')} />}
      {mode !== 'sms' && <Button title="验证码登录" onPress={() => setMode('sms')} />}
      {mode !== 'reset' && <Button title="忘记密码" onPress={() => setMode('reset')} />}
      {mode !== 'register' && <Button title="没有账号？注册" onPress={() => setMode('register')} />}
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

export function TaskDetailScreen({ client, me, task, onBack, onChanged, onOpenTask }: {
  client: PlatformClient; me: Me | null; task: Task; onBack: () => void; onChanged: () => Promise<void>;
  /** 子任务进度里点进某一步 */
  onOpenTask?: (t: Task) => void;
}) {
  const [error, setError] = useState('');
  const [decomposing, setDecomposing] = useState(false);
  const [contract, setContract] = useState<Contract | null>(null);
  const [confirmRelease, setConfirmRelease] = useState(false);
  // SCN-125（179 号 spec）验收前上门回报的差距：第一下拿差距摊开，第二下才验收
  const [visitWarn, setVisitWarn] = useState('');
  const [apps, setApps] = useState<ApplicationRow[]>([]);
  const meId = me?.id ?? null;

  // 操作可见性由 SDK 单一事实来源决定（03/05 spec 角色×状态矩阵，与 Web 共用）
  const actions = taskActions(task, meId, contract);

  const reload = useCallback(async () => {
    if (['matched', 'in_progress', 'pending_acceptance'].includes(task.status)) {
      client.getContractByTask(task.id).then(setContract).catch(() => setContract(null));
    } else setContract(null);
    if (task.status === 'published' && meId === task.creator_id) {
      // APP-090：响应不是数组时当作没人报名，不把详情页带崩
      client.listApplications(task.id).then((r) => setApps(Array.isArray(r) ? r : [])).catch(() => setApps([]));
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

  const isProjectRoot = task.task_type === 'project' && task.parent_id === null;
  if (decomposing) {
    return (
      <ScrollView contentContainerStyle={{ gap: 12 }}>
        <DecomposeScreen client={client} task={task} onBack={() => setDecomposing(false)}
                         onConfirmed={() => { setDecomposing(false); void onChanged(); }} />
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }}>
      <TouchableOpacity onPress={onBack}><Text style={{ color: '#275c52' }}>← 返回</Text></TouchableOpacity>
      <Text style={styles.title}>{task.title}</Text>
      {/* APP-077 项目型草稿还没拆完：在这里接着拆 */}
      {isProjectRoot && task.status === 'draft' && meId === task.creator_id && (
        <TouchableOpacity onPress={() => setDecomposing(true)}>
          <Text style={styles.linkRow}>还没拆完：继续拆解 →</Text>
        </TouchableOpacity>
      )}
      {/* SCN-116：多人、多天的母任务也有子任务（名额），与项目型同一块（判断在共享 SDK） */}
      {hasChildTasks(task) && onOpenTask && <TaskTreeBlock client={client} task={task} onOpenTask={onOpenTask} meId={meId} />}
      {/* SCN-118 名额是某一天的：回到整单，一次报多天 */}
      {task.parent_id !== null && !!task.work_date && task.status === 'published' && onOpenTask && (
        <TouchableOpacity onPress={() => void client.getTask(task.parent_id as number).then(onOpenTask).catch(() => {})}>
          <Text style={styles.linkRow}>这单一共好几天：回到整单，一次报多天 →</Text>
        </TouchableOpacity>
      )}
      {/* SPACE-024 合作驾驶舱（移动简化版：进度、钱、预警、关键路径；APP-007）——只给发布方 */}
      {hasChildTasks(task) && meId === task.creator_id && <CockpitBlock client={client} taskId={task.id} />}
      {/* SCN-120 一单多次上门的逐次回报（176 号 spec）：成交双方 */}
      {hasVisits(task) && meId !== null && (meId === task.creator_id || meId === task.executor_id)
        && !['draft', 'published'].includes(task.status) && (
        <VisitsBlock client={client} task={task} isExecutor={meId === task.executor_id} locate={currentPosition} />
      )}
      {/* PROF-103 这单的画像（126 号 spec） */}
      {task.status !== 'draft' && <TaskProfileBlock client={client} taskId={task.id} isCreator={task.creator_id === me?.id}
        onApplyWithQuestions={actions.includes('apply') ? (m) => void act(() => client.apply(task.id, m)) : undefined} />}
      {/* AGT-080~083 经验工具：双方都能用，只出草稿（109 号 spec） */}
      {meId !== null && (meId === task.creator_id || meId === task.executor_id) && (
        <ExperienceToolsBlock client={client} task={task} />
      )}
      {/* APP-079 找合作者：AI 推荐人选与 AI 助理，只对发布方（110 号 spec） */}
      {meId === task.creator_id && task.status === 'published' && (
        <RecommendationsBlock client={client} task={task} />
      )}
      {meId === task.creator_id && <AgentBlock client={client} task={task} onChanged={() => void onChanged()} />}
      <Text style={styles.mutedLeft}>
        {task.category} · {TASK_STATUS_LABEL[task.status]} · {fmtYuan(task.budget_cents)}
      </Text>
      {!!task.description && <Text>{task.description}</Text>}
      {!!task.address_exact && <Text style={styles.mutedLeft}>📍 {task.address_exact}</Text>}
      {/* SCN-117 每天几点到几点 */}
      {!!shiftLabel(task) && <Text style={styles.mutedLeft} accessibilityLabel="时段">🕘 {shiftLabel(task)}（北京时间）</Text>}
      {/* SCN-144 服务对象是未成年人：安排方式与要求的证明 */}
      {!!minorTaskLine(task) && <Text style={styles.mutedLeft} accessibilityLabel="未成年人服务">{minorTaskLine(task)}</Text>}
      {/* SCN-119 替别人发的单：谁都看得到；称呼与到场联系只给成交双方 */}
      {!!task.on_behalf && (
        <Text style={styles.mutedLeft} accessibilityLabel="服务对象">
          替别人发的单{task.recipient_label ? `：服务对象「${task.recipient_label}」` : '（服务对象与到场联系方式成交后可见）'}
          {task.onsite_contact ? ` · 到场联系 ${task.onsite_contact}` : ''}
        </Text>
      )}
      {/* SCN-123 发单后改服务对象（197 号 spec） */}
      {canChangeRecipient(task, meId) && <RecipientEditorBlock client={client} task={task} onChanged={onChanged} />}
      {/* SCN-156（278 号 spec） */}
      {canGrantShowcase(task, meId) && <ShowcaseConsentBlock client={client} task={task} onChanged={onChanged} />}
      <ReportAndBlock client={client} task={task} meId={meId} />
      {contract && (
        <View style={styles.cardRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>合约 #{contract.id} · {contract.status}</Text>
            <ContractEvidence client={client} contractId={contract.id} />
            <Text style={styles.mutedLeft}>
              金额 {fmtYuan(contract.amount_cents)} · 服务费 {(contract.fee_bps / 100).toFixed(1)}%
              {contract.deposit_cents > 0
                ? ` · 保证金 ${fmtYuan(contract.deposit_cents)}（${DEPOSIT_STATUS_LABEL[contract.deposit_status] ?? contract.deposit_status}）`
                : ''}
            </Text>
            <Text style={styles.mutedLeft}>
              签署：发布方{contract.signed_by_requester ? '✓' : '…'} / 执行方{contract.signed_by_executor ? '✓' : '…'}
            </Text>
            {/* APP-076 开票在合约上：放款后发布方在这里申请这一单的平台服务费发票（136 号 spec） */}
            {canRequestInvoice(contract, meId) && (
              <InvoicesBlock client={client} contractId={contract.id} />
            )}
          </View>
        </View>
      )}
      {/* SC-004 / SC-014 分期列表（146 号 spec）：整单验收的提示里说的「验收本期」在这里 */}
      {contract && (
        <MilestonesBlock client={client} contract={contract} isCreator={meId === contract.requester_id}
                         isExecutor={meId === contract.executor_id} onChanged={(c) => { setContract(c); void reload(); }} />
      )}
      {/* SCN-166（297 号 spec）交付文件：原图放款完毕前锁着 */}
      {contract && <DeliverablesList client={client} contractId={contract.id} />}
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
      {actions.includes('accept_delivery') && (() => {
        // SC-013 整单验收会放掉**剩余全部**期（服务端如此设计，93 号 spec）。
        // 发布方当初定分期，正是为了不一次付完——在一个只写「验收通过（放款）」
        // 的按钮上一次放光，他失去的是自己设的那道保护。
        //
        // RN 里没有 `confirm()`，所以做成两步：第一下只把「几期、多少钱」
        // 摊在屏幕上。web 那边用的是 confirm —— 各自平台的惯用法。
        const pending = (contract?.milestones ?? []).filter((m) => m.status !== 'released');
        if (pending.length > 1 && !confirmRelease) {
          const sum = pending.reduce((n, m) => n + m.amount_cents, 0);
          return (
            <View style={styles.cardRow}>
              <View style={{ flex: 1, gap: 6 }}>
                <Text style={styles.cardTitle}>
                  这一步会放掉剩余 {pending.length} 期、共 {fmtYuan(sum)}
                </Text>
                <Text style={styles.mutedLeft}>
                  只想付已完成的那一期，请用下面分期列表里的「验收本期」。
                </Text>
                <Button title="确认整单放款" onPress={() => setConfirmRelease(true)} />
              </View>
            </View>
          );
        }
        if (visitWarn) {
          return (
            <View style={{ gap: 6 }} accessibilityLabel="验收前提醒">
              <Text style={styles.mutedLeft}>{visitWarn}</Text>
              <Button title="仍然验收通过（放款）" onPress={() => act(() => client.acceptDelivery(task.id))} />
            </View>
          );
        }
        return <Button title="验收通过（放款）" onPress={async () => {
          // SCN-125 上门回报比计划少或有漏项：先说清差多少，不拦（钱的事由发单人定）
          if (hasVisits(task)) {
            const warn = visitShortfall(await client.taskVisits(task.id).catch(() => null));
            if (warn) { setVisitWarn(warn); return; }
          }
          await act(() => client.acceptDelivery(task.id));
        }} />;
      })()}
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
  const [deadline, setDeadline] = useState('');
  const [scope, setScope] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    // APP-090：响应不是数组时当作没有变更单
    const r = await client.changeOrders(contract.id).catch(() => []);
    setRows(Array.isArray(r) ? r : []);
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
            <Text style={styles.cardTitle}>{describeChangeOrder(r, contract.amount_cents, (t) => formatDateTime(t))}</Text>
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
          {/* SC-007b 改期（日期，当天 23:59 截止）、改范围 */}
          <TextInput style={styles.input} value={deadline} onChangeText={setDeadline}
                     placeholder="新的截止日期（如 2026-11-02，可不改）" accessibilityLabel="新的截止日期" />
          <TextInput style={styles.input} value={scope} onChangeText={setScope}
                     placeholder="范围调整（如：增加两个卧室，可不改）" accessibilityLabel="范围调整" />
          <TextInput style={styles.input} value={reason} onChangeText={setReason}
                     placeholder="事由（对方会看到）" />
          <Button title="提出变更" onPress={() => {
            if (deadline && !/^\d{4}-\d{2}-\d{2}$/.test(deadline)) { setError('截止日期请写成 2026-11-02 这样'); return; }
            void act(async () => {
            await client.proposeChangeOrder(contract.id, {
              new_amount_cents: amount ? Math.round(parseFloat(amount) * 100) : undefined,
              new_deadline: deadline ? localInputToServerTime(`${deadline}T23:59`) : undefined,
              scope_change: scope.trim() || undefined, reason,
            });
            setAmount(''); setReason(''); setDeadline(''); setScope('');
            });
          }} />
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
      // 响应不像一条纠纷时当作没有（与子任务进度、驾驶舱同一条：一块出错不许把详情页带崩）
      if (!d || typeof d.id !== 'number') { setDispute(null); return; }
      setDispute(d);
      const st = await client.disputeStatements(d.id);
      setStatements(Array.isArray(st) ? st : []);
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
      {/* APP-090 证据包导出（136 号 spec）：整包原样，用系统分享发出去 */}
      <EvidenceExportButton client={client} disputeId={dispute.id} />
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
export function PublishScreen({ client, onDone, category = '跑腿', allowProject = false, template }: {
  client: PlatformClient; onDone: (created?: Task) => void;
  /** SCN-133（211 号 spec）从服务包的发单模板过来：预填标题、说明、上门次数与清单（只是预填，发不发由人定） */
  template?: PackTaskTemplateBrief;
  /** APP-077 「这是一个要拆开做的项目」。只在合作入口给：从「不懂就问」带着类目来的，是一单具体的活 */
  allowProject?: boolean;
  /** LAW-051 别处把人送来时会带上类目（问答答不了 → 发一单法律咨询）。
   *  写死类目的话那个补救入口就是假的：人到了发布页，类目还停在「跑腿」上。 */
  category?: string;
}) {
  const prefill = template ? templatePrefill(template) : null;
  const [title, setTitle] = useState(prefill?.title ?? '');
  const [budget, setBudget] = useState('200');
  // 没有默认值是有意的（IPC-001）：替发布方猜归属，对执行方不公平，
  // 对含第三方素材的交付物直接就是错的
  const [ip, setIp] = useState<IpAssignment | ''>('');
  const [project, setProject] = useState(false);
  // TASK-007 / SCN-107（167 号 spec）几个人、连续几天：名额 = 人数 × 天数
  const [people, setPeople] = useState('1');
  const [days, setDays] = useState('1');
  const [startDate, setStartDate] = useState('');
  // SCN-117（178 号 spec）每天几点到几点
  const [shiftStart, setShiftStart] = useState('');
  const [shiftEnd, setShiftEnd] = useState('');
  // SCN-127（201 号 spec）每天时段不一样
  const [perDay, setPerDay] = useState(false);
  const [dayRows, setDayRows] = useState<DayShiftInput[]>([]);
  // SCN-119（175 号 spec）替别人发单：替谁、到场联系谁、问过本人没有
  const [onBehalf, setOnBehalf] = useState(false);
  const [recipient, setRecipient] = useState('');
  const [onsite, setOnsite] = useState('');
  const [consented, setConsented] = useState(false);
  // SCN-144（214 号 spec）服务对象是未成年人：监护人在场或公开场所、监护人确认
  const [minor, setMinor] = useState(false);
  const [guardianMode, setGuardianMode] = useState<GuardianMode | ''>('');
  const [guardianOk, setGuardianOk] = useState(false);
  // SCN-120（176 号 spec）一单多次上门：上门几次、每次要做的事
  const [visits, setVisits] = useState(prefill?.visits ?? '');
  const [checklist, setChecklist] = useState(prefill?.checklist ?? '');
  const [error, setError] = useState('');
  const nDays = parseInt(days, 10) || 1;
  const nPeople = parseInt(people, 10) || 1;
  return (
    <ScrollView contentContainerStyle={styles.center}>
      <Text style={styles.title}>发布任务</Text>
      {allowProject && (
        <TouchableOpacity onPress={() => setProject((v) => !v)} accessibilityRole="checkbox"
                          accessibilityState={{ checked: project }}>
          <Text style={project ? styles.optionActive : styles.option}>
            {project ? '☑ ' : '☐ '}这是一个要拆开做的项目（AI 帮你一层层拆，说清每一步谁能做）
          </Text>
        </TouchableOpacity>
      )}
      <TextInput style={styles.input} placeholder="标题（如：帮忙取快递）" value={title} onChangeText={setTitle} />
      <TextInput style={styles.input} placeholder="预算（元）" value={budget} onChangeText={setBudget} keyboardType="numeric" />
      <PriceRefBlock client={client} category={category} />
      {/* PROF-101 边写边提示还缺什么（126 号 spec） */}
      <DraftHints client={client} draft={{ title, category, budget_cents: Math.round(parseFloat(budget || '0') * 100), is_remote: true }} />
      {!project && (
        <>
          <TextInput style={styles.input} accessibilityLabel="需要几个人" placeholder="需要几个人" value={people} onChangeText={setPeople} keyboardType="numeric" />
          <TextInput style={styles.input} accessibilityLabel="连续几天" placeholder="连续几天" value={days} onChangeText={setDays} keyboardType="numeric" />
          {nDays > 1 && (
            <TextInput style={styles.input} accessibilityLabel="从哪天开始" placeholder="从哪天开始（如 2026-10-20）" value={startDate} onChangeText={setStartDate} />
          )}
          <TextInput style={styles.input} accessibilityLabel="每天几点开始" placeholder="每天几点开始（如 09:00，可不填）" value={shiftStart} onChangeText={setShiftStart} />
          <TextInput style={styles.input} accessibilityLabel="每天几点结束" placeholder="每天几点结束（如 18:00，可不填）" value={shiftEnd} onChangeText={setShiftEnd} />
          {nDays > 1 && (
            <TouchableOpacity accessibilityRole="checkbox" accessibilityLabel="每天时段不一样" accessibilityState={{ checked: perDay }}
                              onPress={() => setPerDay((x) => !x)}>
              <Text style={styles.mutedLeft}>{perDay ? '☑ ' : '☐ '}每天时段不一样（某天空着就用上面的时段）</Text>
            </TouchableOpacity>
          )}
          {perDay && nDays > 1 && Array.from({ length: Math.min(nDays, 14) }, (_, i) => (
            <View key={i}>
              <Text style={styles.mutedLeft}>{dayLabel(startDate, i)}</Text>
              <TextInput style={styles.input} accessibilityLabel={`第 ${i + 1} 天几点开始`} placeholder="几点开始（如 10:00）"
                         value={dayRows[i]?.start ?? ''}
                         onChangeText={(v) => setDayRows((rs) => { const n = [...rs]; n[i] = { start: v, end: n[i]?.end ?? '' }; return n; })} />
              <TextInput style={styles.input} accessibilityLabel={`第 ${i + 1} 天几点结束`} placeholder="几点结束（如 16:00）"
                         value={dayRows[i]?.end ?? ''}
                         onChangeText={(v) => setDayRows((rs) => { const n = [...rs]; n[i] = { start: n[i]?.start ?? '', end: v }; return n; })} />
            </View>
          ))}
          {(nPeople > 1 || nDays > 1) && (
            <Text style={styles.mutedLeft}>会拆成 {nPeople * nDays} 个名额（{nPeople} 人 × {nDays} 天），预算平分，每个名额单独招人、单独验收</Text>
          )}
        </>
      )}
      {/* SCN-120 一单多次上门：接单人每次按清单回报 */}
      {!project && (
        <>
          <TextInput style={styles.input} accessibilityLabel="要上门几次" placeholder="要上门几次（可不填）" value={visits}
                     onChangeText={setVisits} keyboardType="numeric" />
          <TextInput style={styles.input} accessibilityLabel="每次要做的事" placeholder="每次要做的事，用顿号分开（如：喂食、换水、铲屎）"
                     value={checklist} onChangeText={setChecklist} />
        </>
      )}
      {/* SCN-119 替别人发单：称呼与到场联系只给成交双方；发之前先问过本人 */}
      <TouchableOpacity onPress={() => setOnBehalf((v) => !v)} accessibilityRole="checkbox" accessibilityLabel="替别人发"
                        accessibilityState={{ checked: onBehalf }}>
        <Text style={onBehalf ? styles.optionActive : styles.option}>{onBehalf ? '☑ ' : '☐ '}替别人发（家人、朋友）</Text>
      </TouchableOpacity>
      {onBehalf && (
        <>
          <TextInput style={styles.input} accessibilityLabel="服务对象称呼" placeholder="服务对象怎么称呼（如：我妈）" maxLength={20}
                     value={recipient} onChangeText={setRecipient} />
          <TextInput style={styles.input} accessibilityLabel="到场联系" placeholder="到场联系谁（成交后才给对方）" maxLength={40}
                     value={onsite} onChangeText={setOnsite} />
          <TouchableOpacity onPress={() => setConsented((v) => !v)} accessibilityRole="checkbox" accessibilityLabel="已经问过本人"
                            accessibilityState={{ checked: consented }}>
            <Text style={consented ? styles.optionActive : styles.option}>
              {consented ? '☑ ' : '☐ '}已经问过本人，他/她同意有人上门、同意把称呼和联系方式给接单的人
            </Text>
          </TouchableOpacity>
        </>
      )}
      {/* SCN-144 服务对象是未成年人（陪练、看护、接送）：不允许单独相处，接单的人要有无犯罪记录证明 */}
      <TouchableOpacity onPress={() => setMinor((v) => !v)} accessibilityRole="checkbox" accessibilityLabel="服务对象是未成年人"
                        accessibilityState={{ checked: minor }}>
        <Text style={minor ? styles.optionActive : styles.option}>{minor ? '☑ ' : '☐ '}服务对象是未成年人（陪练、看护、接送）</Text>
      </TouchableOpacity>
      {minor && (
        <>
          {(Object.keys(GUARDIAN_MODE_LABEL) as GuardianMode[]).map((m) => (
            <TouchableOpacity key={m} onPress={() => setGuardianMode(m)} accessibilityRole="radio" accessibilityState={{ selected: guardianMode === m }}>
              <Text style={guardianMode === m ? styles.optionActive : styles.option}>{guardianMode === m ? '● ' : '○ '}{GUARDIAN_MODE_LABEL[m]}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity onPress={() => setGuardianOk((v) => !v)} accessibilityRole="checkbox" accessibilityLabel="我是监护人或已经监护人同意"
                            accessibilityState={{ checked: guardianOk }}>
            <Text style={guardianOk ? styles.optionActive : styles.option}>{guardianOk ? '☑ ' : '☐ '}我是孩子的监护人，或已经监护人同意</Text>
          </TouchableOpacity>
          <Text style={styles.mutedLeft}>平台不允许和孩子单独相处的安排；接这类单的人要有平台审核通过的无犯罪记录证明。</Text>
        </>
      )}
      <Text style={styles.mutedLeft}>交付成果归谁（必选）</Text>
      {(Object.keys(IP_ASSIGNMENT_LABEL) as IpAssignment[]).map((key) => (
        <TouchableOpacity key={key} onPress={() => setIp(key)}>
          <Text style={ip === key ? styles.optionActive : styles.option}>
            {ip === key ? '● ' : '○ '}{IP_ASSIGNMENT_LABEL[key]}
          </Text>
        </TouchableOpacity>
      ))}
      {!!error && <Text style={styles.error}>{error}</Text>}
      <Button title={project ? '创建并开始拆解' : '发布（线上任务）'} onPress={async () => {
        setError('');
        if (!ip) { setError('请选择交付成果的知识产权归属'); return; }
        try {
          const created = await client.createTask({
            title, category, task_type: project ? 'project' : 'event',
            ...(prefill?.description ? { description: prefill.description } : {}),
            budget_cents: Math.round(parseFloat(budget || '0') * 100),
            ip_assignment: ip,
            ...(!project && nPeople > 1 ? { people_needed: nPeople } : {}),
            ...(!project && nDays > 1 ? { days: nDays, start_date: startDate.trim() || null } : {}),
            ...(!project && (shiftStart.trim() || shiftEnd.trim()) ? { shift_start: shiftStart.trim(), shift_end: shiftEnd.trim() } : {}),
            ...(!project && perDay && nDays > 1 && dayShiftsPayload(dayRows, nDays) ? { day_shifts: dayShiftsPayload(dayRows, nDays) } : {}),
            ...(!project && (parseInt(visits, 10) || 0) > 0 ? { visits_planned: parseInt(visits, 10) } : {}),
            ...(!project && checklist.trim() ? { visit_checklist: checklist.split(/[、,，]/).map((x) => x.trim()).filter(Boolean) } : {}),
            ...(onBehalf ? { on_behalf: true, recipient_label: recipient, onsite_contact: onsite, recipient_consented: consented } : {}),
            ...minorPayload(minor, guardianMode, guardianOk),
            // 项目先存草稿：拆好、说清每一步谁来做之后，只有能开工的步骤发布出去
            is_remote: true, publish_now: !project,
          });
          onDone(created);
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

  // FIN-073 每个按钮一把「这次操作」的键：弱网下再按一次是重试（同一个键，
  // 服务端回放而不是再扣一次）；连按两下读到的也是同一个键。有确定结果后换新键。
  const topupKey = useRef(new OperationKey());
  const withdrawKey = useRef(new OperationKey());

  async function act(fn: () => Promise<unknown>, op?: OperationKey) {
    setError(''); setHint('');
    try {
      await fn();
      op?.settle();
      await load();
    } catch (e) {
      op?.settle(e);
      // CLI-064 拦截理由原样显示。「请先绑定收款账户」这句话只有配上
      // 下面那个绑定表单才有意义——光显示理由，用户照样无处可去。
      setError(apiErrorText(e));
    }
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }}>
      <Text style={styles.title}>我的钱包</Text>
      <ChainEntry />
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
      <Button title={`充值 ${fmtYuan(cents)}（模拟）`} onPress={() => act(() => client.topup(cents, topupKey.current.for(`topup:${cents}`)),
                                               topupKey.current)} />
      <Button title={`提现 ${fmtYuan(cents)}`} color="#6b7280" onPress={() => act(async () => {
        const r = await client.withdraw(cents, withdrawKey.current.for(`withdraw:${cents}`));
        // AML-030/031 tipping-off：大额进人审时**原样显示服务端的中性话术**，
        // 绝不能自己编一句「你的提现触发了风控」——那等于教他下次怎么规避。
        setHint(r.status === 'pending_review' ? (r.message ?? '提现申请已提交，等待处理')
          : r.status === 'processing' ? (r.message ?? '提现已提交银行处理，结果确认后会通知你') : '提现已受理');
      }, withdrawKey.current)} />
      {!!hint && <Text style={styles.mutedLeft}>{hint}</Text>}
      {!!error && <Text style={styles.error}>{error}</Text>}

      <PayoutAccountBlock client={client} />
      {/* TEAM-070（226 号 spec）团队拨款没用完的退回 */}
      <TeamReturnsBlock client={client} onChanged={() => void load()} />
      {/* APP-090 平台服务费发票（136 号 spec） */}
      <InvoicesBlock client={client} />

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
/** ACC-020 实名核验（V125 重写）。
 *
 * 原来是一个「一键实名认证（模拟）」按钮，**把写死的「测试用户」与
 * 证件号 110101199001011234 提交给服务端**：
 *
 * - 第一个点它的人，账号上被记下的真实姓名是「测试用户」；
 * - 之后每一个点它的人都收到 `id_already_bound`（同一证件号只能绑定一个账号），
 *   而那个 `onPress` 没有 try/catch——**点了什么都不会发生**；
 * - 接上真实供应商后，所有人都在提交同一个假身份。
 *
 * 这一段在模拟供应商下「能用」，所以一直没人发现。改成真实表单，
 * 并按服务端的 `status` 区分通过与转人工（HTTP 200 不等于通过）。
 */
export function VerifyIdentityBlock({ client, onDone }: {
  client: PlatformClient; onDone: () => void;
}) {
  const [name, setName] = useState('');
  const [idNo, setIdNo] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  return (
    <View style={{ gap: 8, alignSelf: 'stretch' }}>
      <Text style={styles.mutedLeft}>
        接单与提现需先完成实名认证。证件号只保存不可逆摘要与掩码，不存明文。
      </Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="真实姓名" />
      <TextInput style={styles.input} value={idNo} onChangeText={setIdNo}
                 placeholder="身份证号（15 或 18 位）" autoCapitalize="characters" />
      <Button title={busy ? '正在核验…' : '提交实名认证'} disabled={busy} onPress={async () => {
        setError(''); setNotice('');
        if (name.trim().length < 2 || !/^\d{15}$|^\d{17}[\dXx]$/.test(idNo.trim())) {
          setError('请填写真实姓名与 15 或 18 位身份证号');
          return;
        }
        setBusy(true);
        try {
          const res = await client.verifyIdentity(name.trim(), idNo.trim());
          setNotice(res.status === 'manual_review'
            ? '已提交，正在人工审核。审核完成前暂时不能接单与提现，结果会以通知告诉你。'
            : '实名认证已通过');
          onDone();
        } catch (e) {
          setError(apiErrorText(e));
        } finally {
          setBusy(false);
        }
      }} />
      {!!notice && <Text style={styles.mutedLeft}>{notice}</Text>}
      {!!error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

function MeScreen({ client, me, refresh, onLogout }: {
  client: PlatformClient; me: Me | null; refresh: () => void; onLogout: () => void;
}) {
  // APP-069 三条线挂在「我的」下面，不再加 Tab——七个已经够多了
  const [sub, setSub] = useState<SubScreen | null>(null);
  // LAW-051 问答答不了时服务端给出「发一单法律咨询」，这里要真的送得到——
  // 否则那个按钮点下去什么也不会发生，而它看起来像是能办事的。
  const [askPublish, setAskPublish] = useState<string | null>(null);
  // SCN-133 从服务包的发单模板过来：预填标题、说明、上门次数与清单
  const [askTemplate, setAskTemplate] = useState<PackTaskTemplateBrief | null>(null);
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

  if (askPublish !== null) {
    return (
      <>
        <TouchableOpacity onPress={() => { setAskPublish(null); setAskTemplate(null); }}>
          <Text style={styles.linkRow}>← 返回「不懂就问」</Text>
        </TouchableOpacity>
        <PublishScreen client={client} category={askPublish} template={askTemplate ?? undefined}
                       onDone={() => { setAskPublish(null); setAskTemplate(null); refresh(); }} />
      </>
    );
  }
  if (sub) {
    return <SubScreenHost client={client} screen={sub} onBack={() => setSub(null)}
                          onPublish={(c) => setAskPublish(c)}
                          onPublishTemplate={(t) => { setAskTemplate(t); setAskPublish(t.category); }} />;
  }
  if (!me) return <Text style={styles.muted}>加载中…</Text>;
  return (
    <ScrollView contentContainerStyle={styles.center}>
      <Text style={styles.title}>{me.nickname}</Text>
      <Text style={styles.muted}>
        信用分 {me.credit_score} · 已完成 {me.tasks_completed} 单 · {me.is_verified ? '已实名' : '未实名'}
      </Text>
      {!me.is_verified && <VerifyIdentityBlock client={client} onDone={refresh} />}

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
      {(['workbench', 'notebook', 'packs', 'opc', 'gig', 'capability', 'availability', 'messages', 'invitations', 'applications', 'certifications', 'rights',
         'ask', 'support', 'xapp', 'teams', 'ventures', 'developer'] as SubScreen[]).map((key) => (
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
  root: { flex: 1, backgroundColor: '#f4f5ef' },
  body: { flex: 1, padding: 12 },
  center: { flex: 1, justifyContent: 'center', padding: 24, gap: 12 },
  title: { fontSize: 22, fontWeight: '700', color: '#275c52', textAlign: 'center' },
  input: { backgroundColor: '#fff', borderRadius: 8, padding: 12, borderWidth: 1, borderColor: '#e5e7eb' },
  cardRow: { flexDirection: 'row', backgroundColor: '#fff', borderRadius: 18, padding: 20, marginBottom: 14, borderWidth: 1, borderColor: '#dce5de' },
  cardTitle: { fontSize: 16, fontWeight: '600' },
  price: { color: '#275c52', fontWeight: '700' },
  badge: { color: '#275c52', fontSize: 12 },
  muted: { color: '#6b7280', fontSize: 13, textAlign: 'center', marginTop: 8 },
  mutedLeft: { color: '#6b7280', fontSize: 13 },
  error: { color: '#dc2626' },
  tabbar: { flexDirection: 'row', backgroundColor: '#fff', borderTopWidth: 1, borderColor: '#e5e7eb' },
  topbar: {
    flexDirection: 'row', justifyContent: 'flex-end', gap: 16,
    paddingHorizontal: 16, paddingVertical: 8, backgroundColor: '#fff',
    borderBottomWidth: 1, borderColor: '#e5e7eb',
  },
  topbarItem: { color: '#2f6fed', fontSize: 13 },
  segbar: { flexDirection: 'row', gap: 8, paddingBottom: 8 },
  seg: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14,
    backgroundColor: '#fff', borderWidth: 1, borderColor: '#e5e7eb', color: '#374151',
  },
  segOn: { backgroundColor: '#2f6fed', borderColor: '#2f6fed', color: '#fff' },
  tab: { flex: 1, padding: 14, alignItems: 'center' },
  tabText: { color: '#6b7280' },
  tabActive: { color: '#275c52', fontWeight: '700' },
  option: { color: '#1a1d24', paddingVertical: 6 },
  optionActive: { color: '#275c52', fontWeight: '600', paddingVertical: 6 },
  linkRow: { color: '#275c52', paddingVertical: 10 },
});
