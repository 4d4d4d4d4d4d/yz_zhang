// 平台 API SDK：Web 与 App 共用（13 号 spec「两端共享同一 API/BFF」）
import type {
  CircleInfo,
  ContentItem,
  Contract,
  Decomposition,
  DecompositionItem,
  Conversation,
  InvitationItem,
  Me,
  Message,
  Notice,
  PriceReference,
  Recommendation,
  Task,
  TaskTree,
  Wallet,
} from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface ClientOptions {
  baseUrl: string;
  getToken: () => string | null;
  fetchImpl?: typeof fetch;
}

export class PlatformClient {
  constructor(private opts: ClientOptions) {}

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const doFetch = this.opts.fetchImpl ?? fetch;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = this.opts.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await doFetch(`${this.opts.baseUrl}/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) {
      const detail = data?.detail;
      throw new ApiError(
        res.status,
        detail?.code ?? 'error',
        detail?.message ?? (typeof detail === 'string' ? detail : '请求失败'),
      );
    }
    return data as T;
  }

  // ---- auth / account ----
  register(phone: string, password: string, nickname: string, smsCode = '123456') {
    return this.request<{ token: string; user: Me }>('POST', '/auth/register', {
      phone, password, nickname, sms_code: smsCode,
    });
  }
  login(phone: string, password: string) {
    return this.request<{ token: string; user: Me }>('POST', '/auth/login', { phone, password });
  }
  me() {
    return this.request<Me>('GET', '/users/me');
  }
  updateMe(patch: Partial<Pick<Me, 'nickname' | 'bio' | 'city' | 'lat' | 'lng' | 'skills' | 'interests'>>) {
    return this.request<Me>('PATCH', '/users/me', patch);
  }
  verifyIdentity(realName: string, idNumber: string) {
    return this.request<{ is_verified: boolean }>('POST', '/users/me/verify', {
      real_name: realName, id_number: idNumber,
    });
  }
  publicProfile(userId: number) {
    return this.request<Partial<Me>>('GET', `/users/${userId}`);
  }

  // ---- tasks ----
  createTask(input: Partial<Task> & { title: string; category: string; publish_now?: boolean }) {
    return this.request<Task>('POST', '/tasks', input);
  }
  listTasks(params: Record<string, string | number | undefined> = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<Task[]>('GET', `/tasks${qs ? `?${qs}` : ''}`);
  }
  getTask(id: number) {
    return this.request<Task>('GET', `/tasks/${id}`);
  }
  apply(taskId: number, message = '', bidCents?: number) {
    return this.request<{ id: number }>('POST', `/tasks/${taskId}/applications`, {
      message, ...(bidCents ? { bid_cents: bidCents } : {}),
    });
  }
  listApplications(taskId: number) {
    return this.request<Array<{ id: number; applicant_id: number; nickname: string; credit_score: number; rating_avg: number; bid_cents: number; message: string; status: string }>>(
      'GET', `/tasks/${taskId}/applications`,
    );
  }
  recommendations(taskId: number) {
    return this.request<Recommendation[]>('GET', `/tasks/${taskId}/recommendations`);
  }
  acceptApplication(applicationId: number) {
    return this.request<{ contract_id: number; task: Task }>('POST', `/applications/${applicationId}/accept`);
  }
  addProgress(taskId: number, content: string) {
    return this.request<{ ok: boolean }>('POST', `/tasks/${taskId}/progress`, { content });
  }
  checkin(taskId: number, lat: number, lng: number) {
    return this.request<{ ok: boolean; distance_m: number }>('POST', `/tasks/${taskId}/checkin`, { lat, lng });
  }
  listProgress(taskId: number) {
    return this.request<Array<{ id: number; user_id: number; kind: string; content: string; created_at: string }>>(
      'GET', `/tasks/${taskId}/progress`,
    );
  }
  deliver(taskId: number) {
    return this.request<Task>('POST', `/tasks/${taskId}/deliver`);
  }
  acceptDelivery(taskId: number) {
    return this.request<Task>('POST', `/tasks/${taskId}/accept-delivery`);
  }
  rejectDelivery(taskId: number, reason: string) {
    return this.request<Task>('POST', `/tasks/${taskId}/reject-delivery`, { reason });
  }
  cancelTask(taskId: number) {
    return this.request<{ task: Task; executor_compensation_cents?: number }>('POST', `/tasks/${taskId}/cancel`);
  }
  review(taskId: number, stars: number, comment = '', tags: string[] = []) {
    return this.request<{ ok: boolean }>('POST', `/tasks/${taskId}/reviews`, { stars, comment, tags });
  }
  listReviews(taskId: number) {
    return this.request<Array<{ reviewer_id: number; target_id: number; stars: number; tags: string[]; comment: string }>>(
      'GET', `/tasks/${taskId}/reviews`,
    );
  }

  // ---- contract / wallet ----
  getContract(id: number) {
    return this.request<Contract>('GET', `/contracts/${id}`);
  }
  getContractByTask(taskId: number) {
    return this.request<Contract>('GET', `/contracts/by-task/${taskId}`);
  }
  signContract(id: number) {
    return this.request<Contract>('POST', `/contracts/${id}/sign`);
  }
  fundContract(id: number) {
    return this.request<Contract>('POST', `/contracts/${id}/fund`);
  }
  wallet() {
    return this.request<Wallet>('GET', '/wallet');
  }
  topup(amountCents: number) {
    return this.request<{ available_cents: number }>('POST', '/wallet/topup', { amount_cents: amountCents });
  }
  withdraw(amountCents: number) {
    return this.request<{ available_cents: number }>('POST', '/wallet/withdraw', { amount_cents: amountCents });
  }
  ledger() {
    return this.request<Array<{ id: number; kind: string; amount_cents: number; contract_id: number | null; memo: string; created_at: string }>>(
      'GET', '/wallet/ledger',
    );
  }

  // ---- decompose / knowledge ----
  propose(taskId: number) {
    return this.request<Decomposition>('POST', `/tasks/${taskId}/decompositions`);
  }
  editDecomposition(decId: number, items: DecompositionItem[]) {
    return this.request<Decomposition>('PATCH', `/decompositions/${decId}`, { items });
  }
  confirmDecomposition(decId: number) {
    return this.request<{ decomposition: Decomposition; children: Task[] }>(
      'POST', `/decompositions/${decId}/confirm`,
    );
  }
  taskTree(taskId: number) {
    return this.request<TaskTree>('GET', `/tasks/${taskId}/tree`);
  }
  priceReference(category: string, city?: string) {
    const qs = city ? `&city=${encodeURIComponent(city)}` : '';
    return this.request<PriceReference>('GET', `/knowledge/price-reference?category=${encodeURIComponent(category)}${qs}`);
  }

  // ---- im / notifications / support / dispute ----
  conversations() {
    return this.request<Conversation[]>('GET', '/conversations');
  }
  openDirect(userId: number) {
    return this.request<Conversation>('POST', '/conversations/direct', { user_id: userId });
  }
  messages(convId: number) {
    return this.request<Message[]>('GET', `/conversations/${convId}/messages`);
  }
  sendMessage(convId: number, content: string) {
    return this.request<{ id: number; risk_flagged: boolean; warning: string | null }>(
      'POST', `/conversations/${convId}/messages`, { content },
    );
  }
  notifications(unreadOnly = false) {
    return this.request<Notice[]>('GET', `/notifications${unreadOnly ? '?unread_only=true' : ''}`);
  }
  markRead(id: number) {
    return this.request<{ ok: boolean }>('POST', `/notifications/${id}/read`);
  }
  askSupport(question: string) {
    return this.request<{ answer: string; source: string | null; escalate_to_human: boolean; account_context: { available_cents: number } | null }>(
      'POST', '/support/ask', { question },
    );
  }
  // ---- contract v1: milestones / change orders ----
  defineMilestones(contractId: number, items: Array<{ title: string; amount_cents: number }>) {
    return this.request<Contract>('POST', `/contracts/${contractId}/milestones`, { items });
  }
  deliverMilestone(contractId: number, idx: number) {
    return this.request<Contract>('POST', `/contracts/${contractId}/milestones/${idx}/deliver`);
  }
  acceptMilestone(contractId: number, idx: number) {
    return this.request<Contract>('POST', `/contracts/${contractId}/milestones/${idx}/accept`);
  }
  proposeChange(contractId: number, newAmountCents: number, reason = '') {
    return this.request<{ id: number; status: string }>('POST', `/contracts/${contractId}/change-orders`, {
      new_amount_cents: newAmountCents, reason,
    });
  }
  acceptChange(contractId: number, orderId: number) {
    return this.request<Contract>('POST', `/contracts/${contractId}/change-orders/${orderId}/accept`);
  }

  // ---- content / social ----
  createContent(input: { kind?: string; title?: string; body: string; tags?: string[]; visibility?: string; circle_id?: number; linked_category?: string }) {
    return this.request<ContentItem>('POST', '/contents', input);
  }
  contentFeed(scope: 'latest' | 'following' = 'latest', params: { tag?: string; kind?: string } = {}) {
    const extra = Object.entries(params).filter(([, v]) => v).map(([k, v]) => `&${k}=${encodeURIComponent(v!)}`).join('');
    return this.request<ContentItem[]>('GET', `/feed?scope=${scope}${extra}`);
  }
  likeContent(contentId: number) {
    return this.request<{ liked: boolean; like_count: number }>('POST', `/contents/${contentId}/like`);
  }
  commentContent(contentId: number, body: string, replyToId?: number) {
    return this.request<{ id: number }>('POST', `/contents/${contentId}/comments`, {
      body, reply_to_id: replyToId ?? null,
    });
  }
  contentComments(contentId: number) {
    return this.request<Array<{ id: number; author_id: number; author_nickname: string; body: string; reply_to_id: number | null; created_at: string }>>(
      'GET', `/contents/${contentId}/comments`,
    );
  }
  followUser(userId: number) {
    return this.request<{ following: boolean }>('POST', `/users/${userId}/follow`);
  }
  followStats(userId: number) {
    return this.request<{ followers: number; following: number }>('GET', `/users/${userId}/follow-stats`);
  }

  // ---- circles ----
  createCircle(input: { name: string; description?: string; kind?: string; join_policy?: string; skill_tag?: string; city?: string; min_credit?: number }) {
    return this.request<CircleInfo>('POST', '/circles', input);
  }
  circles(params: { q?: string; kind?: string; recommended?: boolean } = {}) {
    const qs = Object.entries(params).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');
    return this.request<CircleInfo[]>('GET', `/circles${qs ? `?${qs}` : ''}`);
  }
  getCircle(id: number) {
    return this.request<CircleInfo>('GET', `/circles/${id}`);
  }
  joinCircle(id: number) {
    return this.request<{ status: string }>('POST', `/circles/${id}/join`);
  }
  approveCircleMember(circleId: number, userId: number) {
    return this.request<{ status: string }>('POST', `/circles/${circleId}/members/${userId}/approve`);
  }
  circleFeed(circleId: number) {
    return this.request<ContentItem[]>('GET', `/circles/${circleId}/feed`);
  }
  circleTasks(circleId: number) {
    return this.request<Task[]>('GET', `/circles/${circleId}/tasks`);
  }

  // ---- invitations / subscriptions ----
  inviteToTask(taskId: number, userId: number, message = '') {
    return this.request<{ id: number; status: string }>('POST', `/tasks/${taskId}/invitations`, {
      user_id: userId, message,
    });
  }
  myInvitations() {
    return this.request<InvitationItem[]>('GET', '/invitations');
  }
  acceptInvitation(id: number) {
    return this.request<{ contract_id: number; task_id: number }>('POST', `/invitations/${id}/accept`);
  }
  declineInvitation(id: number) {
    return this.request<{ status: string }>('POST', `/invitations/${id}/decline`);
  }
  subscribeCategory(category: string, city = '') {
    return this.request<{ id: number }>('POST', '/subscriptions', { category, city });
  }
  mySubscriptions() {
    return this.request<Array<{ id: number; category: string; city: string }>>('GET', '/subscriptions');
  }
  unsubscribe(id: number) {
    return this.request<{ ok: boolean }>('DELETE', `/subscriptions/${id}`);
  }

  // ---- legal / reports ----
  legalAsk(question: string) {
    return this.request<{ answer: string; disclaimer: string; refused: boolean }>('POST', '/legal/ask', { question });
  }
  exportEvidence(disputeId: number) {
    return this.request<{ package: Record<string, unknown>; sha256: string }>(
      'GET', `/legal/disputes/${disputeId}/evidence-export`,
    );
  }
  report(targetType: 'task' | 'content' | 'user' | 'message', targetId: number, reason: string) {
    return this.request<{ id: number; status: string }>('POST', '/reports', {
      target_type: targetType, target_id: targetId, reason,
    });
  }

  openDispute(taskId: number, reason: string) {
    return this.request<{ id: number; status: string }>('POST', `/tasks/${taskId}/disputes`, { reason });
  }
  proposeSettlement(disputeId: number, executorShareBps: number) {
    return this.request<{ id: number }>('POST', `/disputes/${disputeId}/settlement`, {
      executor_share_bps: executorShareBps,
    });
  }
  acceptSettlement(disputeId: number) {
    return this.request<{ id: number; status: string }>('POST', `/disputes/${disputeId}/settlement/accept`);
  }
}

export const fmtYuan = (cents: number): string => `¥${(cents / 100).toFixed(2)}`;

export const TASK_STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  published: '招募中',
  matched: '待签约托管',
  in_progress: '执行中',
  pending_acceptance: '待验收',
  completed: '已完成',
  cancelled: '已取消',
  disputed: '纠纷中',
};
