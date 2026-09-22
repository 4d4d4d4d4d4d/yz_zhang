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
  credit_score: number;
  rating_avg: number;
  tasks_completed: number;
  /** TASK-062 这三个服务端一直在返回，**类型里一直没有**——
   *  于是没有任何界面能用上：用户看不到自己的资质过没过，
   *  也看不到信用等级给他带来了什么（CRED-003 的费率折扣就挂在它上面）。 */
  certifications: string[];
  credit_level: string;
  referral_code: string;
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

export interface Decomposition {
  id: number;
  task_id: number;
  items: DecompositionItem[];
  status: 'proposed' | 'confirmed' | 'discarded';
  source: string;
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
  acceptance_criteria: string[];
  last_error: string;
  created_at: string;
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
  members: Array<{ user_id: number; role: string; spend_limit_cents: number }>;
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

export interface ApiKeyView {
  id: number;
  name: string;
  scopes: string[];
  key_prefix: string;
  active: boolean;
  last_used_at: string | null;
  created_at: string;
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
