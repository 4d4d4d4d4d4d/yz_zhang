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
