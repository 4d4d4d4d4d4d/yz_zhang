// 与后端 API 对齐的领域类型（14 号 spec 数据模型）

export interface Me {
  id: number;
  phone: string;
  nickname: string;
  bio: string;
  city: string;
  lat: number | null;
  lng: number | null;
  skills: string[];
  interests: string[];
  is_verified: boolean;
  is_admin: boolean;
  /** SEC-061b 生效的管理员角色（141 号 spec）；不是管理员就是空。没分配过角色的管理员是 ['super'] */
  admin_roles: AdminRoleKey[];
  credit_score: number;
  rating_avg: number;
  tasks_completed: number;
  /** TASK-062 这三个服务端一直在返回，**类型里一直没有**——
   *  于是没有任何界面能用上：用户看不到自己的资质过没过，
   *  也看不到信用等级给他带来了什么（CRED-003 的费率折扣就挂在它上面）。 */
  certifications: string[];
  credit_level: string;
  referral_code: string;
  /** SPACE-023 每周可用时段（北京时间）。只用来回答「截止前有没有空」，不公开给别人 */
  weekly_slots: WeeklySlot[];
  /** SPACE-023 少量接单：还接，但这阵子忙 */
  limited_capacity: boolean;
}

/** TEAM-066 团队邀请链接（147 号 spec） */
export interface TeamInviteLink {
  id: number;
  spend_limit_cents: number;
  uses: number;
  max_uses: number;
  expires_at: string;
  created_at: string;
  state: 'active' | 'used_up' | 'expired' | 'revoked';
}
/** 生成时的响应：令牌只出现这一次 */
export interface TeamInviteCreated extends TeamInviteLink {
  token: string;
  /** 站内路径，例如 /teams/join/xxxx */
  path: string;
  warning: string;
}
export interface TeamInvitePreview {
  team_id: number;
  team_name: string;
  inviter_nickname: string;
  role: 'member';
  spend_limit_cents: number;
  expires_at: string;
  already_member: boolean;
}

/** COOP-060 我收到的合作体邀请（142 号 spec）：接受前要读并签当前版本的风险揭示书 */
export interface VentureInvitationView {
  venture_id: number;
  name: string;
  purpose: string;
  inviter_id: number;
  inviter_nickname: string;
  expires_at: string;
  risk_disclosure_version: string;
}

/** FIN-061 平台财务的一个期间（144 号 spec）：北京时间自然月 / 季度；金额都是正数「收了 / 划出了多少」 */
export interface PlatformFinancePeriod {
  /** 2026-07 或 2026-Q3 */
  period: string;
  start: string;
  end: string;
  fee_cents: number;
  fee_count: number;
  settled_cents: number;
  subsidy_cents: number;
  other_cents: number;
  net_cents: number;
  opening_cents: number;
  closing_cents: number;
  /** 自检：期末 − 期初 = 本期净额 */
  balanced: boolean;
}
export interface PlatformFinancePeriods {
  granularity: 'month' | 'quarter';
  periods: PlatformFinancePeriod[];
}
export interface PlatformFinanceExport {
  filename: string;
  rows: number;
  timezone: string;
  csv: string;
}
export interface PeriodQuery {
  granularity?: 'month' | 'quarter';
  /** YYYY-MM；不填用默认（最近 12 个月 / 4 个季度） */
  start?: string;
  end?: string;
}

/** ADMIN-061 审计日志筛选（143 号 spec）。since / until 是 ISO 时间 */
export interface AuditLogFilter {
  action?: string;
  admin_id?: number;
  target_type?: string;
  target_id?: number;
  since?: string;
  until?: string;
  q?: string;
}
export interface AuditLogExport {
  filename: string;
  rows: number;
  total: number;
  /** 超过 1 万行时只导出最新的 1 万行 */
  truncated: boolean;
  /** 表头里写明的时区，例如「北京时间 UTC+8」 */
  timezone: string;
  csv: string;
}
/** PAY-043 提现复核台筛选（143 号 spec） */
export interface WithdrawQueueFilter {
  status?: 'pending' | 'awaiting_second' | 'approved' | 'rejected';
  user_id?: number;
  min_amount_cents?: number;
  flagged_only?: boolean;
  sort?: 'oldest' | 'largest';
  limit?: number;
  offset?: number;
}

/** SEC-061b 管理员角色（141 号 spec）。拦在服务端；界面只按它决定显示哪些板块 */
export type AdminRoleKey = 'super' | 'support' | 'arbiter' | 'compliance' | 'finance' | 'ops';
export interface AdminRoleDef {
  key: AdminRoleKey;
  label: string;
  scope: string;
}
export interface AdminRoleCatalog {
  roles: AdminRoleDef[];
  mine: AdminRoleKey[];
}
export interface AdminRow {
  user_id: number;
  nickname: string;
  roles: AdminRoleKey[];
  /** 没分配过角色：按超级管理员对待，上线前应当分好 */
  unclassified: boolean;
}
export interface AdminList {
  admins: AdminRow[];
  unclassified: number;
}

/** SPACE-023 每周一个可用时段：d 为 0（周一）~ 6（周日），时间为北京时间 HH:MM */
export interface WeeklySlot {
  d: number;
  from: string;
  to: string;
}

export type TaskStatus =
  | 'draft'
  | 'published'
  | 'matched'
  | 'in_progress'
  | 'pending_acceptance'
  | 'completed'
  | 'cancelled'
  | 'disputed';

export type TaskType = 'service' | 'trade' | 'project' | 'event';

export interface Task {
  id: number;
  creator_id: number;
  executor_id: number | null;
  parent_id: number | null;
  depends_on: number[];
  title: string;
  description: string;
  category: string;
  task_type: TaskType;
  required_skills: string[];
  budget_cents: number;
  pricing: string;
  deposit_cents?: number;
  // IPC-001 知识产权归属。**服务端没有默认值**：不传会被拒。
  // 替当事人猜归属是这条最容易犯的错，所以客户端也必须让用户显式选。
  //
  // TASK-061 **必填而不是可选**：服务端每次都返回它。写成可选的后果不是
  // 「宽容」——是闸门放过「服务端根本不返回」这件事，而那正是改造前的状态：
  // 发布方被强制选归属，执行方在报名前却看不见选的是什么。
  ip_assignment: IpAssignment | '';
  // OUT-002 浮动对价的确定上限。非 outcome 任务恒为 0，同样每次都返回——
  // 一个没给到当事人的「确定上限」，对他不成立（TASK-060）。
  bonus_cents: number;
  is_remote: boolean;
  city: string;
  lat: number | null;
  lng: number | null;
  address_hint: string;
  address_exact: string;
  visibility?: string;
  circle_id?: number | null;
  recurrence?: string;
  recurred_from_id?: number | null;
  status: TaskStatus;
  deadline: string | null;
  reject_count: number;
  created_at: string;
  distance_m?: number | null;
  // TASK-017 详情视角上下文（仅 GET /tasks/{id} 返回）
  my_application_status?: 'pending' | 'accepted' | 'rejected' | 'withdrawn' | null;
  bookmarked?: boolean;
  applications_count?: number; // 仅发布者可见
}

export interface Milestone {
  idx: number;
  title: string;
  amount_cents: number;
  status: 'pending' | 'delivered' | 'released';
}

export type IpAssignment =
  | 'assign'                 // 著作权转让给发布方
  | 'license_exclusive'      // 著作权留执行方，发布方独占使用
  | 'license_nonexclusive'   // 普通许可，执行方可再许可他人
  | 'retain';                // 执行方保留，发布方按约定范围使用

/** CNT-023 关注 / 粉丝列表里的一个人。 */
export interface FollowListItem {
  user_id: number;
  nickname: string;
  followed_at: string;
  /** 访问者自己是否关注了这个人；未登录或就是访问者本人时为 `null`。 */
  viewer_following: boolean | null;
}

/** SYNC-050b / SEC-067 创建任务的请求体——**与服务端 `TaskIn` 逐字段对应**。
 *
 * 此前 `createTask` 的参数是 `Partial<Task> & {...}`，比创建 schema 宽得多：
 * `id` / `status` / `creator_id` / `executor_id` / `created_at` 都在里面。
 * 服务端会把多余的键静默丢掉（pydantic 的默认），所以今天不出事——
 * 但「多收一个字段的代价取决于那个字段是什么」：`status` 是业务错乱，
 * 哪天服务端 schema 不小心加上了同名字段，客户端早就在发了。
 *
 * `ip_assignment` 在服务端 schema 里是可选的，在这里是**必填**：
 * 服务端会拒绝空值（IPC-001），而必填如果没有变成类型上的必填，
 * 它只是一句口头约定（V77 的教训）。 */
export interface TaskCreateInput {
  title: string;
  category: string;
  ip_assignment: IpAssignment;
  description?: string;
  task_type?: string;
  required_skills?: string[];
  budget_cents?: number;
  pricing?: string;
  deposit_cents?: number;
  is_remote?: boolean;
  city?: string;
  lat?: number | null;
  lng?: number | null;
  address_hint?: string;
  address_exact?: string;
  deadline?: string | null;
  visibility?: string;
  circle_id?: number | null;
  recurrence?: string;
  people_needed?: number;
  acceptance_criteria?: string[];
  bonus_cents?: number;
  publish_now?: boolean;
}

/** 与服务端 contract/clauses.py 的 IP_LABELS 一致 */
export const IP_ASSIGNMENT_LABEL: Record<IpAssignment, string> = {
  assign: '著作权转让给我（定制 logo、定制文案）',
  license_exclusive: '独占许可（我独家使用，作者保留著作权与作品集展示）',
  license_nonexclusive: '普通许可（我可使用，作者也可再许可他人）',
  retain: '作者保留（我仅在约定范围内使用）',
};

