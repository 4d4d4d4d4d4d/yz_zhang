// 平台 API SDK：Web 与 App 共用（13 号 spec「两端共享同一 API/BFF」）
import type {
  AgentProfileView,
  AgentRunView,
  AgreementStatus,
  ApiKeyView,
  CaptchaConfig,
  CertificationApplicationView,
  CircleInfo,
  CompliancePath,
  ContentItem,
  ContributionKind,
  ContributionView,
  EligibleAgent,
  RiskDisclosure,
  ShareRow,
  SpendRequestView,
  TeamDetail,
  TeamView,
  VentureDetail,
  VentureView,
  VerificationOrderDetail,
  VerificationOrderView,
  WebhookDeliveryView,
  WebhookView,
  CouponTemplate,
  MarketCell,
  MyCoupon,
  Contract,
  Decomposition,
  DecompositionItem,
  Dispute,
  DisputeStatement,
  Conversation,
  InvitationItem,
  Me,
  Message,
  Mission,
  MissionEvent,
  MissionStep,
  AnchorCoverage,
  SettlementOrderView,
  SignatureReport,
  StepReviewRecord,
  MissionTickResult,
  Notice,
  PriceReference,
  Recommendation,
  Task,
  TaskTree,
  TaxSummary,
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
  /** CAP-010 `captchaToken` 在服务端返回 `captcha_required` 后由调用方补上并重试。
   *
   *  V56 在服务端加了这道门，却没有任何客户端能交出令牌——网页和 App 上
   *  连一个能填的地方都没有。运维一旦按文档接上真实验证码，任何连续输错
   *  3 次密码的用户都会被永久挡在门外。这个参数是那把钥匙。
   */
  login(phone: string, password: string, captchaToken = '') {
    return this.request<{ token: string; user: Me }>('POST', '/auth/login', {
      phone, password, captcha_token: captchaToken,
    });
  }
  /** CAP-002 渲染人机验证挑战所需的配置（公开，登录页还没有 token）。 */
  captchaConfig() {
    return this.request<CaptchaConfig>('GET', '/auth/captcha-config');
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
  /** MOB-021 进度留痕可附图片凭证（先调 uploadImage 拿 url）。 */
  addProgress(taskId: number, content: string, images: string[] = []) {
    return this.request<{ ok: boolean }>('POST', `/tasks/${taskId}/progress`, { content, images });
  }

  /** VND-031 上传图片：传客户端压缩后的 base64（不含 data: 前缀）。 */
  uploadImage(contentType: string, dataBase64: string) {
    return this.request<{ url: string; ref: string }>('POST', '/files', {
      content_type: contentType,
      data_base64: dataBase64,
    });
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
  /** SC-003 托管；可带 GRW 优惠券（补贴先到账再托管，发布方净掏钱变少）。 */
  fundContract(id: number, userCouponId?: number) {
    const q = userCouponId ? `?user_coupon_id=${userCouponId}` : '';
    return this.request<Contract & { coupon_discount_cents?: number }>(
      'POST', `/contracts/${id}/fund${q}`,
    );
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
  /** LAW-002/040 合约签署留痕与校验：签署后改条款 → 哈希对不上，篡改自证。 */
  contractSignatures(contractId: number) {
    return this.request<SignatureReport>('GET', `/contracts/${contractId}/signatures`);
  }

  /** LAW-013 存证覆盖：哪些区间有第三方背书、哪些只是平台自算。 */
  anchorCoverage() {
    return this.request<AnchorCoverage>('GET', '/anchors/coverage');
  }

  /** FIN-042 资金流向审计：一份合约上发生过的全部分账指令。 */
  contractSettlements(contractId: number) {
    return this.request<{ settlements: SettlementOrderView[]; sandbox: boolean }>(
      'GET', `/contracts/${contractId}/settlements`,
    );
  }

  /** AIO-013 某一步的评审留痕（谁判的、依据什么、多久）。 */
  stepReviews(missionId: number, stepId: number) {
    return this.request<{ reviews: StepReviewRecord[] }>(
      'GET', `/missions/${missionId}/steps/${stepId}/reviews`,
    );
  }

  getMission(id: number) {
    return this.request<Mission & { steps: MissionStep[]; timeline: MissionEvent[] }>(
      'GET', `/missions/${id}`,
    );
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
  // ── GRW 增长运营（22 号 spec）────────────────────────────────
  /** 可领取的券（已领满/已领完的不返回）。 */
  availableCoupons() {
    return this.request<{ coupons: CouponTemplate[] }>('GET', '/coupons');
  }
  claimCoupon(couponId: number) {
    return this.request<{ id: number; coupon_id: number; status: string; expires_at: string }>(
      'POST', `/coupons/${couponId}/claim`,
    );
  }
  myCoupons() {
    return this.request<{ coupons: MyCoupon[] }>('GET', '/me/coupons');
  }
  /** 下单前查这一单能用哪张券、能省多少。 */
  couponsForContract(contractId: number) {
    return this.request<{ usable: Array<{ user_coupon_id: number; title: string; discount_cents: number }> }>(
      'GET', `/contracts/${contractId}/coupons`,
    );
  }
  /** GRW-014 邀请战绩。levels 恒为 1：奖励仅一级。 */
  myReferrals() {
    return this.request<{
      referral_code: string; invited_count: number; achieved_count: number;
      blocked_count: number; earned_cents: number; levels: number;
    }>('GET', '/me/referrals');
  }
  /** GRW-020 新人任务进度。 */
  newcomerProgress() {
    return this.request<{
      steps: Array<{ key: string; label: string; done: boolean }>;
      finished: number; total: number; completed: boolean;
    }>('GET', '/me/newcomer');
  }
  /** GRW-023 发布前的供给提示（该区域执行人少时提前告知）。 */
  supplyHint(city: string, category: string) {
    return this.request<{ hint: string }>(
      'GET', `/market/supply-hint?city=${encodeURIComponent(city)}&category=${encodeURIComponent(category)}`,
    );
  }
  marketHealth(days = 30) {
    return this.request<{ window_days: number; min_supply: number; cells: MarketCell[] }>(
      'GET', `/admin/market-health?days=${days}`,
    );
  }
  northStar(days = 30) {
    return this.request<{
      window_days: number; orders_completed: number; gmv_cents: number;
      new_users: number; new_user_first_order_rate: number; dispute_rate: number;
    }>('GET', `/admin/north-star?days=${days}`);
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
  /** CNT-003 `publish: false` 存草稿——草稿只有作者自己看得见。 */
  createContent(input: {
    kind?: string; title?: string; body: string; tags?: string[]; visibility?: string;
    circle_id?: number; linked_category?: string; media_urls?: string[]; publish?: boolean;
  }) {
    return this.request<ContentItem>('POST', '/contents', input);
  }
  contentFeed(scope: 'latest' | 'following' = 'latest', params: { tag?: string; kind?: string } = {}) {
    const extra = Object.entries(params).filter(([, v]) => v).map(([k, v]) => `&${k}=${encodeURIComponent(v!)}`).join('');
    return this.request<ContentItem[]>('GET', `/feed?scope=${scope}${extra}`);
  }
  editContent(contentId: number, patch: {
    title?: string; body?: string; tags?: string[]; media_urls?: string[]; linked_category?: string;
  }) {
    return this.request<ContentItem>('PATCH', `/contents/${contentId}`, patch);
  }
  /** 发布时服务端会**重跑机审**：草稿是随便改的，存草稿时审过不算数。 */
  publishContent(contentId: number) {
    return this.request<ContentItem>('POST', `/contents/${contentId}/publish`);
  }
  myDrafts(limit = 20) {
    return this.request<Array<{ id: number; title: string; created_at: string }>>(
      'GET', `/contents/mine?status=draft&limit=${limit}`,
    );
  }
  getContent(contentId: number) {
    return this.request<ContentItem>('GET', `/contents/${contentId}`);
  }
  /** CNT-014 视频直传。视频不能走 base64——50MB 的视频 base64 后是 67MB 的
   *  JSON 体，整个读进内存再解码，几个并发就能把进程打死。 */
  signVideoUpload(contentType: string, sizeBytes: number) {
    return this.request<{ ref: string; direct_upload: boolean; upload_url?: string; reason?: string }>(
      'POST', '/files/sign-upload', { content_type: contentType, size_bytes: sizeBytes },
    );
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
  /** CERT-060 **这个方法此前会 422。**
   *
   *  V76 把资质从「POST 一个字符串就拿到」改成了「提交申请 + 证件影像 +
   *  持证人姓名与实名比对」，服务端契约换了，SDK 停在旧形状上没人发现——
   *  因为 SDK 的测试打的是 mock fetch，它只验证「我发出的请求长这样」，
   *  从不验证「服务端认不认这个形状」（57 号 spec 第 0 节）。
   *
   *  旧签名保留会更"兼容"，但它兼容的是一个服务端已经不接受的形状，
   *  留着只会让下一个人以为它能用。
   */
  submitCertification(input: {
    name: string;
    holderName: string;
    certNumber: string;
    issuer?: string;
    expiresAt?: string | null;
    images: string[];
  }) {
    return this.request<{ id: number; name: string; status: string; certifications: string[] }>(
      'POST', '/users/me/certifications',
      {
        name: input.name,
        holder_name: input.holderName,
        cert_number: input.certNumber,
        issuer: input.issuer ?? '',
        expires_at: input.expiresAt ?? null,
        images: input.images,
      },
    );
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
  // TAX-021 我的个税代扣明细（注意：是代扣明细，不是完税证明）
  myTax() {
    return this.request<TaxSummary>('GET', '/finance/my-tax');
  }

  // LAW-030/031/032 协议版本、单独同意与数据主体权利
  myAgreements() {
    return this.request<AgreementStatus>('GET', '/legal/agreements');
  }
  acceptAgreements() {
    return this.request<{ accepted_version: string; documents: string[] }>(
      'POST', '/legal/agreements/accept',
    );
  }
  grantConsent(scope: string) {
    return this.request<{ scope: string; granted: boolean; version: string }>(
      'POST', `/legal/consents/${scope}/grant`,
    );
  }
  revokeConsent(scope: string) {
    return this.request<{ scope: string; revoked: boolean; effect: string; applied: string[] }>(
      'POST', `/legal/consents/${scope}/revoke`,
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

  // ---- ACC-003 第三方登录 ----
  /** App Store 规则：提供了任何第三方登录就必须同时提供 Apple，
   *  所以画哪几个按钮以这个端点为准，不要硬编码。 */
  oauthProviders() {
    return this.request<{ providers: string[]; implementation: string; verifies: boolean }>(
      'GET', '/auth/oauth/providers',
    );
  }
  /** `needs_phone` / `needs_verification` 是有意返回的：
   *  第三方登录认证的是「这是同一个微信」，不是「这是张三」——
   *  接单与提现仍然要走实名。 */
  oauthLogin(provider: 'wechat' | 'apple' | 'google', credential: string) {
    return this.request<{
      token: string; user: Me; created: boolean;
      needs_phone: boolean; needs_verification: boolean;
    }>('POST', `/auth/oauth/${provider}`, { credential });
  }

  // ---- IM-020/021/022 好友与通讯录 ----
  sendFriendRequest(userId: number, remark = '') {
    return this.request<{ id: number; status: string }>(
      'POST', '/friends/requests', { user_id: userId, remark },
    );
  }
  friendRequests() {
    return this.request<Array<{ id: number; from_user_id: number; created_at: string }>>(
      'GET', '/friends/requests',
    );
  }
  decideFriendRequest(requestId: number, accept: boolean) {
    return this.request<{ id: number; status: string }>(
      'POST', `/friends/requests/${requestId}/decide?accept=${accept}`,
    );
  }
  friends() {
    return this.request<Array<{ user_id: number; nickname: string; remark: string; credit_score: number }>>(
      'GET', '/friends',
    );
  }
  setFriendRemark(userId: number, remark: string) {
    return this.request<{ user_id: number; remark: string }>('PATCH', `/friends/${userId}`, { remark });
  }
  removeFriend(userId: number) {
    return this.request<{ ok: boolean }>('DELETE', `/friends/${userId}`);
  }
  /** IM-022 合作过的人：服务端**查**出来的，不是存出来的——不会过时。 */
  workedWith() {
    return this.request<Array<{ user_id: number; nickname: string; times: number; credit_score: number }>>(
      'GET', '/friends/worked-with',
    );
  }

  // ---- IM-003 群聊 ----
  createGroup(name: string, memberIds: number[] = []) {
    return this.request<{ id: number; name: string; members: number[] }>(
      'POST', '/conversations/groups', { name, member_ids: memberIds },
    );
  }
  inviteToGroup(convId: number, userIds: number[]) {
    return this.request<{ id: number; members: number[] }>(
      'POST', `/conversations/${convId}/members`, { user_ids: userIds },
    );
  }
  removeFromGroup(convId: number, userId: number) {
    return this.request<{ id: number; members: number[] }>(
      'DELETE', `/conversations/${convId}/members/${userId}`,
    );
  }
  updateGroup(convId: number, patch: { name?: string; announcement?: string; muted?: number[] }) {
    return this.request<{ id: number; name: string; announcement: string; muted: number[] }>(
      'PATCH', `/conversations/${convId}`, patch,
    );
  }

  /** NTF-002 注册推送令牌。App 每次启动都调——服务端按令牌主键幂等。 */
  registerDevice(token: string, platform: 'ios' | 'android' | 'web' = 'ios') {
    return this.request<{ registered: boolean; platform: string }>(
      'PUT', '/notifications/devices', { token, platform },
    );
  }
  unregisterDevice(token: string) {
    return this.request<{ ok: boolean }>('DELETE', `/notifications/devices/${token}`);
  }
  /** KB-022 统一检索。`semantic`/`degraded` 是有意暴露的——
   *  缺省 embedding 是词袋哈希不是语义模型，没建索引时还会退化成词面命中。
   *  悄悄退化的「语义检索」比没有更糟：你不会去修它。 */
  knowledgeSearch(q: string, kind: 'card' | 'faq' = 'card', topK = 5) {
    return this.request<{
      results: Array<{ id: number; score: number; text: string }>;
      semantic: boolean; degraded: boolean; model: string;
    }>('GET', `/knowledge/search?q=${encodeURIComponent(q)}&kind=${kind}&top_k=${topK}`);
  }

  openDispute(taskId: number, reason: string) {
    return this.request<Dispute>('POST', `/tasks/${taskId}/disputes`, { reason });
  }
  dispute(disputeId: number) {
    return this.request<Dispute>('GET', `/disputes/${disputeId}`);
  }
  // DSPC-010 被诉方进入这场纠纷的唯一一条路：他只知道任务 id。
  // 发起方能从 openDispute() 的返回值里拿到 dispute_id，被诉方拿不到。
  disputeByTask(taskId: number) {
    return this.request<Dispute>('GET', `/tasks/${taskId}/dispute`);
  }
  disputeStatements(disputeId: number) {
    return this.request<DisputeStatement[]>('GET', `/disputes/${disputeId}/statements`);
  }
  // DSPC-001 答辩。服务端把「两造兼听」当作裁决的硬性前置，
  // 而在此之前没有任何客户端能写入这张表——那道前置永远只能靠等答辩期超时满足。
  addDisputeStatement(disputeId: number, content: string, attachments: string[] = []) {
    return this.request<{ id: number; role: string; created_at: string }>(
      'POST', `/disputes/${disputeId}/statements`, { content, attachments },
    );
  }
  appealDispute(disputeId: number) {
    return this.request<Dispute & { appealed: boolean }>('POST', `/disputes/${disputeId}/appeal`);
  }
  proposeSettlement(disputeId: number, executorShareBps: number) {
    return this.request<{ id: number }>('POST', `/disputes/${disputeId}/settlement`, {
      executor_share_bps: executorShareBps,
    });
  }
  acceptSettlement(disputeId: number) {
    return this.request<{ id: number; status: string }>('POST', `/disputes/${disputeId}/settlement/accept`);
  }

  // ==================================================================
  // CLI-062 以下六条线在 V73~V79 全部只做了服务端。
  // 清点结果：78 个用户可达端点，SDK 里一个都没有——服务端完整、
  // 测试全绿、文档齐备，而用户点不到（57 号 spec）。
  // 覆盖闸门见 server/tests/test_client_contract_coverage.py。
  // ==================================================================

  // ---- AGT 平台自有 AI 助理 ----
  /** 平台在售的 AI 助理目录。不含 prompt 与成本——那是平台的实现细节与经营数据。 */
  agents() {
    return this.request<AgentProfileView[]>('GET', '/agents');
  }
  /** AGT-018 这个任务哪些助理能接，以及**不能接的逐条理由**。
   *  只回一个空列表没有意义：发布方不知道是因为要到场、还是金额超限，
   *  也就不知道该改什么。 */
  eligibleAgents(taskId: number) {
    return this.request<EligibleAgent[]>('GET', `/tasks/${taskId}/eligible-agents`);
  }
  /** 由发布方主动邀请，平台不自动派单——让 AI 接自己的活是一个需要知情的选择。 */
  inviteAgent(taskId: number, agentUserId: number) {
    return this.request<{ id: number; status: string; agent_user_id: number }>(
      'POST', `/tasks/${taskId}/agent-apply?agent_user_id=${agentUserId}`,
    );
  }
  /** 触发执行。AGT-060：成功即由平台代为提交交付（agent 没有登录态）。 */
  runAgent(taskId: number) {
    return this.request<AgentRunView & { delivered: boolean; task_status: string }>(
      'POST', `/tasks/${taskId}/agent-run`,
    );
  }
  agentRuns(taskId: number) {
    return this.request<{ runs: AgentRunView[]; delivery_block: string }>(
      'GET', `/tasks/${taskId}/agent-runs`,
    );
  }

  // ---- VER 人类核验 ----
  /** VER-002 谁付费由服务端判断：置信度不足自动升级 → 平台付；
   *  主动核验一个已成功的 run → 发布方付。响应里的 `payer_id` 就是答案。 */
  requestVerification(taskId: number) {
    return this.request<VerificationOrderView>('POST', `/tasks/${taskId}/verification`);
  }
  /** 可接的核验单。不能接的带 `reason`——**只显示空列表，核验人不知道
   *  是资格不够还是真没单**。 */
  openVerificationOrders() {
    return this.request<Array<VerificationOrderView & {
      category: string; task_title: string; claimable: boolean; reason: string;
    }>>('GET', '/verification-orders');
  }
  claimVerificationOrder(orderId: number) {
    return this.request<VerificationOrderView>('POST', `/verification-orders/${orderId}/claim`);
  }
  /** 核验人要看的就是这三样：AI 产出 + 自报置信度 + 平台判据逐条结果。 */
  verificationOrder(orderId: number) {
    return this.request<VerificationOrderDetail>('GET', `/verification-orders/${orderId}`);
  }
  submitVerificationOutcome(
    orderId: number, outcome: 'approved' | 'revised' | 'rejected',
    comment = '', revisedOutput = '',
  ) {
    return this.request<{ outcome: string; unblocked: boolean; delivered: boolean }>(
      'POST', `/verification-orders/${orderId}/outcome`,
      { outcome, comment, revised_output: revisedOutput },
    );
  }

  // ---- COOP 早期合作体 ----
  /** COOP-030 加入前要签的那份。**公开可读**——要求人签一份他看不到的东西是荒谬的。 */
  ventureRiskDisclosure(name = '（待定）') {
    return this.request<RiskDisclosure>('GET', `/ventures/risk-disclosure?name=${encodeURIComponent(name)}`);
  }
  createVenture(name: string, purpose: string, category: string, riskDisclosureVersion: string) {
    return this.request<VentureView>('POST', '/ventures', {
      name, purpose, category, risk_disclosure_version: riskDisclosureVersion,
    });
  }
  myVentures() {
    return this.request<Array<VentureView & { role: string }>>('GET', '/ventures/mine');
  }
  venture(ventureId: number) {
    return this.request<VentureDetail>('GET', `/ventures/${ventureId}`);
  }
  /** COOP-021 邀请制，没有公开加入端点——这是让它落在合作内部而非公开募集的
   *  结构性设计之一。 */
  inviteToVenture(ventureId: number, userId: number) {
    return this.request<{ invited: number; venture_id: number; risk_disclosure_version: string }>(
      'POST', `/ventures/${ventureId}/invitations`, { user_id: userId },
    );
  }
  /** 风险揭示书由**被邀请人自己**签：代签的知情同意不是知情同意。 */
  joinVenture(ventureId: number, riskDisclosureVersion: string) {
    return this.request<{ venture_id: number; user_id: number; role: string }>(
      'POST', `/ventures/${ventureId}/members`, { risk_disclosure_version: riskDisclosureVersion },
    );
  }
  submitContribution(ventureId: number, kind: ContributionKind, description: string, evidence: string[] = []) {
    return this.request<{ id: number; status: string }>(
      'POST', `/ventures/${ventureId}/contributions`, { kind, description, evidence },
    );
  }
  ventureContributions(ventureId: number) {
    return this.request<ContributionView[]>('GET', `/ventures/${ventureId}/contributions`);
  }
  /** 提交时不计价：贡献人说「我做了什么」，确认人说「这值多少」。 */
  confirmContribution(ventureId: number, contributionId: number, valuedCents: number, note = '', accept = true) {
    return this.request<{ id: number; status: string; valued_cents: number; shares: ShareRow[] }>(
      'POST', `/ventures/${ventureId}/contributions/${contributionId}/confirm`,
      { accept, valued_cents: valuedCents, note },
    );
  }
  ventureShares(ventureId: number) {
    return this.request<{ shares: ShareRow[]; total_bps: number; basis: string }>(
      'GET', `/ventures/${ventureId}/shares`,
    );
  }
  distributeVenture(ventureId: number, amountCents: number, memo = '') {
    return this.request<{ id: number; total_cents: number; share_snapshot: ShareRow[] }>(
      'POST', `/ventures/${ventureId}/distributions`, { amount_cents: amountCents, memo },
    );
  }
  ventureDistributions(ventureId: number) {
    return this.request<Array<{ id: number; total_cents: number; memo: string; share_snapshot: ShareRow[]; created_at: string }>>(
      'GET', `/ventures/${ventureId}/distributions`,
    );
  }
  /** COOP-040 **告诉你需要什么，不拦住你**：结构化清单 + 每项理由 + 当前状态。 */
  ventureCompliancePath(ventureId: number) {
    return this.request<CompliancePath>('GET', `/ventures/${ventureId}/compliance-path`);
  }

  // ---- TEAM 团队账户 ----
  createTeam(name: string) {
    return this.request<TeamView>('POST', '/teams', { name });
  }
  myTeams() {
    return this.request<Array<TeamView & { my_role: string; my_spend_limit_cents: number }>>('GET', '/teams/mine');
  }
  team(teamId: number) {
    return this.request<TeamDetail>('GET', `/teams/${teamId}`);
  }
  addTeamMember(teamId: number, userId: number, role: 'admin' | 'member' = 'member', spendLimitCents = 0) {
    return this.request<{ team_id: number; user_id: number; role: string; spend_limit_cents: number }>(
      'POST', `/teams/${teamId}/members`, { user_id: userId, role, spend_limit_cents: spendLimitCents },
    );
  }
  updateTeamMember(teamId: number, memberUserId: number, patch: { role?: 'admin' | 'member'; spend_limit_cents?: number }) {
    return this.request<{ user_id: number; role: string; spend_limit_cents: number }>(
      'PATCH', `/teams/${teamId}/members/${memberUserId}`, patch,
    );
  }
  removeTeamMember(teamId: number, memberUserId: number) {
    return this.request<{ removed: number }>('DELETE', `/teams/${teamId}/members/${memberUserId}`);
  }
  /** 超出个人额度时服务端返回 `needed_approval`，不是直接失败——
   *  申请已经建好了，等的是审批。 */
  requestTeamSpend(teamId: number, amountCents: number, purpose = '', taskId?: number) {
    return this.request<{ id: number; status: string; needed_approval: boolean; reason: string }>(
      'POST', `/teams/${teamId}/spends`, { amount_cents: amountCents, purpose, task_id: taskId ?? null },
    );
  }
  teamSpends(teamId: number) {
    return this.request<SpendRequestView[]>('GET', `/teams/${teamId}/spends`);
  }
  decideTeamSpend(teamId: number, requestId: number, approve: boolean, reason = '') {
    return this.request<{ id: number; status: string }>(
      'POST', `/teams/${teamId}/spends/${requestId}/decide`, { approve, reason },
    );
  }
  executeTeamSpend(teamId: number, requestId: number) {
    return this.request<{ id: number; status: string; amount_cents: number }>(
      'POST', `/teams/${teamId}/spends/${requestId}/execute`,
    );
  }
  /** TEAM-030 企业信息转人工核验（沿用 V76 那套：材料是敏感文件）。 */
  submitTeamCompany(teamId: number, companyName: string, taxNumber: string, licenseImages: string[] = []) {
    return this.request<TeamView>(
      'POST', `/teams/${teamId}/company`,
      { company_name: companyName, tax_number: taxNumber, license_images: licenseImages },
    );
  }

  // ---- OAPI 开放 API 与 Webhook ----
  apiScopes() {
    return this.request<{ scopes: Array<{ name: string; description: string }>; note: string }>(
      'GET', '/developer/scopes',
    );
  }
  /** API-001 明文 key **只在这个响应里出现一次**，库里只存哈希。 */
  createApiKey(name: string, scopes: string[]) {
    return this.request<{ id: number; name: string; scopes: string[]; key_prefix: string; key: string; warning: string }>(
      'POST', '/developer/api-keys', { name, scopes },
    );
  }
  apiKeys() {
    return this.request<ApiKeyView[]>('GET', '/developer/api-keys');
  }
  revokeApiKey(keyId: number) {
    return this.request<{ id: number; active: boolean }>('DELETE', `/developer/api-keys/${keyId}`);
  }
  /** 明文找不回来，所以轮换是「丢了怎么办」的唯一出路。 */
  rotateApiKey(keyId: number) {
    return this.request<{ id: number; key: string; revoked_id: number; warning: string }>(
      'POST', `/developer/api-keys/${keyId}/rotate`,
    );
  }
  createWebhook(url: string, events: string[]) {
    return this.request<{ id: number; url: string; events: string[]; secret: string; signature_howto: string }>(
      'POST', '/developer/webhooks', { url, events },
    );
  }
  webhooks() {
    return this.request<WebhookView[]>('GET', '/developer/webhooks');
  }
  /** HOOK-002 投递记录。没有它，集成方报「我没收到」时两边都无法证明。 */
  webhookDeliveries(webhookId: number) {
    return this.request<WebhookDeliveryView[]>('GET', `/developer/webhooks/${webhookId}/deliveries`);
  }
  deleteWebhook(webhookId: number) {
    return this.request<{ deleted: number }>('DELETE', `/developer/webhooks/${webhookId}`);
  }

  // ---- 其余用户侧端点（闸门点名的零散项）----
  smsLogin(phone: string, smsCode: string) {
    return this.request<{ token: string; user: Me }>('POST', '/auth/login-sms', {
      phone, sms_code: smsCode,
    });
  }
  myCertifications() {
    return this.request<{ active: string[]; applications: CertificationApplicationView[] }>(
      'GET', '/users/me/certifications',
    );
  }
  publishTask(taskId: number) {
    return this.request<Task>('POST', `/tasks/${taskId}/publish`);
  }
  /** GEO-022 行程共享开关：到场类任务的安全功能，不是位置追踪。 */
  setTripShare(taskId: number, enabled: boolean) {
    return this.request<{ enabled: boolean }>('POST', `/tasks/${taskId}/trip-share?enabled=${enabled}`);
  }
  trip(taskId: number) {
    return this.request<{ shared: boolean; points: Array<{ lat: number; lng: number; at: string }> }>(
      'GET', `/tasks/${taskId}/trip`,
    );
  }
  sos(taskId: number, lat: number, lng: number) {
    return this.request<{ id: number; notified: number }>('POST', `/tasks/${taskId}/sos`, { lat, lng });
  }
  circleMembers(circleId: number) {
    return this.request<Array<{ user_id: number; nickname: string; credit_score: number }>>(
      'GET', `/circles/${circleId}/members`,
    );
  }
  removeCircleMember(circleId: number, userId: number) {
    return this.request<{ removed: number }>('POST', `/circles/${circleId}/members/${userId}/remove`);
  }
  rejectChangeOrder(contractId: number, orderId: number) {
    return this.request<{ id: number; status: string }>(
      'POST', `/contracts/${contractId}/change-orders/${orderId}/reject`,
    );
  }
  userContents(userId: number) {
    return this.request<ContentItem[]>('GET', `/users/${userId}/contents`);
  }
  createTicket(subject: string, body = '') {
    return this.request<{ id: number; status: string; reply: string }>('POST', '/support/tickets', { subject, body });
  }
  myTickets() {
    return this.request<Array<{ id: number; subject: string; body: string; status: string; reply: string; created_at: string }>>(
      'GET', '/support/tickets',
    );
  }
  /** ESCA-001 工单转纠纷**带上下文**：不带的话用户要把刚说过的话重说一遍，
   *  而两次陈述不一致会在纠纷里被当成翻供。 */
  escalateTicket(ticketId: number, taskId: number, reason: string) {
    return this.request<{ dispute_id: number; ticket_id: number }>(
      'POST', `/support/tickets/${ticketId}/escalate-to-dispute`, { task_id: taskId, reason },
    );
  }
  notificationPrefs() {
    return this.request<Array<{ category: string; enabled: boolean; label: string; forced?: boolean }>>(
      'GET', '/notifications/prefs',
    );
  }
  setNotificationPref(category: string, enabled: boolean) {
    return this.request<{ category: string; enabled: boolean }>(
      'PUT', `/notifications/prefs?category=${encodeURIComponent(category)}&enabled=${enabled}`,
    );
  }
  trendingTerms(limit = 10) {
    return this.request<Array<{ term: string; count: number }>>('GET', `/search/trending?limit=${limit}`);
  }
  searchSuggest(q: string) {
    return this.request<string[]>('GET', `/search/suggest?q=${encodeURIComponent(q)}`);
  }
  /** 13.C 客户端漏斗埋点。 */
  trackEvent(name: string, refType = '', refId = 0) {
    return this.request<{ ok: boolean }>('POST', '/events', { name, ref_type: refType, ref_id: refId });
  }
  knowledgeCards(category?: string, limit = 20) {
    const q = category ? `?category=${encodeURIComponent(category)}&limit=${limit}` : `?limit=${limit}`;
    return this.request<Array<{ id: number; category: string; title: string; body: string }>>(
      'GET', `/knowledge/cards${q}`,
    );
  }
  decompositionTemplate(category: string, q = '') {
    return this.request<{ found: boolean; items: DecompositionItem[] }>(
      'GET', `/knowledge/templates?category=${encodeURIComponent(category)}&q=${encodeURIComponent(q)}`,
    );
  }
  categoryDemand() {
    return this.request<Array<{ category: string; open_tasks: number; completed: number; gmv_cents: number; suppliers: number }>>(
      'GET', '/knowledge/category-demand',
    );
  }
  /** TAX-022 只开**平台服务费**那部分：执行者的劳务报酬平台没有开票资格，
   *  含糊其辞地「帮你开全额发票」是虚开，不是服务。 */
  requestInvoice(contractId: number, title: string, taxNo = '') {
    return this.request<{ id: number; status: string; amount_cents: number; scope: string }>(
      'POST', '/finance/invoices', { contract_id: contractId, title, tax_no: taxNo },
    );
  }
  myInvoices() {
    return this.request<Array<{ id: number; contract_id: number; title: string; amount_cents: number; status: string; created_at: string }>>(
      'GET', '/finance/invoices',
    );
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
