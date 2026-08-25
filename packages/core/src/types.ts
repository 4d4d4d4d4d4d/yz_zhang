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

export interface Contract {
  id: number;
  task_id: number;
  requester_id: number;
  executor_id: number;
  amount_cents: number;
  released_cents: number;
  fee_bps: number;
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