export interface Contract {
  id: number;
  task_id: number;
  requester_id: number;
  executor_id: number;
  amount_cents: number;
  released_cents: number;
  fee_bps: number;
  // SYNC-005 服务端从保证金功能上线起就返回这两个字段，类型里一直没有。
  // 于是 Web 端压根没写这块显示：执行方接单被冻结的保证金，在合约页上
  // 没有一个字提到，在钱包里只是「冻结中」的一个数字。
  deposit_cents: number;
  deposit_status: string;   // none / held / returned / forfeited
  terms: string;
  status: string;
  signed_by_requester: boolean;
  signed_by_executor: boolean;
  frozen: boolean;
  version: number;
  milestones?: Milestone[];
}

export interface ContentItem {
  id: number;
  author_id: number;
  author_nickname: string;
  kind: 'post' | 'blog' | 'case';
  title: string;
  body: string;
  tags: string[];
  visibility: string;
  circle_id: number | null;
  linked_category: string;
  source_task_id: number | null;
  /** CNT-003/014 配图与视频。此前 contents 表压根没有存媒体的地方。 */
  media_urls: string[];
  /** draft 只有作者自己看得见 */
  status?: string;
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
  /** CNT-024 我是否关注了作者。**自己的内容为 `null`**——「对自己」没有关注这回事
   *  （与 follow-stats 的 `viewer_following` 同一约定）。此前流里的关注按钮永远写着
   *  「关注」，已关注的人点了没有任何变化，也没法从流里取消关注。 */
  author_followed_by_viewer: boolean | null;
  created_at: string;
}

export interface CircleInfo {
  id: number;
  name: string;
  description: string;
  kind: 'interest' | 'skill' | 'local';
  join_policy: 'open' | 'approval';
  owner_id: number;
  skill_tag: string;
  city: string;
  min_credit: number;
  member_count: number;
  conversation_id: number | null;
  my_status: 'active' | 'pending' | null;
  my_role: 'owner' | 'admin' | 'member' | null;
}

export interface InvitationItem {
  id: number;
  task_id: number;
  task_title: string;
  budget_cents: number;
  message: string;
  status: string;
  task_status: string;
}

export interface Wallet {
  available_cents: number;
  escrow_cents: number;
  frozen_cents: number;
}

/** LEDG-004 账单流水一行。`kind` 是账本科目，中文名走 `ledgerKindLabel()`——
 *  **不要在任何一个端里另写一份中文**（V84 立的那条：科目与中文名双向相等）。 */
export interface LedgerRow {
  id: number;
  kind: string;
  amount_cents: number;
  contract_id: number | null;
  memo: string;
  created_at: string;
}

/** MOD-060 封禁影响面。**封禁前就要看见**：这个人手上有几笔在途合约、
 *  多少托管资金会受影响、几个招募中的任务会被下架。
 *  V58 专门算了这些，而管理后台此前直接调 `banUser`——**管理员在盲封**。 */
export interface BanImpactView {
  in_flight_contracts: Array<{
    contract_id: number; task_id: number; status: string;
    amount_cents: number; counterparty_id: number;
  }>;
  in_flight_count: number;
  escrow_at_risk_cents: number;
  open_task_ids: number[];
  open_task_count: number;
  wallet: { available_cents: number; escrow_cents: number; frozen_cents: number };
}

/** ADMIN-060 审计日志一行。**谁批了那笔三万块**——V96 之前这个问题
 *  只能靠查数据库回答，那不是合规底线该有的样子。 */
export interface AdminAuditRow {
  id: number;
  admin_id: number;
  action: string;
  target_type: string;
  target_id: number | null;
  detail: string;
  created_at: string;
}

/** FIN-060 平台自己的钱：佣金收了多少、结算走了多少、账上还剩多少。 */
export interface PlatformFinanceView {
  balance_cents: number;
  total_fee_cents: number;
  settled_cents: number;
  fee_count: number;
}

/** PAY-040 提现复核台的一行。
 *
 *  `flags` 是这笔申请命中的可疑模式，**只出现在管理端响应里**——
 *  AML-030/031 的分界是「合规官看得到为什么，用户只看到中性话术」。
 *  改造前这一行只有 id/user_id/amount_cents：一个风控岗要为三万块
 *  做放行判断，拿到的是一个用户 ID。 */
export interface WithdrawRequestRow {
  id: number;
  user_id: number;
  amount_cents: number;
  /** `pending` / `awaiting_second`（大额已一审、等第二人确认）/ `approved` / `rejected` */
  status: string;
  /** PAY-042 第一次复核人。第二个人必须知道自己在确认谁的意见——
   *  也才看得出「这是不是我自己刚批的那一笔」。 */
  first_approved_by: number | null;
  created_at: string;
  nickname: string;
  is_verified: boolean;
  registered_at: string | null;
  withdrawn_total_cents: number;
  flags: Array<{ pattern: string; detail: string; amount_cents: number }>;
}

/** AML-021 可疑活动。整条线**只对管理员开放**：可疑标记一旦出现在用户
 *  能看到的任何地方（包括数据导出）就构成 tipping-off。 */
export interface SuspiciousActivityRow {
  id: number;
  user_id: number;
  pattern: string;
  pattern_label: string;
  detail: string;
  amount_cents: number;
  ref_type: string;
  ref_id: number;
  status: string;
  review_note: string;
  at: string;
}

/** SC-007 变更单。任务范围一变（「加了两个房间」），这是产品里唯一
 *  能把它落地的路——否则双方只剩取消或纠纷两条对抗路径。
 *
 *  `can_decide` 与服务端 `accept_change` 的准入同源（提案人自己不能接受）：
 *  **客户端不重写这个判断**（UI-075 / TEAM-021 同一条）。 */
export interface ChangeOrderView {
  id: number;
  contract_id: number;
  proposed_by: number;
  new_amount_cents: number;
  reason: string;
  status: string;
  created_at: string;
  can_decide: boolean;
  /** SC-007b 改期：null 表示这张不改截止时间 */
  new_deadline: string | null;
  /** SC-007b 改范围：空串表示这张不改范围 */
  scope_change: string;
}

/** GEO-023 一键求助的回执。
 *
 *  `guidance` 是这一刻**唯一对用户有用的那句话**（「如遇危险请立即拨打 110」），
 *  必须原样显示。此前 SDK 把这个响应声明成 `{ id, notified }`——
 *  服务端从来没返回过这两个键，而**错了这么久没人发现，
 *  因为两端都没有任何一处调用过它**。 */
export interface SosResult {
  ok: boolean;
  guidance: string;
}

/** PAY-030 收款账户。`account_no` 是**脱敏后**的（`6222****0000`）——
 *  服务端本来就不返回完整卡号，任何一端都不要试图拼回去。 */
export interface PayoutAccountView {
  bound: boolean;
  kind?: string;
  account_no?: string;
  holder_name?: string;
}

export interface Recommendation {
  user_id: number;
  nickname: string;
  score: number;
  credit_score: number;
  rating_avg: number;
  skills: string[];
  reasons: string[];
}

export interface DecompositionItem {
  title: string;
  description?: string;
  required_skills: string[];
  budget_cents: number;
  depends_on_idx: number[];
  source?: string;
}

/** AI-DEC-042 每一步谁能闭环（106 号 spec）。依据在 `executor_basis` 里，是可查的事实。 */
export type ExecutorKind = 'ai_closable' | 'needs_human' | 'needs_expert' | 'needs_machine' | 'unknown';

/** AI-DEC-040 叶子四条判据里缺的那几条。 */
export type LeafCriterion = 'deliverable' | 'acceptance' | 'single_owner' | 'budget';

/** 逐层拆解树上的一步（V132）。`parent` 为 null 表示挂在总任务下面。 */
export interface DecompositionNode {
  id: number;
  parent: number | null;
  depth: number;
  title: string;
  description: string;
  required_skills: string[];
  budget_cents: number;
  /** 同一级里必须先完成的步骤 id */
  depends_on: number[];
  deliverable: string;
  acceptance: string;
  single_owner: boolean;
  category: string;
  executor_hint: string;
  source: string;
  /** AI-DEC-048 这一步是模型不可用时回落模板拆出来的 */
  fallback: boolean;
  leaf: boolean;
  missing: LeafCriterion[];
  stop_reason: string;
  /** 停在这里的原因，服务端写好的话，原样显示 */
  stop_note: string;
  expanded: boolean;
  executor_kind: ExecutorKind | '';
  executor_basis: string;
  required_cert: string;
  task_id: number | null;
}

export interface Decomposition {
  id: number;
  task_id: number;
  /** 树形提案里是第一层的只读视图 */
  items: DecompositionItem[];
  status: 'proposed' | 'confirmed' | 'discarded';
  source: string;
  mode: 'flat' | 'tree';
  nodes: DecompositionNode[];
  /** 逐层展开与逐步编辑都要带上它：别的窗口改过就 409 */
  revision: number;
  /** 确认前必须说清的步骤 */
  unresolved: Array<{ id: number; title: string; why: string }>;
  can_expand: boolean;
  fallback: boolean;
  model_calls: number;
  /** 只有 `expandDecomposition` 的响应带：这一次展开了哪些、停在哪、哪些被审核拦下 */
  report?: DecompositionExpandReport;
}

export interface DecompositionExpandReport {
  expanded: Array<number | null>;
  stopped: Array<{ id: number; reason: string }>;
  blocked: string[];
}

