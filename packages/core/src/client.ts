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
  Mission,
  MissionStep,
  MissionTickResult,
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
  updateMe(patch: Partial<Pick<Me, 'nickname' | 'bio' | 'city' | 'lat' | 'lng' | 'skills' | 'interests'>> & {
    privacy?: { profile_public?: boolean };
    service_rate_cents?: number;
    available_times?: string;
  }) {
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
  createTask(input: Partial<Task> & {
    title: string;
    category: string;
    publish_now?: boolean;
    people_needed?: number;
  }) {
    return this.request<Task & { slots?: Task[] }>('POST', '/tasks', input);
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
  myTasks(params: { role?: 'all' | 'posted' | 'working'; status?: string; limit?: number; offset?: number } = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<Task[]>('GET', `/tasks/mine${qs ? `?${qs}` : ''}`);
  }
  expireTasks() {
    return this.request<{ expired: number }>('POST', '/tasks/jobs/expire-tasks');
  }
  editTask(id: number, patch: Partial<{
    title: string; description: string; budget_cents: number;
    required_skills: string[]; address_hint: string; address_exact: string; deadline: string;
  }>) {
    return this.request<Task>('PATCH', `/tasks/${id}`, patch);
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
  userReviews(userId: number, params: { limit?: number; offset?: number } = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<{
      total: number; tag_counts: Record<string, number>;
      items: Array<{ task_id: number; reviewer_id: number; stars: number; tags: string[]; comment: string; created_at: string }>;
    }>('GET', `/users/${userId}/reviews${qs ? `?${qs}` : ''}`);
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
  /** VND-020 请求短信验证码（模拟通道回显 dev_code，真实通道不回显）。 */
  sendSmsCode(phone: string, scene = 'verify') {
    return this.request<{ sent: boolean; expires_in: number; dev_code?: string }>(
      'POST', '/auth/send-code', { phone, scene },
    );
  }

  /** VND-011 充值两阶段：模拟通道即时 succeeded；真实通道返回 pending + pay_url。 */
  topup(amountCents: number) {
    return this.request<{
      order_no: string;
      status: 'succeeded' | 'pending';
      available_cents?: number;
      pay_url?: string;
    }>('POST', '/wallet/topup', { amount_cents: amountCents });
  }
  getPayoutAccount() {
    return this.request<{ bound: boolean; kind?: string; account_no?: string; holder_name?: string }>(
      'GET', '/wallet/payout-account',
    );
  }
  bindPayoutAccount(accountNo: string, holderName: string, kind: 'bank' | 'alipay' = 'bank') {
    return this.request<{ bound: boolean; kind: string; account_no: string }>(
      'PUT', '/wallet/payout-account', { kind, account_no: accountNo, holder_name: holderName },
    );
  }
  withdraw(amountCents: number) {
    return this.request<{ status: 'done' | 'pending_review'; request_id?: number; available_cents: number; frozen_cents: number }>(
      'POST', '/wallet/withdraw', { amount_cents: amountCents },
    );
  }
  withdrawRequests(status = 'pending') {
    return this.request<Array<{ id: number; user_id: number; amount_cents: number; status: string; created_at: string }>>(
      'GET', `/wallet/withdraw-requests?status=${status}`,
    );
  }
  decideWithdraw(requestId: number, approve: boolean) {
    return this.request<{ status: string; amount_cents: number }>(
      'POST', `/wallet/withdraw-requests/${requestId}/${approve ? 'approve' : 'reject'}`,
    );
  }
  changePassword(oldPassword: string, newPassword: string) {
    return this.request<{ token: string }>('POST', '/auth/change-password', {
      old_password: oldPassword, new_password: newPassword,
    });
  }
  resetPassword(phone: string, smsCode: string, newPassword: string) {
    return this.request<{ ok: boolean }>('POST', '/auth/reset-password', {
      phone, sms_code: smsCode, new_password: newPassword,
    });
  }
  changePhone(newPhone: string, smsCode: string, password: string) {
    return this.request<{ ok: boolean; phone: string }>('POST', '/auth/change-phone', {
      new_phone: newPhone, sms_code: smsCode, password,
    });
  }
  broadcastAnnouncement(title: string, body = '', verifiedOnly = false) {
    return this.request<{ delivered: number }>('POST', '/admin/announcements', {
      title, body, verified_only: verifiedOnly,
    });
  }
  platformFinance() {
    return this.request<{ balance_cents: number; total_fee_cents: number; settled_cents: number; fee_count: number }>(
      'GET', '/admin/platform-finance',
    );
  }
  settlePlatform(amountCents: number, memo = '平台收入结算') {
    return this.request<{ settled_cents: number; balance_cents: number }>(
      'POST', '/admin/platform-finance/settle', { amount_cents: amountCents, memo },
    );
  }
  withdrawApplication(applicationId: number) {
    return this.request<{ id: number; status: string }>('POST', `/applications/${applicationId}/withdraw`);
  }
  myApplications(params: { status?: string; limit?: number; offset?: number } = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<Array<{ application_id: number; task_id: number; status: string; bid_cents: number; message: string; created_at: string; task_title: string | null; task_status: string | null; task_budget_cents: number | null }>>(
      'GET', `/users/me/applications${qs ? `?${qs}` : ''}`,
    );
  }
  bookmark(taskId: number) {
    return this.request<{ ok: boolean; already?: boolean }>('POST', `/tasks/${taskId}/bookmark`);
  }
  unbookmark(taskId: number) {
    return this.request<{ ok: boolean }>('DELETE', `/tasks/${taskId}/bookmark`);
  }
  myBookmarks() {
    return this.request<Task[]>('GET', '/users/me/bookmarks');
  }
  ledger() {
    return this.request<Array<{ id: number; kind: string; amount_cents: number; contract_id: number | null; memo: string; created_at: string }>>(
      'GET', '/wallet/ledger',
    );
  }

  // ---- orchestrator（Agent Harness：发任务给人=工具调用）----
  createMission(body: { goal: string; detail?: string; category?: string; budget_cap_cents: number; max_iterations?: number; acceptance_criteria?: string[] }) {
    return this.request<Mission>('POST', '/missions', body);
  }
  myMissions(params: { status?: string; limit?: number; offset?: number } = {}) {
    const qs = Object.entries(params).filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');
    return this.request<Mission[]>('GET', `/missions${qs ? `?${qs}` : ''}`);
  }
  getMission(id: number) {
    return this.request<Mission & { steps: MissionStep[] }>('GET', `/missions/${id}`);
  }
  tickMission(id: number) {
    return this.request<MissionTickResult>('POST', `/missions/${id}/tick`);
  }
  cancelMission(id: number) {
    return this.request<Mission & { closed_open_tasks: number }>('POST', `/missions/${id}/cancel`);
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
    return this.request<Array<Conversation & {
      unread_count: number;
      last_message: { id: number; sender_id: number; kind: string; content: string; created_at: string } | null;
    }>>('GET', '/conversations');
  }
  imUnreadCount() {
    return this.request<{ unread: number }>('GET', '/conversations/unread-count');
  }
  markConversationRead(convId: number) {
    return this.request<{ conversation_id: number; last_read_message_id: number }>(
      'POST', `/conversations/${convId}/read`,
    );
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
  unreadCount() {
    return this.request<{ unread: number }>('GET', '/notifications/unread-count');
  }
  markAllRead() {
    return this.request<{ marked: number }>('POST', '/notifications/read-all');
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

  // ---- V3/V4: clarify / templates / cities / sessions / export ----
  clarify(input: { title?: string; description?: string; category?: string; budget_cents?: number; city?: string; is_remote?: boolean }) {
    return this.request<{
      ready: boolean;
      questions: Array<{ field: string; question: string }>;
      feasibility: { level: string; message: string; p50_cents?: number } | null;
    }>('POST', '/ai/clarify', input);
  }
  taskTemplate(category: string) {
    return this.request<{ category: string; title: string; description: string; checklist: string[]; price_reference: PriceReference }>(
      'GET', `/task-templates?category=${encodeURIComponent(category)}`,
    );
  }
  categories() {
    return this.request<Array<{ id: number; name: string; required_cert: string }>>('GET', '/categories');
  }
  cities() {
    return this.request<Array<{ id: number; name: string }>>('GET', '/cities');
  }
  finalReport(taskId: number) {
    return this.request<{ summary: string; total_cost_cents: number; children_completed: number; children_total: number; deliverables: Array<Record<string, unknown>> }>(
      'GET', `/tasks/${taskId}/final-report`,
    );
  }
  mySessions() {
    return this.request<Array<{ id: number; device: string; created_at: string }>>('GET', '/auth/sessions');
  }
  revokeSession(id: number) {
    return this.request<{ ok: boolean }>('POST', `/auth/sessions/${id}/revoke`);
  }
  deactivateAccount() {
    return this.request<{ deleted: boolean }>('POST', '/users/me/deactivate');
  }
  exportContract(contractId: number) {
    return this.request<{ contract_id: number; text: string; ledger_count: number; anchor_head: string | null }>(
      'GET', `/contracts/${contractId}/export`,
    );
  }
  sendQuoteCard(convId: number, taskId: number, priceCents: number, note = '') {
    return this.request<{ id: number; kind: string }>('POST', `/conversations/${convId}/quote-cards`, {
      task_id: taskId, price_cents: priceCents, note,
    });
  }
  createExperiencePost(taskId: number, body: string, title = '') {
    return this.request<ContentItem>('POST', `/tasks/${taskId}/experience-post`, { body, title });
  }
  circleStats(circleId: number) {
    return this.request<{ member_count: number; posts: number; tasks_total: number; tasks_completed: number; gmv_cents: number }>(
      'GET', `/circles/${circleId}/stats`,
    );
  }

  // ---- block / recall / certification / anchors ----
  toggleBlock(userId: number) {
    return this.request<{ blocked: boolean }>('POST', `/users/${userId}/block`);
  }
  myBlocks() {
    return this.request<Array<{ user_id: number; nickname: string }>>('GET', '/users/me/blocks');
  }
  recallMessage(messageId: number) {
    return this.request<{ ok: boolean }>('POST', `/messages/${messageId}/recall`);
  }
  addCertification(name: string, licenseNo: string) {
    return this.request<{ certifications: string[] }>('POST', '/users/me/certifications', {
      name, license_no: licenseNo,
    });
  }
  contractAnchors(contractId: number) {
    return this.request<Array<{ seq: number; event_type: string; chain_hash: string; payload_hash: string; created_at: string }>>(
      'GET', `/anchors/contracts/${contractId}`,
    );
  }
  verifyAnchorChain() {
    return this.request<{ valid: boolean; total: number; broken_at_seq?: number }>('GET', '/anchors/verify');
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

  // ---- search / recurring / export ----
  search(q: string) {
    return this.request<{
      tasks: Array<{ id: number; title: string; category: string; budget_cents: number; city: string }>;
      users: Array<{ id: number; nickname: string; skills: string[]; credit_score: number; rating_avg: number }>;
      contents: Array<{ id: number; kind: string; title: string; body: string; author_id: number }>;
      circles: Array<{ id: number; name: string; kind: string; member_count: number }>;
    }>('GET', `/search?q=${encodeURIComponent(q)}`);
  }
  exportMyData() {
    return this.request<Record<string, unknown>>('GET', '/users/me/export');
  }
  legalDocument(kind: 'demand_letter' | 'settlement_agreement', taskId: number, demand = '') {
    return this.request<{ kind: string; text: string; disclaimer: string }>('POST', '/legal/documents', {
      kind, task_id: taskId, demand,
    });
  }

  // ---- admin ----
  adminMetrics() {
    return this.request<{
      total_users: number; verified_users: number; total_tasks: number; published_tasks: number;
      completed_tasks: number; closed_loop_rate: number; dispute_count: number;
      gmv_cents: number; fee_income_cents: number;
    }>('GET', '/admin/metrics');
  }
  adminReports(status = 'pending') {
    return this.request<Array<{ id: number; reporter_id: number; target_type: string; target_id: number; reason: string; created_at: string }>>(
      'GET', `/admin/reports?status=${status}`,
    );
  }
  banImpact(userId: number) {
    return this.request<{
      in_flight_contracts: Array<{ contract_id: number; task_id: number; status: string; amount_cents: number; counterparty_id: number }>;
      in_flight_count: number; escrow_at_risk_cents: number;
      wallet: { available_cents: number; escrow_cents: number; frozen_cents: number };
    }>('GET', `/admin/users/${userId}/ban-impact`);
  }
  adminAuditLog(params: { action?: string; limit?: number; offset?: number } = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<Array<{ id: number; admin_id: number; action: string; target_type: string; target_id: number | null; detail: string; created_at: string }>>(
      'GET', `/admin/audit-log${qs ? `?${qs}` : ''}`,
    );
  }
  resolveReport(reportId: number, action: 'dismiss' | 'remove_content' | 'ban_user') {
    return this.request<{ id: number; status: string; action: string }>(
      'POST', `/admin/reports/${reportId}/resolve`, { action },
    );
  }
  adminUsers(q = '') {
    return this.request<Array<{ id: number; phone: string; nickname: string; is_verified: boolean; is_banned: boolean; credit_score: number; tasks_completed: number }>>(
      'GET', `/admin/users${q ? `?q=${encodeURIComponent(q)}` : ''}`,
    );
  }
  banUser(userId: number) {
    return this.request<{ id: number; is_banned: boolean }>('POST', `/admin/users/${userId}/ban`);
  }
  unbanUser(userId: number) {
    return this.request<{ id: number; is_banned: boolean }>('POST', `/admin/users/${userId}/unban`);
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