export interface DecompositionNodePatch {
  title?: string;
  description?: string;
  budget_cents?: number;
  deliverable?: string;
  acceptance?: string;
  single_owner?: boolean;
  category?: string;
  executor_hint?: '' | 'human' | 'expert' | 'ai';
  depends_on?: number[];
}

export interface TaskTree {
  parent_id: number;
  parent_status: TaskStatus;
  progress_pct: number;
  all_children_completed: boolean;
  children: Array<{
    id: number;
    title: string;
    status: TaskStatus;
    budget_cents: number;
    depends_on: number[];
    executor_id: number | null;
  }>;
}

export interface Conversation {
  id: number;
  kind: 'direct' | 'task';
  task_id: number | null;
  participants: number[];
}

export interface Message {
  id: number;
  sender_id: number;
  content: string;
  risk_flagged: boolean;
  created_at: string;
  /** IM-009 `quote` 是报价卡（内容是结构化 JSON），其余为 `text`。
   *  服务端一直在返回这个键，类型里一直没有——于是没有任何界面能把
   *  报价卡渲染成卡片。 */
  kind: string;
  /** IM-004 已撤回。服务端把内容替换成「[消息已撤回]」并置这个标记；
   *  声明了它，界面才能把撤回的消息显示成灰条而不是一句正常的话。 */
  recalled: boolean;
}

export interface Notice {
  id: number;
  category: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
}

export interface PriceReference {
  sample_size: number;
  p50_cents?: number;
  min_cents?: number;
  max_cents?: number;
  message?: string;
}

// ---- ORC 编排（Agent Harness）----
export type MissionStatus = 'planning' | 'running' | 'blocked' | 'succeeded' | 'failed' | 'cancelled';

export interface Mission {
  id: number;
  owner_id: number;
  goal: string;
  detail: string;
  category: string;
  status: MissionStatus;
  budget_cap_cents: number;
  /** AIO-024 当前占用额度：分发时增加，任务取消/流单时释放（钱没花出去）。 */
  committed_cents: number;
  /** AIO-024 真实花费：任务完成放款后才计入，可与钱包账本交叉核对。 */
  spent_cents: number;
  iteration: number;
  max_iterations: number;
  completion_pct: number;
  /** AIO-020 已完成步的平均评审分。达标要求「全部完成」且「均分过线」。 */
  quality_pct: number;
  model_calls: number;
  /** ORC-061 是否允许把步骤派给平台 AI 助理。**默认关**：发起人授权了
   *  「自动花钱」，不等于授权「活由 AI 做」。 */
  allow_agents: boolean;
  /** AGT-084 是否允许分发时用平台经验工具生成草稿（只出草稿，等你确认）。默认关（131 号 spec） */
  allow_tools: boolean;
  acceptance_criteria: string[];
  last_error: string;
  created_at: string;
}
/** AGT-084 编排用经验工具给某一步生成的草稿 */
export interface MissionToolDraft {
  invocation_id: number;
  unit_id: number;
  version: number;
  label: string;
  text: string;
  status: 'pending' | 'adopted' | 'discarded';
}
export interface MissionDraftDecision {
  step_id: number;
  invocation_id: number;
  status: 'adopted' | 'discarded';
}
/** AGT-091 编排复盘（133 号 spec） */
export interface MissionSummary {
  mission_id: number;
  goal: string;
  status: MissionStatus;
  rounds: number;
  max_rounds: number;
  spent_cents: number;
  committed_cents: number;
  cap_cents: number;
  /** 不含被整改替代的步骤 */
  steps_total: number;
  steps_done: number;
  steps_failed: number;
  remedies: number;
  avg_review_score: number | null;
  drafts_total: number;
  drafts_adopted: number;
  /** 还没结束时为 null */
  duration_days: number | null;
  highlights: string[];
  next: string;
}
/** AGT-092 复盘存进个人知识库的结果（134 号 spec）：再存一次更新同一条 */
export interface MissionSummarySaved {
  note_id: number;
  created: boolean;
  title: string;
  saved_at: string;
}
/** REL-110 本月助手成本（北京时间自然月） */
export interface AssistantCosts {
  month: string;
  agent_tools_cents: number;
  routines_cents: number;
  total_cents: number;
  cap_cents: number;
  remaining_cents: number;
  agent_calls: number;
}

/** AIO-023 编排时间线的一条：做了什么 / 现在怎样 / 下一步。 */
export interface MissionEvent {
  iteration: number;
  action: string;
  summary: string;
  at: string;
}

/** AIO-013 一次评审的留痕（谁判的、用哪版提示词、依据什么）。 */
export interface StepReviewRecord {
  id: number;
  reviewer: string;        // rule | anthropic:<model>
  prompt_version: string;
  verdict: 'pass' | 'revise' | 'fail';
  score: number;
  reasons: string[];
  missing: string[];
  input_digest: string;
  duration_ms: number;
  at: string;
}

export interface MissionStep {
  id: number;
  iteration: number;
  tool: string;          // publish_task：把任务发给平台上的其他人
  title: string;
  task_id: number | null;
  status: 'pending' | 'dispatched' | 'done' | 'failed' | 'superseded';
  observation: string;
  is_remedy: boolean;
  /** ORC-060 这一步派给了哪个平台 AI 助理（没派则为 null）。 */
  agent_user_id: number | null;
  budget_cents?: number;
  /** AIO-022 修复步指向被它接续的原步（幂等键，取代原先的标题匹配）。 */
  parent_step_id: number | null;
  attempt: number;
  acceptance: string[];
  review_verdict: '' | 'pass' | 'revise' | 'fail';
  review_score: number;
  review_missing: string[];
  tool_drafts: MissionToolDraft[];
}

export interface MissionTickResult {
  action: 'dispatched' | 'waiting' | 'completed' | 'blocked' | 'give_up';
  status: MissionStatus;
  total_steps: number;
  done: number;
  failed: number;
  superseded: number;
  completion_pct: number;
  quality_pct: number;
  planned?: number;
  dispatched?: number;
  remedies?: number;
  error?: string;
  issues: Array<{ step_id: number; title: string; observation: string; missing: string[] }>;
  observations: Array<{ step_id: number; task_id: number; task_status: string; observation: string }>;
}

// ── GRW 增长运营（22 号 spec）────────────────────────────────
export interface CouponTemplate {
  id: number;
  title: string;
  kind: 'requester_discount' | 'worker_bonus';
  amount_cents: number;
  percent_bps: number;
  max_discount_cents: number;
  min_order_cents: number;
  category: string;
  newcomer_only: boolean;
  total_quota: number;
  issued_count: number;
  per_user_limit: number;
  valid_days: number;
  active: boolean;
  ends_at: string;
  campaign_id: number | null;
}

export interface MyCoupon {
  id: number;
  status: 'unused' | 'used' | 'expired';
  title: string;
  kind: string;
  min_order_cents: number;
  amount_cents: number;
  percent_bps: number;
  max_discount_cents: number;
  category: string;
  expires_at: string;
  discount_cents: number;
  contract_id: number | null;
}

/** GRW-022 供需健康度的一个「城市×类目」格子。gap 标出缺口方向。 */
export interface MarketCell {
  city: string;
  category: string;
  published: number;
  active_workers: number;
  matched: number;
  fill_rate: number;
  gap: '' | 'supply' | 'demand';
}

// ── FIN 资金合规（25 号 spec）──────────────────────────────────
/** 一次资金分配指令。接存管前是内部账本的镜像，接存管后就是给存管方的报文。 */
export interface SettlementOrderView {
  id: number;
  kind: 'release' | 'milestone' | 'refund' | 'split' | 'verdict';
  total_cents: number;
  backend: 'internal' | 'custody';
  status: string;
  /** 存管方流水号；存管模式下为空即视为异常。 */
  custody_ref: string;
  memo: string;
  at: string;
  /** 金额之和必须等于 total_cents（整数分，不允许尾差蒸发）。 */
  splits: Array<{
    payee_user_id: number;   // 0 = 平台账户
    amount_cents: number;
    purpose: 'payout' | 'fee' | 'refund' | 'compensation' | 'tax';
  }>;
}

// ── LAW 法律效力（26 号 spec）──────────────────────────────────
/**
 * 一条签署留痕。`reliability` 诚实标注证明力：
 *  platform_witness 平台见证（能证明文本未改，**不能独立证明签名人身份**）
 *  qualified        第三方 CA 证书 + 可信时间戳（可靠电子签名）
 */
export interface ContractSignatureView {
  id: number;
  signer_id: number;
  role: 'requester' | 'executor';
  contract_version: number;
  document_hash: string;
  /** 与当前条款是否一致；旧版本签名为 null（条款已变更属正常，不是篡改）。 */
  matches_current_terms: boolean | null;
  signature_valid: boolean;
  reliability: 'platform_witness' | 'qualified';
  provider: string;
  signed_at: string;
}

export interface SignatureReport {
  valid: boolean;
  current_version: number;
  current_document_hash: string;
  signatures: ContractSignatureView[];
  /** 证明力边界说明——诚实标注好过让人误以为全有司法效力。 */
  reliability_note: string;
}

export interface AnchorCoverage {
  total_entries: number;
  third_party_backed_to_seq: number;
  uncovered_entries: number;
  receipts: Array<{
    seq_from: number; seq_to: number; receipt_no: string;
    authority: string; backed: boolean; detail: string; at: string;
  }>;
  note: string;
}

/** LAW-030 一份基础文书的同意状态。 */
export interface AgreementDocument {
  key: string;
  name: string;
  current_version: string;
  /** 用户同意过的版本；从未同意为 null。 */
  agreed_version: string | null;
  needs_reconsent: boolean;
}

/** LAW-031 一个敏感个人信息处理项——每项都必须单独同意、可单独撤回。 */
export interface SensitiveScope {
  key: string;
  purpose: string;
  granted: boolean;
  granted_at: string | null;
  revocable: boolean;
  /** 撤回后会失去什么——必须在用户点撤回**之前**就展示。 */
  revocation_effect: string;
}

export interface AgreementStatus {
  current_version: string;
  documents: AgreementDocument[];
  sensitive_scopes: SensitiveScope[];
  /** KB-080/089 经验的两种用途（复用 / 训练）：选择加入、各自独立、可撤回。
   *  它们不是敏感个人信息，所以单列，不混进 sensitive_scopes。 */
  data_use_scopes: SensitiveScope[];
  /** LAW-032 数据主体权利入口，前端据此渲染，避免「有能力但用户找不到」。 */
  rights: Record<string, string>;
}

/** TAX-021 一笔代扣记录。 */
export interface TaxWithholdingItem {
  id: number;
  contract_id: number;
  kind: string;
  income_cents: number;
  taxable_cents: number;
  withheld_cents: number;
  rule: string;
  note: string;
  at: string;
}

export interface TaxSummary {
  mode: string;
  yearly: Array<{ year: number; income_cents: number; withheld_cents: number; count: number }>;
  items: TaxWithholdingItem[];
  /** 平台出具的是**代扣明细**，不是税务机关的完税证明——前端必须原样展示这句。 */
  disclaimer: string;
}

/** CAP-002 人机验证的客户端配置。 */
export interface CaptchaConfig {
  provider: string;
  /** 直通实现为 false——客户端不必渲染任何东西。 */
  enforcing: boolean;
  /** 站点公钥；hCaptcha / Turnstile / 腾讯云都用它渲染。 */
  site_key: string;
  /** 供应商脚本地址；为空表示退化为手工输入令牌（沙箱/自建）。 */
  script_url: string;
}

/** DSP/DSPC 纠纷。`response_deadline` 与 `appealable` 由服务端算——
 *  答辩期长度与申诉窗口都是服务端配置，客户端不该猜，更不该硬编码。 */
export interface Dispute {
  id: number;
  task_id: number;
  contract_id: number;
  opened_by: number;
  reason: string;
  /** open / appealed（进行中） | resolved / settled（终态） */
  status: string;
  evidence: Record<string, unknown>;
  settlement_proposal: { executor_share_bps: number; proposed_by: number } | null;
  verdict_executor_share_bps: number | null;
  verdict_reason: string;
  split_base_cents: number;
  escalated: boolean;
  resolved_at: string | null;
  /** 被诉方的答辩截止时间；逾期平台可缺席作出处理决定。 */
  response_deadline: string;
  /** 与 `POST /disputes/{id}/appeal` 的准入是同一个判断，不是两份实现。 */
  appealable: boolean;
  /** 仅在按 id / 按任务取回时返回（列表接口不带）。 */
  respondent_id?: number | null;
  respondent_spoke?: boolean;
}

export interface DisputeStatement {
  id: number;
  user_id: number;
  /** opener 发起方 / respondent 被诉方 */
  role: string;
  content: string;
  attachments: string[];
  created_at: string;
}

// =====================================================================
// CLI-062 V73~V79 六个批次的用户侧类型。改造前一个都没有——
// 服务端完整而端上零入口（57 号 spec）。
// =====================================================================

/** AGT 平台自有助理的公开档案。**不含 system_prompt 与成本**：
 *  prompt 泄露等于交出判据之外的实现细节，成本是平台的经营数据。 */
export interface AgentProfileView {
  user_id: number;
  name: string;
  domains: string[];
  max_task_budget_cents: number;
  runs_total: number;
  runs_succeeded: number;
  is_active: boolean;
}

/** `reason` 是这条类型存在的理由：不能接时必须说明为什么。 */
export interface EligibleAgent extends AgentProfileView {
  eligible: boolean;
  reason: string;
}

export interface AgentCriterionResult {
  text: string;
  /** auto 平台判据（阻断交付） / manual 人判（不阻断） */
  kind: string;
  passed: boolean;
  detail?: string;
}

export interface AgentRunView {
  id: number;
  task_id: number;
  /** running / succeeded / escalated / failed */
  status: string;
  /** AGT-013 **自报**的置信度（万分比），正因为自报才需要平台判据压着它。 */
  confidence_bps: number;
  output: string;
  criteria_results: AgentCriterionResult[];
  error: string;
  /** AGT-051 内容审核结论：pass / review / reject（reject 时 output 为空）。 */
  moderation_status: string;
  created_at: string | null;
  finished_at: string | null;
}

/** VER 核验单。`payer_id` 是有意暴露的：升级触发平台付，主动核验发布方付。 */
export interface VerificationOrderView {
  id: number;
  task_id: number;
  /** open / claimed / done / cancelled / expired */
  status: string;
  /** escalation 自动升级 / requested 发布方主动 */
  trigger: string;
  fee_cents: number;
  payer_id: number;
  verifier_id: number | null;
  outcome: string;
  comment: string;
  revised_output: string;
  criteria_results: AgentCriterionResult[];
  deadline: string | null;
  created_at: string | null;
}

export interface VerificationOrderDetail extends VerificationOrderView {
  task_title: string;
  task_description: string;
  category: string;
  acceptance_criteria: Array<{ text: string; kind: string }>;
  agent_output: string;
  agent_confidence_bps: number | null;
  agent_criteria_results: AgentCriterionResult[];
}

/** COOP 风险揭示书。加入前必签，**公开可读**。 */
export interface RiskDisclosure {
  version: string;
  title: string;
  points: string[];
  text: string;
}

export type ContributionKind = 'time' | 'money' | 'ip' | 'resource' | 'other';

export interface VentureView {
  id: number;
  name: string;
  purpose: string;
  category: string;
  status: string;
  founder_id: number;
  created_at: string | null;
}

export interface ShareRow {
  user_id: number;
  share_bps: number;
  valued_cents: number;
}

export interface VentureDetail extends VentureView {
  members: Array<{ user_id: number; role: string; joined_at: string | null }>;
  shares: ShareRow[];
  /** 「已实现」是字面意思：这就是合作体**真的收到**的钱，不是估值。 */
  realized_funds_cents: number;
}

export interface ContributionView {
  id: number;
  user_id: number;
  kind: ContributionKind;
  description: string;
  status: string;
  valued_cents: number;
  confirmed_by: number | null;
  confirm_note: string;
  evidence: string[];
  created_at: string | null;
  /** 与服务端同一判断：自己的贡献不能自己确认。 */
  can_confirm: boolean;
}

/** COOP-040 合规路径：告诉你需要什么，不拦住你。
 *
 *  每一项都带 `why`——**只给一张清单而不说理由，用户不知道哪些能省、
 *  哪些不能，最后要么全不做要么全找律师**。`disclaimer` 必须显示：
 *  这不是法律意见。 */
export interface CompliancePathItem {
  key: string;
  title: string;
  why: string;
  /** ready / todo / na */
  status: string;
  action: string;
}

export interface CompliancePath {
  documents: CompliancePathItem[];
  registrations: CompliancePathItem[];
  notices: string[];
  disclaimer: string;
}

export interface TeamView {
  id: number;
  name: string;
  owner_id: number;
  company_name: string;
  tax_number: string;
  /** none / pending / verified / rejected —— 服务端字段名是 `verify_status`。
   *  这里**曾经写成 `company_status`**：类型对不上却没有任何东西会红，
   *  于是团队页上那行状态在运行时恒为 undefined（CLI-067 抓到的第一条）。 */
  verify_status: string;
  verify_reason: string;
  active: boolean;
}

export interface TeamDetail extends TeamView {
  balance_cents: number;
  my_role: string;
  /** TEAM-050 **月度累计**额度（V87 起），不是单笔——只管单笔的额度
   *  拆单就能绕过，那是 V55 在提现上修过的同一个洞。 */
  my_spend_limit_cents: number;
  members: Array<{ user_id: number; role: string; spend_limit_cents: number; nickname: string }>;
  /** TEAM-030 客户端的「开票」按钮读这个，与服务端同一判断。 */
  invoice_block: string;
  /** TEAM-052 团队月度预算池（0 = 不设池）与本月用量。 */
  monthly_budget_cents: number;
  month_spent_cents: number;
  my_month_spent_cents: number;
}

export interface SpendRequestView {
  id: number;
  requester_id: number;
  amount_cents: number;
  purpose: string;
  status: string;
  task_id: number | null;
  decided_by: number | null;
  decision_reason: string;
  created_at: string;
  /** TEAM-021 「审批」按钮读这个：自己批自己不算审批。 */
  can_decide: boolean;
}

/** TEAM-031 待核验的团队企业信息（76 号 spec）。
 *
 * `license_urls` 是**鉴权**端点，不是匿名能力 URL——营业执照是企业敏感材料。 */
/** QUEUE-011 人审队列概览（78 号 spec）。
 *
 * `chased_elsewhere` 非空表示「这个队列有人盯，但催办在别处」——
 * 提现人审的催办与超时退回在 75 号里。 */
export interface ReviewQueueRow {
  key: string;
  label: string;
  pending: number;
  oldest_wait_hours: number;
  sla_hours: number;
  breached: boolean;
  chased_elsewhere: string;
}

export interface ReviewQueuesView {
  queues: ReviewQueueRow[];
  total_pending: number;
  breached: string[];
}

/** TAX-024 我的发票申请。`at`/`note` 是服务端的字段名，不是 `created_at`。 */
export interface InvoiceRow {
  id: number;
  kind: string;
  contract_id: number;
  amount_cents: number;
  title: string;
  status: string;
  note: string;
  at: string;
}

/** NTF-065 通知开关（77 号 spec）。
 *
 * `always_on` 是**服务端**的必达声明表，界面原样显示 `why`——
 * 抄一份到界面里，那张表一变它就过期了。 */
export interface NotificationPrefsView {
  prefs: Record<string, boolean>;
  always_on_categories: string[];
  always_on: Array<{ category: string; title: string; why: string }>;
}

export interface PendingTeamRow {
  team_id: number;
  name: string;
  owner_id: number;
  owner_nickname: string;
  company_name: string;
  tax_number: string;
  license_urls: string[];
  created_at: string;
}

/** CERT-030 待核验的受限类目资质申请。
 *
 * `name_matches` 是服务端算好的「证件姓名 vs 实名是否一致」——
 * 客户端不重算（第二份实现必然抄漏）。 */
export interface PendingCertificationRow {
  id: number;
  user_id: number;
  name: string;
  holder_name: string;
  cert_number: string;
  issuer: string;
  expires_at: string | null;
  image_urls: string[];
  real_name: string;
  name_matches: boolean;
  status: string;
  created_at: string;
}

/** UMOD-030 机审拿不准的图片。 */
export interface PendingUploadRow {
  name: string;
  url: string;
  owner_id: number;
  labels: string[];
  content_type: string;
  size_bytes: number;
  created_at: string;
}

/** CS-030 工单队列里的一条。 */
export interface AdminTicketRow {
  id: number;
  user_id: number;
  subject: string;
  body: string;
  created_at: string;
}

/** SECEV-030 安全看板。读 DB，所以任何副本看到的都一样。 */
export interface SecurityBoardView {
  banned: Array<{ ip: string; seconds_left: number; reason: string }>;
  watching: Array<{ ip: string; recent_failures: number }>;
  captcha_required_in_window: number;
  threshold: number;
  captcha_after: number;
  ban_seconds: number;
}

export interface ApiKeyView {
  id: number;
  name: string;
  scopes: string[];
  key_prefix: string;
  active: boolean;
  last_used_at: string | null;
  created_at: string;
  /** API-050 自己设的每分钟上限（145 号 spec）；0 = 用平台默认 */
  rate_per_minute: number;
  /** 生效的每分钟上限 */
  effective_rate_per_minute: number;
}
export interface ApiKeyRate {
  id: number;
  rate_per_minute: number;
  effective_rate_per_minute: number;
}

export interface WebhookView {
  id: number;
  url: string;
  events: string[];
  active: boolean;
  consecutive_failures: number;
  /** 连续失败自动停用时写在这里——悄悄停掉比不停更坏。 */
  disabled_reason: string;
}

export interface WebhookDeliveryView {
  id: number;
  event_type: string;
  status: string;
  attempts: number;
  response_code: number | null;
  response_excerpt: string;
  created_at: string;
}

/** CERT 资质申请的状态。`decision_reason` 是被拒时唯一能改进的依据。 */
export interface CertificationApplicationView {
  id: number;
  name: string;
  /** pending / approved / rejected / revoked */
  status: string;
  decision_reason: string;
  expires_at: string | null;
  created_at: string;
}

export interface MachineMandateInput {
  operations: Array<'publish' | 'apply' | 'deliver'>;
  categories: string[];
  per_task_cents: number;
  total_cents: number;
  valid_days: number;
  acknowledge_responsibility: true;
}
export interface MachineMandateView {
  key_id: number;
  principal_id: number;
  operations: string[];
  categories: string[];
  per_task_cents: number;
  total_cents: number;
  used_cents: number;
  expires_at: string;
}
export interface MachineActionView {
  id: number;
  key_id: number;
  principal_id: number;
  operation: string;
  task_id: number;
  fingerprint: string;
  created_at: string;
}

export interface OrganizationRightInput {
  holder_name: string;
  role: 'shareholder' | 'general_partner' | 'limited_partner' | 'cooperator' | 'proprietor';
  subscribed_cents: number;
  paid_cents: number;
  interest_description: string;
  source_document: string;
}
export interface OrganizationRecordInput {
  entity_type: 'project_cooperation' | 'sole_proprietor' | 'limited_company' | 'joint_stock_company' | 'general_partnership' | 'limited_partnership' | 'other';
  jurisdiction: string;
  registered_name: string;
  registration_number: string;
  representative_user_id: number;
  governance_basis: string;
  document_references: string[];
  rights: OrganizationRightInput[];
  acknowledge_record_only: true;
  acknowledge_member_visibility: true;
}
export interface OrganizationRecordView {
  id: number;
  venture_id: number;
  revision: number;
  submitted_by: number;
  entity_type: string;
  jurisdiction: string;
  registered_name: string;
  registration_number: string;
  representative_user_id: number;
  governance_basis: string;
  document_references: string[];
  rights: OrganizationRightInput[];
  record_hash: string;
  created_at: string;
  verification_status: string;
  notice: string;
}

export interface PayoutProposalView {
  id: number; venture_id: number; created_by: number; amount_cents: number; memo: string;
  member_ids: number[]; share_snapshot: ShareRow[]; approvals: Array<{user_id:number;at:string}>;
  status: 'pending'|'rejected'|'executed'; distribution_id: number|null; expires_at: string;
}

/** Configuration inventory, deliberately not a legal/commercial launch approval. */
export interface CommercialReadiness {
  environment: string;
  checks_passed: number;
  checks_total: number;
  configuration_ready: boolean;
  commercial_launch_approved: false;
  checks: Array<{ code: string; passed: boolean; category: string; detail: string }>;
  vendors: Array<{ kind: string; configured_grade: string; registered_non_mock_implementations: string[] }>;
  outside_this_report: string[];
  note: string;
}

export interface SpaceItem { title: string; kind: 'work' | 'article' | 'video' | 'shop' | 'live' | 'service'; summary: string; url: string }
export interface SpaceReview {
  stars: number;
  tags: string[];
  comment: string;
  created_at: string;
}
/** SPACE-029 履约记录：完成单数、评分、评价（复用双盲揭晓规则，不带评价人） */
export interface SpaceTrackRecord {
  tasks_completed: number;
  rating_avg: number;
  reviews_total: number;
  top_tags: string[];
  recent_reviews: SpaceReview[];
}
export interface PersonalSpace { user_id: number; nickname: string; headline: string; introduction: string; theme: 'clay' | 'moss' | 'ink'; kind: 'person' | 'agent' | 'organization'; items: SpaceItem[]; items_count: number; accepting_orders: boolean; track_record?: SpaceTrackRecord }
export interface OwnSpace extends PersonalSpace { revision: number; published: boolean; profile_public: boolean }
export interface SpaceSummary extends Omit<PersonalSpace, 'introduction' | 'items'> { preview: SpaceItem[] }

// ---- KB-070~076 经验子类（108 号 spec）----
export type KnowledgeOutcome = 'completed' | 'disputed' | 'cancelled';

/** 一个子类：这一类活儿通常怎么做、通常多少钱。**每个结论都带样本量与时间范围**（KB-073a）。 */
export interface KnowledgeCluster {
  id: number;
  category: string;
  label: string;
  status: 'active' | 'merged' | 'retired';
  /** 合并掉的子类指向合并去向：历史引用不悬空 */
  merged_into: number | null;
  sample_count: number;
  price_p50_cents: number | null;
  price_p90_cents: number | null;
  duration_p50_days: number | null;
  duration_p90_days: number | null;
  /** 有价格的已完成样本数（价格只从 completed 算） */
  priced_samples: number;
  /** 失败率是子类的属性，不是噪音：纠纷与取消一起给 */
  outcome_mix: Record<KnowledgeOutcome, number>;
  first_sample_at: string | null;
  last_sample_at: string | null;
  /** 近 180 天样本的占比 */
  recent_share: number;
  /** 样本少于门槛：必须标「样本过少，仅供参考」 */
  few_samples: boolean;
  note: string;
  created_by: string;
}

export interface KnowledgeClusterList {
  items: KnowledgeCluster[];
  /** 不是语义模型时，子类检索只是字面相近，界面要说出来 */
  semantic: boolean;
  model: string;
}

export interface KnowledgeClusterDetail extends KnowledgeCluster {
  consensus_steps: Array<{ title: string; count: number }>;
  /** KB-072 偏离共识却成功闭环的做法：**不许被平均掉** */
  dissent: Array<{ steps: string[]; count: number }>;
  /** 只出现过一次的不同做法：不展示文字（避免暴露个案），但数出来 */
  dissent_hidden: number;
  steps_basis: number;
  evidence: { shown: unknown[]; hidden: number; note: string };
}

export interface KnowledgeAdminOverview {
  model: string;
  semantic: boolean;
  states: Record<'pending' | 'assigned' | 'undecided' | 'held' | 'excluded' | 'retracted', number>;
  active_clusters: number;
  thresholds: KnowledgeThresholdRow[];
  held: Record<string, number>;
}

export interface KnowledgeUndecidedRow {
  card_id: number;
  category: string;
  city: string;
  title: string;
  outcome: KnowledgeOutcome;
  state: 'undecided' | 'held';
  hint: { nearest_id?: number | null; nearest_label?: string; similarity?: number | null; why?: string;
          reason?: string; note?: string };
  created_at: string | null;
}

export interface KnowledgeCalibrationPair {
  a: { card_id: number; city: string; title: string; outcome: KnowledgeOutcome; price_actual_cents: number; duration_days: number };
  b: { card_id: number; city: string; title: string; outcome: KnowledgeOutcome; price_actual_cents: number; duration_days: number };
  similarity: number;
}

export interface KnowledgeThresholdView {
  category: string;
  tau_merge: number;
  tau_near: number;
  embedding_model: string;
  labeled_pairs: number;
  errors: number;
  calibrated_at: string | null;
}

// ---- KB-080~089 / AGT-080~083 经验变成能被调用的单元（109 号 spec）----
export type ReusableUnitKind = 'price_hint' | 'checklist' | 'procedure' | 'skill_tool';

/** 适用条件：**排除条件必填**——只说「适用于什么」的单元，会在不适用的场合被照样调用。 */
export interface ReusableUnitApplicability {
  category: string;
  cities: string[];
  budget_min_cents: number | null;
  budget_max_cents: number | null;
  exclusions: string[];
}

/** 验证状态：每次使用的结果（闭环 / 返工 / 失败）回流到这里（KB-084）。 */
export interface ReusableUnitValidation {
  status: 'unvalidated' | 'validated' | 'needs_review';
  uses: number;
  closed: number;
  reworked: number;
  failed: number;
}

/** 一个可复用单元：从子类蒸馏出来，带来源、适用与排除条件、验证状态、两个独立授权位。 */
export interface ReusableUnit {
  id: number;
  cluster_id: number;
  kind: ReusableUnitKind;
  kind_label: string;
  title: string;
  version: number;
  status: 'active' | 'needs_review' | 'retired';
  applicability: ReusableUnitApplicability;
  validation: ReusableUnitValidation;
  /** 来源样本数：只算双方都同意经验复用的那几单 */
  sample_count: number;
  scope: 'private' | 'project' | 'platform';
  /** KB-086 复用授权与训练授权是两回事，各自独立 */
  reuse_license: boolean;
  train_license: boolean;
  created_at: string | null;
}

export interface ReusableUnitContributor {
  user_id: number;
  nickname: string;
}

export interface ReusableUnitDetail extends ReusableUnit {
  /** 随类型不同：报价提示是分布，验收清单是条目，分解流程是步骤，工具是工具名与清单 */
  content: Record<string, unknown>;
  /** 可执行工具的权限清单：读什么、写什么、花不花钱、发不发消息（AGT-081） */
  manifest: Record<string, unknown>;
  est_cost_cents: number;
  /** KB-085 贡献者：只列同意了经验复用的人 */
  contributors: ReusableUnitContributor[];
}

/** AGT-083 经验工具的产出：**只是草稿**，带「未经人工确认」标签，可丢弃。 */
export interface ExperienceToolDraft {
  invocation_id: number;
  draft: boolean;
  label: string;
  text: string;
  exclusions: string[];
  /** 这次调用受益的贡献者人数 */
  contributors: number;
}

export interface ReusableUnitDistillInput {
  kind: ReusableUnitKind;
  title?: string;
  cities?: string[];
  budget_min_cents?: number | null;
  budget_max_cents?: number | null;
  exclusions: string[];
  scope?: 'private' | 'project' | 'platform';
  reuse_license: boolean;
  train_license: boolean;
  tool?: string;
}

export interface KnowledgeThresholdRow extends KnowledgeThresholdView {
  /** 阈值是用旧模型标定的：归并会被拒，须重标 */
  stale: boolean;
}

// ---- PWB 个人工作台（116 号 spec）----
export type WbStatus = 'todo' | 'doing' | 'blocked' | 'done' | 'dropped';
export type WbProgressSource = 'manual' | 'children' | 'platform';
export interface WbProject {
  id: number;
  name: string;
  color: 'clay' | 'moss' | 'ink' | 'sky' | 'sun';
  archived: boolean;
  sort: number;
  created_at: string;
}
export interface WbLinkedTask {
  id: number;
  title: string;
  status: string;
  status_name: string;
}
export interface WbItem {
  id: number;
  project_id: number | null;
  parent_id: number | null;
  title: string;
  notes: string;
  status: WbStatus;
  status_name: string;
  /** 0 低 / 1 普通 / 2 高 / 3 紧急 */
  priority: number;
  category: string;
  due_at: string | null;
  remind_at: string | null;
  /** 有清单子项时按子项算、关联平台任务时跟平台走，都不能手填——看 `progress_source` */
  progress: number;
  progress_source: WbProgressSource;
  children_total: number;
  children_done: number;
  tags: string[];
  linked_task: WbLinkedTask | null;
  revision: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}
export interface WbItemDetail extends WbItem {
  children: WbItem[];
}
export interface WbItemInput {
  title: string;
  notes?: string;
  project_id?: number | null;
  parent_id?: number | null;
  status?: WbStatus;
  priority?: number;
  category?: string;
  due_at?: string | null;
  remind_at?: string | null;
  progress?: number;
  tags?: string[];
  linked_task_id?: number | null;
}
/** 改任务：只传要改的字段；带上 `revision` 可以防止两台设备互相覆盖 */
export interface WbItemPatch {
  revision?: number;
  title?: string;
  notes?: string;
  project_id?: number | null;
  status?: WbStatus;
  priority?: number;
  category?: string;
  due_at?: string | null;
  remind_at?: string | null;
  progress?: number;
  tags?: string[];
  linked_task_id?: number | null;
  sort?: number;
}
export interface WbLog {
  id: number;
  kind: 'note' | 'status' | 'progress' | 'assistant';
  body: string;
  created_at: string;
}
export interface WbStep {
  title: string;
  note: string;
}
export interface WbBreakdown {
  source: string;
  steps: WbStep[];
  /** KB-104 助手参考了哪几条自己的笔记（V147 起；更早的服务端没有这个字段） */
  references?: NbReference[];
}
export interface WbPlatformSection {
  to_choose: { task_id: number; title: string; applicants: number }[];
  to_accept: { task_id: number; title: string }[];
  executing: { task_id: number; title: string; status: string; status_name: string }[];
}
export interface WbOverview {
  counts: { overdue: number; today: number; doing: number; blocked: number; stale: number; done_this_week: number; open: number };
  overdue: WbItem[];
  today: WbItem[];
  doing: WbItem[];
  blocked: WbItem[];
  stale: WbItem[];
  done_this_week: WbItem[];
  projects: { id: number; name: string; color: string; total: number; done: number; progress: number }[];
  platform: WbPlatformSection;
  summary: string;
}
export interface WbMemory {
  id: number;
  content: string;
  created_at: string;
}
export type WbRoutineKind = 'digest' | 'review' | 'reminder';
export type WbFreq = 'once' | 'daily' | 'weekly' | 'monthly';
export interface WbRoutine {
  id: number;
  name: string;
  kind: WbRoutineKind;
  freq: WbFreq;
  time_of_day: string;
  weekday: number;
  monthday: number;
  run_at: string | null;
  note: string;
  item_id: number | null;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: '' | WbRunStatus;
  failures: number;
  /** REL-101 运行合同（130 号 spec）：超时、失败后重试几次、重试用尽时是否降级交付 */
  timeout_ms: number;
  max_retries: number;
  degrade: boolean;
  /** 当前这次排期已经重试了几次；在重试中时 pending_slot_at 是原来那次排期 */
  retry_count: number;
  pending_slot_at: string | null;
}
/** ok 送达；degraded 降级送达；retrying 失败、等退避后重试；skipped 数据源没就绪、这次不跑；failed 失败 */
export type WbRunStatus = 'ok' | 'failed' | 'retrying' | 'skipped' | 'degraded';
export interface WbRoutineInput {
  name: string;
  kind: WbRoutineKind;
  freq: WbFreq;
  time_of_day?: string;
  weekday?: number;
  monthday?: number;
  run_at?: string | null;
  note?: string;
  item_id?: number | null;
  enabled?: boolean;
  timeout_ms?: number;
  max_retries?: number;
  degrade?: boolean;
}
export interface WbRoutineRun {
  id: number;
  status: WbRunStatus;
  output: string;
  started_at: string;
  /** REL-105 运行日志：哪次排期、第几次尝试、耗时、成本、错误类型（只记类型） */
  slot_at: string | null;
  attempt: number;
  duration_ms: number;
  cost_cents: number;
  error_kind: string;
  degraded: boolean;
}
export interface WbRoutineErrorKind {
  kind: string;
  count: number;
}
export interface WbRoutineContract {
  timeout_ms: number;
  max_retries: number;
  degrade: boolean;
}
export interface WbRoutineHealth {
  routine_id: number;
  runs: number;
  /** 最终结果里成功的比例；还没有最终结果时为 null */
  success_rate: number | null;
  delivered: number;
  degraded: number;
  retries: number;
  skipped: number;
  failed: number;
  p50_ms: number | null;
  p95_ms: number | null;
  error_kinds: WbRoutineErrorKind[];
  cost_cents: number;
  contract: WbRoutineContract;
}
export interface WbRoutinePatch {
  name?: string;
  freq?: WbFreq;
  time_of_day?: string;
  weekday?: number;
  monthday?: number;
  run_at?: string | null;
  note?: string;
  enabled?: boolean;
  timeout_ms?: number;
  max_retries?: number;
  degrade?: boolean;
}

// ---- SPACE-024 / AI-DEC-021 合作驾驶舱（120 号 spec）----
export interface CockpitBudget {
  planned_cents: number;
  allocated_cents: number;
  committed_cents: number;
  paid_cents: number;
  remaining_cents: number;
}
export interface CockpitAlert {
  task_id: number;
  kind: 'dispute' | 'overdue' | 'no_applicants' | 'to_accept' | 'over_budget';
  text: string;
}
export interface CockpitNode {
  id: number;
  parent_id: number | null;
  title: string;
  status: string;
  status_name: string;
  budget_cents: number;
  is_container: boolean;
  depends_on: number[];
  /** 还没完成的前置步骤：这一步卡在它们身上 */
  blocked_by: number[];
  executor_id: number | null;
  executor_nickname: string | null;
  deadline: string | null;
  overdue: boolean;
  on_critical_path: boolean;
  in_dispute: boolean;
}
export interface Cockpit {
  task_id: number;
  title: string;
  status: string;
  progress_pct: number;
  steps_total: number;
  steps_done: number;
  budget: CockpitBudget;
  /** 剩余步骤最多的那条依赖链（叶子 id，按先后） */
  critical_path: number[];
  alerts: CockpitAlert[];
  nodes: CockpitNode[];
}

// ---- KB-100 个人知识库（122 号 spec）：只属于本人 ----
export type NbKind = 'note' | 'link' | 'minutes';
export type NbStatus = 'inbox' | 'filed' | 'archived';
export interface NbNoteBrief {
  id: number;
  kind: NbKind;
  title: string;
  url: string;
  status: NbStatus;
  tags: string[];
  pinned: boolean;
  project_id: number | null;
  revision: number;
  /** 列表里是正文开头；带 q 检索时是命中处的摘录 */
  excerpt: string;
  created_at: string;
  updated_at: string;
}
export interface NbNote extends NbNoteBrief {
  body: string;
}
export interface NbNoteInput {
  body?: string;
  title?: string;
  url?: string;
  kind?: NbKind;
  tags?: string[];
  status?: NbStatus;
  project_id?: number | null;
}
export interface NbNotePatch {
  revision?: number;
  title?: string;
  body?: string;
  url?: string;
  kind?: NbKind;
  tags?: string[];
  status?: NbStatus;
  pinned?: boolean;
  project_id?: number | null;
}
export interface NbTagCount {
  tag: string;
  count: number;
}
export interface NbSummary {
  total: number;
  inbox: number;
  archived: number;
  methods: number;
  limit: number;
  tags: NbTagCount[];
}
export interface NbReference {
  note_id: number;
  title: string;
  snippet: string;
  score: number;
}
export interface NbCitation {
  n: number;
  note_id: number;
  title: string;
  snippet: string;
}
export interface NbAnswer {
  /** 摘录式：每一句都来自自己的笔记，不编 */
  mode: 'extractive';
  answer: string;
  citations: NbCitation[];
}
export interface NbTodoDraft {
  title: string;
  due_at: string | null;
  line: string;
}
export interface NbTodoInput {
  title: string;
  due_at?: string | null;
}
export interface NbMethod {
  id: number;
  name: string;
  description: string;
  steps: WbStep[];
  source_note_ids: number[];
  uses: number;
  created_at: string;
  updated_at: string;
}
export interface NbMethodDraft {
  name: string;
  steps: WbStep[];
  source_note_ids: number[];
  /** numbered：取的是编号步骤；bullets：圆点列表；none：没找到步骤，请手写 */
  found: 'numbered' | 'bullets' | 'none';
}
export interface NbExport {
  filename: string;
  notes: number;
  methods: number;
  markdown: string;
}

// ---- PACK-100 场景包与平台资产（123 号 spec） ----
export type PackSegment = 'opc' | 'gig' | 'creator' | 'studio' | 'buyer' | 'general';
export interface PackAssistant {
  key: string;
  name: string;
  persona: string;
  inputs: string[];
  outputs: string[];
  forbidden: string[];
  tools: string[];
  /** 人工关口（中文说明）：这些事助手只给草稿，必须本人确认 */
  human_gates: string[];
}
export interface PackMethodBrief {
  key: string;
  name: string;
  steps: number;
}
export interface PackKnowledgeBrief {
  key: string;
  title: string;
  kind: 'rule' | 'policy' | 'howto';
  source: string;
  valid_until: string | null;
}
export interface PackRoutineBrief {
  key: string;
  name: string;
  freq: string;
  time_of_day: string;
}
export interface PackTaskTemplateBrief {
  key: string;
  title: string;
  category: string;
  /** 说明（含验收标准），用来预填发布页 */
  description: string;
}
export interface PackAssets {
  assistants: PackAssistant[];
  methods: PackMethodBrief[];
  knowledge: PackKnowledgeBrief[];
  routines: PackRoutineBrief[];
  task_templates: PackTaskTemplateBrief[];
}
export interface ScenarioPackCard {
  key: string;
  version: number;
  title: string;
  segment: PackSegment;
  summary: string;
  pains: string[];
  enabled: boolean;
  enabled_version: number | null;
  upgrade_available: boolean;
  active_users: number;
  assets: PackAssets;
  published_at: string | null;
}
export interface PackInstalledCounts {
  methods: number;
  notes: number;
  routines: number;
}
export interface PackEnableResult extends ScenarioPackCard {
  installed: PackInstalledCounts;
}
export interface PackCitation {
  n: number;
  kind: 'pack' | 'note' | 'legal' | 'tool' | 'experience';
  title: string;
  snippet: string;
  source: string;
  valid_until: string | null;
  expired: boolean;
  note_id: number | null;
}
export interface PackRemedy {
  action: 'publish_task';
  category: string;
  label: string;
}
export interface PackAnswer {
  assistant: string;
  gates: string[];
  gate_notice: string;
  refused: boolean;
  answer: string;
  citations: PackCitation[];
  remedy: PackRemedy | null;
}
export interface PackMetrics {
  active: number;
  enabled_total: number;
  asks_30d: number;
  unanswered_30d: number;
  helpful_30d: number;
  unhelpful_30d: number;
  unanswered_rate: number | null;
  helpful_rate: number | null;
}
export interface ScenarioPackAdminRow {
  id: number;
  key: string;
  version: number;
  title: string;
  segment: PackSegment;
  status: 'draft' | 'review' | 'published' | 'superseded' | 'retired';
  score: number;
  created_by: number;
  reviewed_by: number | null;
  published_at: string | null;
  retired_reason: string;
  updated_at: string;
  definition: Record<string, unknown>;
}
export interface ScenarioPackAdminListRow extends ScenarioPackAdminRow {
  metrics: PackMetrics;
}
export interface PackValidation {
  ok: boolean;
  problems: string[];
  score: number | null;
}
export interface RadarSignal {
  source: 'search_gap' | 'stuck_demand' | 'pack_gap';
  key: string;
  title: string;
  evidence: string;
  people: number;
  suggested: Record<string, number>;
}
export interface PackImportResult {
  created: string[];
  skipped: string[];
  invalid: { file: string; problems: string[] }[];
}

// ---- OPC-100 一人公司：财税与合规（124 号 spec）。只出底稿与提醒，申报 / 开票 / 签字由本人在官方渠道完成 ----
export type OpcEntity = 'individual' | 'sole_prop' | 'company';
export type OpcVat = 'none' | 'small_scale' | 'general';
export interface OpcProfileView {
  entity: OpcEntity;
  vat: OpcVat;
  vat_period: 'month' | 'quarter';
  small_low_profit: boolean;
  /** 还没填过时是 false（按「个人」推算） */
  configured: boolean;
}
export interface OpcProfileInput {
  entity: OpcEntity;
  vat: OpcVat;
  vat_period?: 'month' | 'quarter';
  small_low_profit?: boolean;
}
export interface OpcEntryRow {
  id: number;
  /** YYYY-MM-DD（日期，不是时间点） */
  occurred_on: string;
  kind: 'income' | 'expense';
  amount_cents: number;
  tax_cents: number;
  category: string;
  counterparty: string;
  invoice_no: string;
  invoice_kind: 'none' | 'ordinary' | 'special';
  note: string;
  source: 'manual' | 'platform';
  created_at: string;
}
export interface OpcEntryInput {
  occurred_on: string;
  kind: 'income' | 'expense';
  amount_cents: number;
  tax_cents?: number;
  category?: string;
  counterparty?: string;
  invoice_no?: string;
  invoice_kind?: 'none' | 'ordinary' | 'special';
  note?: string;
}
export interface OpcCategoryTotal {
  kind: 'income' | 'expense';
  category: string;
  amount_cents: number;
}
export interface OpcVatCheck {
  period_kind: 'month' | 'quarter';
  sales_cents: number;
  limit_cents: number;
  over: boolean;
}
export interface OpcSummary {
  period: string;
  start: string;
  end: string;
  kind: 'month' | 'quarter' | 'year';
  income_cents: number;
  expense_cents: number;
  profit_cents: number;
  by_category: OpcCategoryTotal[];
  platform_withheld_cents: number;
  entries: number;
  vat_check: OpcVatCheck | null;
  notes: string[];
  disclaimer: string;
}
export interface OpcExport {
  filename: string;
  rows: number;
  csv: string;
}
export interface OpcDeadline {
  /** YYYY-MM-DD */
  date: string;
  kind: 'vat' | 'cit' | 'iit' | 'annual';
  title: string;
  detail: string;
}
export interface OpcCalendar {
  configured: boolean;
  items: OpcDeadline[];
  notice: string;
}
export interface ContractFinding {
  level: 'high' | 'medium' | 'info';
  clause: string;
  finding: string;
  suggestion: string;
}
export interface ContractReview {
  findings: ContractFinding[];
  amounts: string[];
  dates: string[];
  disclaimer: string;
}

// ---- GIG-100 接单者：现在有空、常用地点、附近、顺路、报价参考（125 号 spec）。位置只存约 1 公里精度 ----
export interface GigAvailabilityView {
  available: boolean;
  until: string | null;
  radius_km: number | null;
  categories: string[];
  /** 这一段「有空」里已经推了几条（上限 6） */
  pushed: number;
}
export interface GigAvailabilityInput {
  lat: number;
  lng: number;
  radius_km?: number;
  hours?: number;
  categories?: string[];
}
export interface GigPlaceRow {
  id: number;
  name: string;
  lat: number;
  lng: number;
}
export interface GigTaskCard {
  task_id: number;
  title: string;
  category: string;
  budget_cents: number;
  /** 扣平台服务费后的到手（个税另算） */
  net_cents: number;
  address_hint: string;
  city: string;
  deadline: string | null;
  /** 附近：直线距离；顺路：没有 */
  distance_m?: number;
  /** 顺路：多走的路（直线估算） */
  detour_m?: number;
  from_start_m?: number;
}
export interface GigNearby {
  radius_km: number;
  items: GigTaskCard[];
  notice: string;
}
export interface GigAlong {
  to: string;
  max_detour_km: number;
  items: GigTaskCard[];
  notice: string;
}
export interface GigQuote {
  task_id: number | null;
  category: string;
  city: string;
  sample_size: number;
  p50_cents: number | null;
  min_cents: number | null;
  max_cents: number | null;
  budget_cents: number | null;
  suggested_cents: number | null;
  net_cents: number | null;
  basis: string[];
  disclaimer: string;
}

// ---- PROF-100 任务画像与能力画像（126 号 spec） ----
export interface TaskProfilePrice {
  sample_size: number;
  p50_cents: number | null;
  min_cents: number | null;
  max_cents: number | null;
  /** below_min / below_median / around_median / above_median / unknown */
  position: 'below_min' | 'below_median' | 'around_median' | 'above_median' | 'unknown';
}
export interface TaskProfileRisk {
  kind: string;
  text: string;
}
export interface TaskProfileCheck {
  key: string;
  ok: boolean;
  /** 没通过时怎么补；通过时是空串 */
  hint: string;
}
export interface TaskProfile {
  category: string;
  mode: 'remote' | 'onsite';
  declared_skills: string[];
  /** 从标题与说明里认出来的技能（不含已写明的） */
  inferred_skills: string[];
  size: 'small' | 'medium' | 'large' | 'unknown';
  price: TaskProfilePrice;
  risks: TaskProfileRisk[];
  /** 0~1：说明完整度 */
  completeness: number;
  checks: TaskProfileCheck[];
  /** SCN-106 创作类的单才有（140 号 spec）：需求单九项写到了哪些；不计入说明完整度 */
  brief: TaskBrief | null;
}
export interface TaskBriefItem {
  name: string;
  ok: boolean;
  /** 没写时该补的那句话 */
  ask: string;
}
export interface TaskBrief {
  items: TaskBriefItem[];
  missing: number;
}
export interface TaskProfileView extends TaskProfile {
  task_id: number;
}
export interface TaskDraftInput {
  title?: string;
  description?: string;
  category?: string;
  budget_cents?: number;
  is_remote?: boolean;
  city?: string;
  lat?: number | null;
  deadline?: string | null;
  required_skills?: string[];
  acceptance_criteria?: string[];
}
export interface CapabilityCategory {
  category: string;
  completed: number;
  rating_avg: number | null;
}
export interface CapabilitySkill {
  skill: string;
  /** true：有成交佐证；false：只是自述 */
  evidenced: boolean;
}
export interface CapabilityProfile {
  user_id: number;
  tasks_completed: number;
  categories: CapabilityCategory[];
  skills: CapabilitySkill[];
  certifications: string[];
  /** 样本少于 3 单时为 null */
  on_time_rate: number | null;
  rework_rate: number | null;
  reply_hours_median: number | null;
  has_weekly_slots: boolean;
  limited_capacity: boolean;
  note: string;
  /** 只有本人看得到；对外是 null */
  disputes: number | null;
}

// ---- INF-100 影响力与专家等级（127 号 spec） ----
export type InfluenceTier = 'newcomer' | 'skilled' | 'expert' | 'expert_senior';
export const INFLUENCE_TIER_NAMES: Record<InfluenceTier, string> = {
  newcomer: '新手', skilled: '熟手', expert: '专家', expert_senior: '资深专家',
};
/** 对外看到的一个类目 */
export interface InfluenceCategory {
  category: string;
  /** 衰减后的影响力（取整） */
  points: number;
  tier: InfluenceTier;
  tier_name: string;
  completed: number;
  rating_avg: number | null;
}
/** 本人看到的一个类目：多了担保占用、可用额度与升级还差什么 */
export interface InfluenceMyCategory {
  category: string;
  points: number;
  tier: InfluenceTier;
  tier_name: string;
  completed: number;
  rating_avg: number | null;
  locked: number;
  available: number;
  gaps: string[];
}
export interface InfluenceEventRow {
  id: number;
  category: string;
  /** earn_task / earn_publish / earn_vouch / slash_dispute / slash_vouch / restore */
  kind: string;
  points: number;
  reason: string;
  created_at: string;
}
export interface InfluenceVouchRow {
  id: number;
  voucher_id: number;
  voucher_nickname: string;
  subject_id: number;
  subject_nickname: string;
  category: string;
  task_id: number | null;
  stake: number;
  status: 'active' | 'released' | 'slashed' | 'withdrawn';
  note: string;
  created_at: string;
  resolved_at: string | null;
}
export interface InfluenceMine {
  categories: InfluenceMyCategory[];
  events: InfluenceEventRow[];
  vouches_given: InfluenceVouchRow[];
  vouches_received: InfluenceVouchRow[];
  rules: string;
}
export interface InfluenceVouchedSummary {
  category: string;
  vouchers: number;
  stake: number;
}
export interface InfluencePublic {
  user_id: number;
  categories: InfluenceCategory[];
  vouched: InfluenceVouchedSummary[];
}
export interface InfluenceLeaderRow {
  user_id: number;
  nickname: string;
  tier: InfluenceTier;
  tier_name: string;
  points: number;
  completed: number;
}
export interface InfluenceLeaderboard {
  category: string;
  items: InfluenceLeaderRow[];
}
export interface InfluenceVouchInput {
  subject_id: number;
  category: string;
  /** 为某一单作保；不给 = 整个类目（180 天后自动释放） */
  task_id?: number | null;
  stake: number;
  note?: string;
}
export interface InfluenceSnapshotView {
  id: number;
  taken_at: string;
  merkle_root: string;
  leaves: number;
  anchor_seq: number | null;
}
/** 最近一次快照；还没做过是 null */
export interface InfluenceLatestSnapshot {
  snapshot: InfluenceSnapshotView | null;
}
export interface InfluenceProofItem {
  category: string;
  points: number;
  leaf: string;
  path: string[];
  verified: boolean;
}
export interface InfluenceProof {
  snapshot: InfluenceSnapshotView | null;
  items: InfluenceProofItem[];
}

// ---- SBX-100 端侧隐私沙箱（128 号 spec） ----
export interface SandboxState {
  enabled: boolean;
  since: string | null;
  /** 开着时被拦下的云端 AI 接口数 */
  blocked_endpoints: number;
  note: string;
}
export interface SandboxModelRow {
  id: number;
  key: string;
  name: string;
  family: string;
  params_b: number;
  quant: string;
  file_format: string;
  size_mb: number;
  sha256: string;
  url: string;
  license: string;
  min_ram_gb: number;
  languages: string[];
  skills: string[];
  note: string;
  published_at: string | null;
}
export interface SandboxModelList {
  items: SandboxModelRow[];
  note: string;
}
export interface SandboxModelAdminRow {
  id: number;
  key: string;
  name: string;
  family: string;
  params_b: number;
  quant: string;
  file_format: string;
  size_mb: number;
  sha256: string;
  url: string;
  license: string;
  min_ram_gb: number;
  languages: string[];
  skills: string[];
  note: string;
  published_at: string | null;
  status: 'draft' | 'published' | 'retired';
  created_by: number;
  reviewed_by: number | null;
  retired_reason: string;
  created_at: string;
}
export interface SandboxModelInput {
  key: string;
  name: string;
  family?: string;
  params_b?: number;
  quant?: string;
  file_format?: string;
  size_mb?: number;
  sha256?: string;
  url?: string;
  license?: string;
  min_ram_gb?: number;
  languages?: string[];
  skills?: string[];
  note?: string;
}

// ---- REL-107 助手专家的角色契约（130 号 spec） ----
export interface AssistantContractItem {
  key: string;
  name: string;
}
export interface AssistantContract {
  key: string;
  name: string;
  persona: string;
  inputs: string[];
  outputs: string[];
  forbidden: string[];
  tools: AssistantContractItem[];
  human_gates: AssistantContractItem[];
  fallback_category: string;
}

// ---- SKL-100 技能概念表（135 号 spec） ----
export interface SkillConceptView {
  name: string;
  aliases: string[];
}
export interface SkillConceptList {
  items: SkillConceptView[];
}
export interface SkillNormalized {
  skill: string;
  /** 会按这个规范名去匹配；认不出时就是原样 */
  canonical: string;
  known: boolean;
}
export interface SkillNormalizeResult {
  items: SkillNormalized[];
}
export interface SkillConceptRow {
  id: number;
  name: string;
  aliases: string[];
  status: 'active' | 'retired';
  updated_by: number;
  updated_at: string;
}
export interface SkillConceptAdminView {
  effective: SkillConceptView[];
  overrides: SkillConceptRow[];
}
