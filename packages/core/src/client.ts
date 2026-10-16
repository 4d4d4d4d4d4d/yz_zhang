// 平台 API SDK：Web 与 App 共用（13 号 spec「两端共享同一 API/BFF」）
import type {
  AssistantContract, SkillConceptAdminView, SkillConceptList, SkillConceptRow, SkillNormalizeResult, Cockpit, CapabilityProfile, SandboxModelAdminRow, SandboxModelInput, SandboxModelList, SandboxState, InfluenceLeaderboard, InfluenceMine, InfluenceLatestSnapshot, InfluenceProof, InfluencePublic, InfluenceVouchInput, InfluenceVouchRow, TaskDraftInput, TaskProfile, TaskProfileView, ContractReview, GigAlong, GigAvailabilityInput, GigAvailabilityView, GigNearby, GigPlaceRow, GigQuote, OpcCalendar, OpcEntryInput, OpcEntryRow, OpcExport, OpcProfileInput, OpcProfileView, OpcSummary, PackAnswer, PackEnableResult, PackImportResult, PackValidation, RadarKnowledgeDraft, RadarSignal, LegalFaqInput, LegalFaqRow, ScenarioPackAdminListRow, ScenarioPackAdminRow, ScenarioPackCard, NbAnswer, NbExport, NbKind, NbMethod, NbMethodDraft, NbNote, NbNoteBrief, NbNoteInput, NbNotePatch, NbReference, NbStatus, NbSummary, NbTodoDraft, NbTodoInput, WbBreakdown, WbItem, WbItemDetail, WbItemInput, WbItemPatch, WbLog, WbMemory, WbOverview, WbProject, WbRoutine, WbRoutineHealth, WbRoutineInput, WbRoutinePatch, WbRoutineRun, WbRunStatus, WbStatus, WbStep,
  CommercialReadiness,
  AgentProfileView,
  PayoutProposalView,
  OrganizationRecordInput, OrganizationRecordView,
  MachineMandateInput, MachineMandateView, MachineActionView,
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
  FollowListItem,
  TaskCreateInput,
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
  KnowledgeAdminOverview,
  KnowledgeCalibrationPair,
  KnowledgeCluster,
  ExperienceToolDraft,
  ReusableUnit,
  ReusableUnitDetail,
  ReusableUnitDistillInput,
  ReusableUnitKind,
  KnowledgeClusterDetail,
  KnowledgeClusterList,
  KnowledgeThresholdView,
  KnowledgeUndecidedRow,
  DecompositionItem,
  DecompositionNodePatch,
  Dispute,
  DisputeStatement,
  Conversation,
  InvitationItem,
  Me,
  Message,
  Mission,
  MissionEvent,
  MissionDraftDecision,
  MissionSummary,
  MissionMethodDraft,
  XappCatalog,
  XappPlan,
  XappGrant,
  XappGrantRevoked,
  XappNext,
  XappRun,
  XappRunDetail,
  XappStepInput,
  XappStepOutcome,
  MissionSummarySaved,
  AssistantCosts,
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
  LedgerRow,
  PayoutAccountView,
  SosResult,
  ChangeOrderView,
  WithdrawRequestRow,
  SuspiciousActivityRow,
  BanImpactView,
  ReviewQueuesView,
  InvoiceRow,
  NotificationPrefsView,
  PendingTeamRow,
  PendingCertificationRow,
  PendingUploadRow,
  AdminTicketRow,
  AnnouncementAudience,
  AnnouncementPreview,
  AnnouncementRevoked,
  AnnouncementRow,
  AnnouncementSent,
  MyTicket,
  TicketClaimed,
  TicketReplied,
  SecurityBoardView,
  AdminAuditRow,
  PlatformFinanceView,
  AdminList,
  PlatformSettleApproved,
  PlatformSettlePending,
  PlatformSettleRequestRow,
  TeamInviteCreated,
  TeamInviteLink,
  TeamInvitePreview,
  ApiKeyQuota,
  ApiKeyRate,
  ApiKeyUsageView,
  PeriodQuery,
  PlatformFinanceExport,
  PlatformFinancePeriods,
  AuditChainReport,
  AuditLogExport,
  AuditLogFilter,
  WithdrawQueueFilter,
  VentureInvitationView,
  AdminRoleCatalog,
  AdminRoleKey,
  AdminRow,
} from './types';
import { isCloudAiRequest } from './sandbox';

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
  /** SBX-102 隐私沙箱开着吗：开着时，把原文交给云端 AI 的请求在发出之前就拦下（128 号 spec） */
  sandbox?: () => boolean;
}

/** 查询串：跳过 undefined / 空串 / false */
function qs(params: object): string {
  const pairs = Object.entries(params as Record<string, unknown>)
    .filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== false)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`);
  return pairs.length ? `?${pairs.join('&')}` : '';
}

export class PlatformClient {
  constructor(private opts: ClientOptions) {}

  private async request<T>(method: string, path: string, body?: unknown,
                           extraHeaders?: Record<string, string>): Promise<T> {
    return (await this.send<T>(method, path, body, extraHeaders)).data;
  }

  /** ADMIN-061 / PAY-043 分页列表（143 号 spec）：响应体照旧是数组，总条数在响应头 `X-Total-Count`。
   *  老服务端没有这个头时 `total` 是 null，界面按「不知道总数」显示。 */
  private async requestPage<T>(path: string): Promise<{ items: T[]; total: number | null }> {
    const { data, res } = await this.send<T[]>('GET', path);
    const raw = (res as { headers?: { get?: (k: string) => string | null } }).headers?.get?.('X-Total-Count');
    return { items: Array.isArray(data) ? data : [], total: raw == null || raw === '' ? null : Number(raw) };
  }

  private async send<T>(method: string, path: string, body?: unknown,
                        extraHeaders?: Record<string, string>): Promise<{ data: T; res: Response }> {
    if (this.opts.sandbox?.() && isCloudAiRequest(method, path)) {
      // 不发请求：原文一个字也不出设备
      throw new ApiError(409, 'sandbox_cloud_ai_blocked', '隐私沙箱开着：这类助手的活在本机做');
    }
    const doFetch = this.opts.fetchImpl ?? fetch;
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...extraHeaders };
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
    return { data: data as T, res };
  }

  // ---- auth / account ----
  register(phone: string, password: string, nickname: string, smsCode = '') {
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
    weekly_slots?: import('./types').WeeklySlot[];
    limited_capacity?: boolean;
  }) {
    return this.request<Me>('PATCH', '/users/me', patch);
  }
  /** ACC-020 实名核验。**HTTP 200 不等于通过**：供应商可能转人工，
   *  此时 `is_verified: false, status: 'manual_review'`。此前这里只声明了
   *  `is_verified`，网页于是在转人工时照样弹「实名认证成功」。 */
  verifyIdentity(realName: string, idNumber: string) {
    return this.request<{ is_verified: boolean; status: 'verified' | 'manual_review' }>('POST', '/users/me/verify', {
      real_name: realName, id_number: idNumber,
    });
  }
  discoverSpaces(q = '', after = 0) {
    return this.request<{ items: import('./types').SpaceSummary[]; next_cursor: number | null }>('GET', `/spaces?q=${encodeURIComponent(q)}&after=${after}`);
  }
  personalSpace(userId: number) { return this.request<import('./types').PersonalSpace>('GET', `/spaces/${userId}`); }
  ownSpace() { return this.request<import('./types').OwnSpace>('GET', '/spaces/me'); }
  saveSpace(body: Pick<import('./types').OwnSpace, 'revision' | 'published' | 'headline' | 'introduction' | 'theme' | 'items'>) {
    return this.request<import('./types').OwnSpace>('PUT', '/spaces/me', body);
  }
  publicProfile(userId: number) {
    return this.request<Partial<Me>>('GET', `/users/${userId}`);
  }

  /** SPACE-024 合作驾驶舱：树、关键路径、预算账、预警（只给母任务发布方） */
  cockpit(taskId: number) { return this.request<Cockpit>('GET', `/tasks/${taskId}/cockpit`); }

  // ---- PWB 个人工作台（116 号 spec）：我的任务、进度与助手 ----
  workbenchOverview() { return this.request<WbOverview>('GET', '/workbench/overview'); }
  workbenchProjects(includeArchived = false) {
    return this.request<WbProject[]>('GET', `/workbench/projects${includeArchived ? '?include_archived=true' : ''}`);
  }
  createWorkbenchProject(name: string, color: WbProject['color'] = 'clay') {
    return this.request<WbProject>('POST', '/workbench/projects', { name, color });
  }
  updateWorkbenchProject(id: number, patch: Partial<Pick<WbProject, 'name' | 'color' | 'archived' | 'sort'>>) {
    return this.request<WbProject>('PATCH', `/workbench/projects/${id}`, patch);
  }
  deleteWorkbenchProject(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/workbench/projects/${id}`); }
  workbenchItems(filter: { project_id?: number; status?: WbStatus; view?: 'all' | 'today' | 'overdue' | 'week' | 'open'; q?: string } = {}) {
    const qs = Object.entries(filter).filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');
    return this.request<WbItem[]>('GET', `/workbench/items${qs ? `?${qs}` : ''}`);
  }
  createWorkbenchItem(input: WbItemInput) {
    return this.request<WbItem>('POST', '/workbench/items', input);
  }
  workbenchItem(id: number) { return this.request<WbItemDetail>('GET', `/workbench/items/${id}`); }
  updateWorkbenchItem(id: number, patch: WbItemPatch) {
    return this.request<WbItem>('PATCH', `/workbench/items/${id}`, patch);
  }
  deleteWorkbenchItem(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/workbench/items/${id}`); }
  workbenchLogs(id: number) { return this.request<WbLog[]>('GET', `/workbench/items/${id}/logs`); }
  addWorkbenchLog(id: number, body: string) {
    return this.request<WbLog>('POST', `/workbench/items/${id}/logs`, { body });
  }
  /** 助手拆清单：只返回草稿，确认后调 `addWorkbenchChildren` */
  workbenchBreakdown(id: number) {
    return this.request<WbBreakdown>('POST', `/workbench/items/${id}/breakdown`);
  }
  addWorkbenchChildren(id: number, steps: WbStep[]) {
    return this.request<WbItemDetail>('POST', `/workbench/items/${id}/children`, { steps });
  }
  workbenchMemories() {
    return this.request<{ limit: number; items: WbMemory[] }>('GET', '/workbench/memories');
  }
  addWorkbenchMemory(content: string) {
    return this.request<WbMemory>('POST', '/workbench/memories', { content });
  }
  deleteWorkbenchMemory(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/workbench/memories/${id}`); }
  workbenchRoutines() { return this.request<WbRoutine[]>('GET', '/workbench/routines'); }
  createWorkbenchRoutine(input: WbRoutineInput) {
    return this.request<WbRoutine>('POST', '/workbench/routines', input);
  }
  updateWorkbenchRoutine(id: number, patch: WbRoutinePatch) {
    return this.request<WbRoutine>('PATCH', `/workbench/routines/${id}`, patch);
  }
  deleteWorkbenchRoutine(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/workbench/routines/${id}`); }
  runWorkbenchRoutine(id: number) {
    return this.request<{ status: WbRunStatus; output: string; routine: WbRoutine }>('POST', `/workbench/routines/${id}/run`);
  }
  /** REL-105 最近 30 次运行的健康度（130 号 spec） */
  workbenchRoutineHealth(id: number) { return this.request<WbRoutineHealth>('GET', `/workbench/routines/${id}/health`); }
  workbenchRoutineRuns(id: number) {
    return this.request<WbRoutineRun[]>('GET', `/workbench/routines/${id}/runs`);
  }

  // ---- KB-100 个人知识库（122 号 spec） ----
  notebookNotes(filter: { q?: string; tag?: string; status?: NbStatus; kind?: NbKind; limit?: number } = {}) {
    const p = new URLSearchParams();
    if (filter.q) p.set('q', filter.q);
    if (filter.tag) p.set('tag', filter.tag);
    if (filter.status) p.set('status', filter.status);
    if (filter.kind) p.set('kind', filter.kind);
    if (filter.limit) p.set('limit', String(filter.limit));
    const qs = p.toString();
    return this.request<NbNoteBrief[]>('GET', `/notebook/notes${qs ? `?${qs}` : ''}`);
  }
  /** 随手记：一句话、一段纪要或一个链接（服务端不抓取链接内容） */
  createNote(input: NbNoteInput) {
    return this.request<NbNote>('POST', '/notebook/notes', {
      body: input.body, title: input.title, url: input.url, kind: input.kind,
      tags: input.tags, status: input.status, project_id: input.project_id,
    });
  }
  note(id: number) { return this.request<NbNote>('GET', `/notebook/notes/${id}`); }
  updateNote(id: number, patch: NbNotePatch) {
    return this.request<NbNote>('PATCH', `/notebook/notes/${id}`, {
      revision: patch.revision, title: patch.title, body: patch.body, url: patch.url, kind: patch.kind,
      tags: patch.tags, status: patch.status, pinned: patch.pinned, project_id: patch.project_id,
    });
  }
  deleteNote(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/notebook/notes/${id}`); }
  notebookSummary() { return this.request<NbSummary>('GET', '/notebook/summary'); }
  /** 从自己的笔记里找答案：摘录式、带出处 */
  askNotebook(q: string) { return this.request<NbAnswer>('POST', '/notebook/ask', { q }); }
  relatedNotes(itemId: number) { return this.request<NbReference[]>('GET', `/notebook/related?item_id=${itemId}`); }
  /** 纪要抽待办：只返回草稿，确认后调 `addNoteTodos` */
  extractNoteTodos(id: number) {
    return this.request<{ note_id: number; items: NbTodoDraft[] }>('POST', `/notebook/notes/${id}/extract-todos`);
  }
  addNoteTodos(id: number, items: NbTodoInput[], projectId?: number | null) {
    return this.request<WbItem[]>('POST', `/notebook/notes/${id}/todos`, { items, project_id: projectId });
  }
  /** 把几条笔记里的步骤收成方法草稿（不写库），确认后调 `createMethod` */
  distillMethod(noteIds: number[]) {
    return this.request<NbMethodDraft>('POST', '/notebook/methods/distill', { note_ids: noteIds });
  }
  notebookMethods() { return this.request<NbMethod[]>('GET', '/notebook/methods'); }
  createMethod(input: { name: string; description?: string; steps: WbStep[]; source_note_ids?: number[] }) {
    return this.request<NbMethod>('POST', '/notebook/methods', {
      name: input.name, description: input.description, steps: input.steps, source_note_ids: input.source_note_ids,
    });
  }
  updateMethod(id: number, patch: { name?: string; description?: string; steps?: WbStep[] }) {
    return this.request<NbMethod>('PATCH', `/notebook/methods/${id}`, {
      name: patch.name, description: patch.description, steps: patch.steps,
    });
  }
  deleteMethod(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/notebook/methods/${id}`); }
  /** 把方法套到工作台任务上：步骤变成它的清单子项 */
  applyMethod(id: number, itemId: number) {
    return this.request<WbItemDetail>('POST', `/notebook/methods/${id}/apply`, { item_id: itemId });
  }
  exportNotebook() { return this.request<NbExport>('GET', '/notebook/export'); }

  // ---- PACK-100 场景包（123 号 spec） ----
  scenarioPacks() { return this.request<ScenarioPackCard[]>('GET', '/packs'); }
  scenarioPack(key: string) { return this.request<ScenarioPackCard>('GET', `/packs/${encodeURIComponent(key)}`); }
  /** 启用＝把包里的方法、知识、例行任务复制进我的知识库与工作台；已启用时再调＝升级（只补新增的） */
  enablePack(key: string, withRoutines = true) {
    return this.request<PackEnableResult>('POST', `/packs/${encodeURIComponent(key)}/enable`, { with_routines: withRoutines });
  }
  /** `removeCopies`：删掉没改过的副本（改过的留着）；例行任务无论如何都会关掉 */
  disablePack(key: string, removeCopies = false) {
    return this.request<{ disabled: boolean; removed: number; kept_modified: number }>(
      'POST', `/packs/${encodeURIComponent(key)}/disable`, { remove_copies: removeCopies });
  }
  /** REL-107 问之前先看：这位助手要什么、给什么、不做什么、用哪些工具、哪些事必须你本人确认 */
  assistantContract(packKey: string, assistantKey: string) {
    return this.request<AssistantContract>('GET', `/packs/${encodeURIComponent(packKey)}/assistants/${encodeURIComponent(assistantKey)}/contract`);
  }
  askPackAssistant(key: string, assistantKey: string, q: string) {
    return this.request<PackAnswer>('POST', `/packs/${encodeURIComponent(key)}/assistants/${encodeURIComponent(assistantKey)}/ask`, { q });
  }
  packFeedback(key: string, helpful: boolean) {
    return this.request<{ recorded: boolean }>('POST', `/packs/${encodeURIComponent(key)}/feedback`, { helpful });
  }
  adminPacks() { return this.request<ScenarioPackAdminListRow[]>('GET', '/admin/packs'); }
  adminValidatePack(definition: Record<string, unknown>) {
    return this.request<PackValidation>('POST', '/admin/packs/validate', { definition });
  }
  adminCreatePack(definition: Record<string, unknown>) {
    return this.request<ScenarioPackAdminRow>('POST', '/admin/packs', { definition });
  }
  adminUpdatePack(id: number, definition: Record<string, unknown>) {
    return this.request<ScenarioPackAdminRow>('PUT', `/admin/packs/${id}`, { definition });
  }
  adminSubmitPack(id: number) { return this.request<ScenarioPackAdminRow>('POST', `/admin/packs/${id}/submit`); }
  /** 四眼：写它的人不能自己批 */
  adminApprovePack(id: number) { return this.request<ScenarioPackAdminRow>('POST', `/admin/packs/${id}/approve`); }
  adminRejectPack(id: number) { return this.request<ScenarioPackAdminRow>('POST', `/admin/packs/${id}/reject`); }
  adminRetirePack(id: number, reason: string) {
    return this.request<ScenarioPackAdminRow>('POST', `/admin/packs/${id}/retire`, { reason });
  }
  adminPackRadar() { return this.request<RadarSignal[]>('GET', '/admin/packs/radar'); }
  /** SCN-112 雷达上的一条信号起草成目标场景包里的一条知识（只出草稿，空要人填，上线四眼） */
  adminDraftKnowledgeFromRadar(input: { source: RadarSignal['source']; key: string; pack_key: string }) {
    return this.request<RadarKnowledgeDraft>('POST', '/admin/packs/radar/draft-knowledge', input);
  }
  adminImportPackSeeds() { return this.request<PackImportResult>('POST', '/admin/packs/import-seeds'); }

  // ---- OPC-100 一人公司（124 号 spec） ----
  opcProfile() { return this.request<OpcProfileView>('GET', '/opc/profile'); }
  saveOpcProfile(input: OpcProfileInput) {
    return this.request<OpcProfileView>('PUT', '/opc/profile', {
      entity: input.entity, vat: input.vat, vat_period: input.vat_period, small_low_profit: input.small_low_profit,
    });
  }
  /** `period`：2026-10（月）、2026-Q3（季）、2026（年） */
  opcEntries(filter: { period?: string; kind?: 'income' | 'expense' } = {}) {
    const p = new URLSearchParams();
    if (filter.period) p.set('period', filter.period);
    if (filter.kind) p.set('kind', filter.kind);
    const qs = p.toString();
    return this.request<OpcEntryRow[]>('GET', `/opc/entries${qs ? `?${qs}` : ''}`);
  }
  addOpcEntry(input: OpcEntryInput) {
    return this.request<OpcEntryRow>('POST', '/opc/entries', {
      occurred_on: input.occurred_on, kind: input.kind, amount_cents: input.amount_cents, tax_cents: input.tax_cents,
      category: input.category, counterparty: input.counterparty, invoice_no: input.invoice_no,
      invoice_kind: input.invoice_kind, note: input.note,
    });
  }
  updateOpcEntry(id: number, patch: { category?: string; counterparty?: string; invoice_no?: string; note?: string }) {
    return this.request<OpcEntryRow>('PATCH', `/opc/entries/${id}`, {
      category: patch.category, counterparty: patch.counterparty, invoice_no: patch.invoice_no, note: patch.note,
    });
  }
  deleteOpcEntry(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/opc/entries/${id}`); }
  /** 把平台上已到账的报酬记进底稿（按流水去重，导几次都一样） */
  importPlatformIncome() { return this.request<{ imported: number }>('POST', '/opc/entries/import-platform', {}); }
  opcSummary(period?: string) {
    return this.request<OpcSummary>('GET', `/opc/summary${period ? `?period=${encodeURIComponent(period)}` : ''}`);
  }
  exportOpcBooks(period: string) { return this.request<OpcExport>('GET', `/opc/export?period=${encodeURIComponent(period)}`); }
  opcCalendar(days = 120) { return this.request<OpcCalendar>('GET', `/opc/calendar?days=${days}`); }
  /** 合同原文不保存：体检完就丢 */
  reviewContract(text: string, role: 'party_a' | 'party_b' | 'unknown' = 'unknown') {
    return this.request<ContractReview>('POST', '/opc/contract-review', { text, role });
  }

  // ---- PROF-100 任务画像与能力画像（126 号 spec） ----
  /** 发布页实时调用：还缺什么、价格在什么位置、有什么风险（不落库） */
  taskDraftProfile(draft: TaskDraftInput) {
    return this.request<TaskProfile>('POST', '/profiles/task-draft', {
      title: draft.title, description: draft.description, category: draft.category, budget_cents: draft.budget_cents,
      is_remote: draft.is_remote, city: draft.city, lat: draft.lat, deadline: draft.deadline,
      required_skills: draft.required_skills, acceptance_criteria: draft.acceptance_criteria,
    });
  }
  taskProfile(taskId: number) { return this.request<TaskProfileView>('GET', `/tasks/${taskId}/profile`); }
  myCapability() { return this.request<CapabilityProfile>('GET', '/users/me/capability'); }
  userCapability(userId: number) { return this.request<CapabilityProfile>('GET', `/users/${userId}/capability`); }

  // ---- INF-100 影响力与专家等级（127 号 spec）：不可转让——SDK 里也没有任何转让方法 ----
  myInfluence() { return this.request<InfluenceMine>('GET', '/influence/me'); }
  userInfluence(userId: number) { return this.request<InfluencePublic>('GET', `/users/${userId}/influence`); }
  influenceLeaderboard(category: string) {
    return this.request<InfluenceLeaderboard>('GET', `/influence/leaderboard?category=${encodeURIComponent(category)}`);
  }
  /** 拿自己在这个类目的影响力为别人作保：对方做成了你得一点，对方纠纷败诉罚没担保额的一半 */
  createVouch(input: InfluenceVouchInput) {
    return this.request<InfluenceVouchRow>('POST', '/influence/vouches', {
      subject_id: input.subject_id, category: input.category, task_id: input.task_id ?? null, stake: input.stake,
      note: input.note ?? '',
    });
  }
  withdrawVouch(id: number) { return this.request<{ withdrawn: boolean }>('DELETE', `/influence/vouches/${id}`); }
  latestInfluenceSnapshot() { return this.request<InfluenceLatestSnapshot>('GET', '/influence/snapshots/latest'); }
  /** 我在最近一次快照里的每一条，附 Merkle 路径：拿锚定的根就能自己验 */
  myInfluenceProof() { return this.request<InfluenceProof>('GET', '/influence/me/proof'); }

  // ---- SBX-100 端侧隐私沙箱（128 号 spec）：本机助手不走这里，这里只有开关与模型目录 ----
  mySandbox() { return this.request<SandboxState>('GET', '/users/me/sandbox'); }
  setSandbox(enabled: boolean) { return this.request<SandboxState>('PUT', '/users/me/sandbox', { enabled }); }
  sandboxModels() { return this.request<SandboxModelList>('GET', '/sandbox/models'); }
  adminSandboxModels() { return this.request<SandboxModelAdminRow[]>('GET', '/admin/sandbox/models'); }
  createSandboxModel(input: SandboxModelInput) { return this.request<SandboxModelAdminRow>('POST', '/admin/sandbox/models', input); }
  updateSandboxModel(id: number, input: SandboxModelInput) {
    return this.request<SandboxModelAdminRow>('PATCH', `/admin/sandbox/models/${id}`, input);
  }
  /** 四眼：登记的人不能自己上架；上架时必须有 sha256、https 地址、大小、许可证、最低内存 */
  publishSandboxModel(id: number) { return this.request<SandboxModelAdminRow>('POST', `/admin/sandbox/models/${id}/publish`); }
  retireSandboxModel(id: number, reason: string) {
    return this.request<SandboxModelAdminRow>('POST', `/admin/sandbox/models/${id}/retire`, { reason });
  }

  // ---- SKL-100 技能概念表（135 号 spec）：「VI 设计」按「品牌设计」匹配 ----
  skillConcepts() { return this.request<SkillConceptList>('GET', '/skills/concepts'); }
  normalizeSkills(skills: string[]) {
    return this.request<SkillNormalizeResult>('GET', `/skills/normalize?skills=${encodeURIComponent(skills.join(','))}`);
  }
  adminSkillConcepts() { return this.request<SkillConceptAdminView>('GET', '/admin/skill-concepts'); }
  upsertSkillConcept(name: string, aliases: string[]) {
    return this.request<SkillConceptRow>('POST', '/admin/skill-concepts', { name, aliases });
  }
  retireSkillConcept(id: number) { return this.request<SkillConceptRow>('POST', `/admin/skill-concepts/${id}/retire`); }

  // ---- GIG-100 接单者（125 号 spec） ----
  gigAvailability() { return this.request<GigAvailabilityView>('GET', '/gig/available'); }
  /** 接下来几个小时有空：附近有新单就推给我（每段最多 6 条），到点自动失效、位置随之删除 */
  setGigAvailable(input: GigAvailabilityInput) {
    return this.request<GigAvailabilityView>('PUT', '/gig/available', {
      lat: input.lat, lng: input.lng, radius_km: input.radius_km, hours: input.hours, categories: input.categories,
    });
  }
  stopGigAvailable() { return this.request<GigAvailabilityView>('DELETE', '/gig/available'); }
  /** 不给坐标时用「现在有空」里的位置 */
  gigNearby(at?: { lat: number; lng: number; radius_km?: number }) {
    const p = new URLSearchParams();
    if (at) { p.set('lat', String(at.lat)); p.set('lng', String(at.lng)); if (at.radius_km) p.set('radius_km', String(at.radius_km)); }
    const qs = p.toString();
    return this.request<GigNearby>('GET', `/gig/nearby${qs ? `?${qs}` : ''}`);
  }
  /** 顺路单：起点是一个常用地点或当前位置，终点是一个常用地点 */
  gigAlong(input: { to_place: number; from_place?: number; from_lat?: number; from_lng?: number; max_detour_km?: number }) {
    const p = new URLSearchParams({ to_place: String(input.to_place) });
    if (input.from_place !== undefined) p.set('from_place', String(input.from_place));
    if (input.from_lat !== undefined && input.from_lng !== undefined) { p.set('from_lat', String(input.from_lat)); p.set('from_lng', String(input.from_lng)); }
    if (input.max_detour_km) p.set('max_detour_km', String(input.max_detour_km));
    return this.request<GigAlong>('GET', `/gig/along?${p.toString()}`);
  }
  gigPlaces() { return this.request<GigPlaceRow[]>('GET', '/gig/places'); }
  addGigPlace(name: string, lat: number, lng: number) {
    return this.request<GigPlaceRow>('POST', '/gig/places', { name, lat, lng });
  }
  deleteGigPlace(id: number) { return this.request<{ deleted: boolean }>('DELETE', `/gig/places/${id}`); }
  /** 报价参考：给一单（task_id）或一个类目 */
  gigQuote(input: { task_id?: number; category?: string; city?: string }) {
    return this.request<GigQuote>('POST', '/gig/quote', { task_id: input.task_id, category: input.category, city: input.city });
  }

  // ---- tasks ----
  /** APP-060 `ip_assignment` 是**必需参数**，不是可选的。
   *
   *  服务端从 V77 起强制它（留空直接 400），但 SDK 的签名是
   *  `Partial<Task> & {...}`——每个业务字段都可选，于是 App 漏掉它时
   *  **类型系统认为这段代码完全正确**，而那个「发布」按钮每次点击都返回 400，
   *  一直到 V88 才被探针发现。
   *
   *  **服务端的「必填」如果没有变成类型上的「必填」，那它只是一句口头约定。**
   *  放在类型里比再加一条测试好：它覆盖所有客户端（包括以后写的那个）、
   *  在写代码时就红、而且不需要有人记得去写那条测试。
   */
  createTask(input: TaskCreateInput) {
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
    return this.request<{ id: number; status: string }>('POST', `/tasks/${taskId}/applications`, {
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
    return this.request<Array<{ id: number; user_id: number; kind: string; content: string; images: string[]; created_at: string }>>(
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

  /** VND-011 充值两阶段：模拟通道即时 succeeded；真实通道返回 pending + pay_url。
   *
   *  FIN-073 `idempotencyKey` 必填：同一次操作的重试用同一个键（见 `OperationKey`），
   *  服务端回放第一次的结果而不是再充一次。不带键服务端直接 400。 */
  topup(amountCents: number, idempotencyKey: string) {
    return this.request<{
      order_no: string;
      status: 'succeeded' | 'pending';
      available_cents?: number;
      pay_url?: string;
    }>('POST', '/wallet/topup', { amount_cents: amountCents },
      { 'Idempotency-Key': idempotencyKey });
  }
  getPayoutAccount() {
    return this.request<PayoutAccountView>('GET', '/wallet/payout-account');
  }
  bindPayoutAccount(accountNo: string, holderName: string, kind: 'bank' | 'alipay' = 'bank') {
    return this.request<{ bound: boolean; kind: string; account_no: string }>(
      'PUT', '/wallet/payout-account', { kind, account_no: accountNo, holder_name: holderName },
    );
  }
  /** PAY-005 提现。**前置是先绑收款账户**（`no_payout_account`），
   *  所以任何给出这个按钮的端，都必须同时给出 `bindPayoutAccount` 的入口。
   *
   *  `message` 是大额进人审时服务端给的**中性话术**（AML-030/031 tipping-off）：
   *  原样显示，**绝不能自己编一句「你的提现触发了风控」**——那等于告诉他
   *  哪条规则命中了。此前类型里没有这个字段，于是没有任何界面显示得了它。 */
  withdraw(amountCents: number, idempotencyKey: string) {
    // CONC-067（V138）出款两阶段：银行结果不明时是 processing——钱在冻结里，补偿 job 按同一个单号结
    return this.request<{ status: 'done' | 'pending_review' | 'processing'; request_id?: number; message?: string; available_cents: number; frozen_cents: number }>(
      'POST', '/wallet/withdraw', { amount_cents: amountCents },
      { 'Idempotency-Key': idempotencyKey },
    );
  }
  /** PAY-040 提现复核队列（管理端）。V82 的豁免表里写着这两个动作
   *  「在管理后台做」——而管理后台里此前没有这一条，**那句话是一个
   *  没人核对过的承诺**。 */
  withdrawRequests(status = 'pending') {
    return this.request<WithdrawRequestRow[]>(
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
  /** NTF-064 起可以定时（scheduledAt 为带时区的 ISO 时间，不填就马上发），响应多了 id / status（151 号 spec） */
  /** NTF-066（159 号 spec）起可按城市与人群定向（target 不填 = 全体） */
  broadcastAnnouncement(title: string, body = '', verifiedOnly = false, scheduledAt?: string,
    target: { city?: string; audience?: AnnouncementAudience } = {}) {
    return this.request<AnnouncementSent>('POST', '/admin/announcements', {
      title, body, verified_only: verifiedOnly, scheduled_at: scheduledAt ?? null,
      city: target.city ?? '', audience: target.audience ?? 'all',
    });
  }
  /** NTF-064 发之前先看：会送给多少人、要留意的地方。不发、不落库 */
  previewAnnouncement(title: string, body = '', verifiedOnly = false,
    target: { city?: string; audience?: AnnouncementAudience } = {}) {
    return this.request<AnnouncementPreview>('POST', '/admin/announcements/preview', {
      title, body, verified_only: verifiedOnly, city: target.city ?? '', audience: target.audience ?? 'all',
    });
  }
  /** NTF-064 公告记录（最新的在前） */
  announcements(status = '') {
    return this.request<AnnouncementRow[]>('GET', `/admin/announcements${qs({ status })}`);
  }
  /** NTF-064 取消还没发出的定时公告 */
  cancelAnnouncement(id: number, reason = '') {
    return this.request<AnnouncementRow>('POST', `/admin/announcements/${id}/cancel`, { reason });
  }
  /** NTF-064 撤回已发出的公告：用户通知中心里那条会改成「已撤回」并显示理由；推送收不回来 */
  revokeAnnouncement(id: number, reason: string) {
    return this.request<AnnouncementRevoked>('POST', `/admin/announcements/${id}/revoke`, { reason });
  }
  // ---- AML 合规官视图（全部 require_admin，AML-030 tipping-off）----
  /** AML-021 可疑活动清单。V55 就建好了这三个端点，**SDK 里一个都没有**
   *  （它们在 /admin 下，被覆盖闸门整体跳过了），于是标记躺在库里没人复核。 */
  amlActivities(status = 'pending') {
    return this.request<{ items: SuspiciousActivityRow[]; note: string }>(
      'GET', `/admin/aml/activities?status=${status}`,
    );
  }
  amlStats() {
    return this.request<Record<string, number>>('GET', '/admin/aml/stats');
  }
  /** `decision`: cleared（复核无问题）/ to_report（待报送）/ reported（已报送）。 */
  reviewAmlActivity(activityId: number, decision: 'cleared' | 'to_report' | 'reported', note = '') {
    return this.request<{ id: number; status: string }>(
      'POST', `/admin/aml/activities/${activityId}/review`, { decision, note },
    );
  }
  platformFinance() {
    return this.request<PlatformFinanceView>(
      'GET', '/admin/platform-finance',
    );
  }
  /** 小额一步划出；达到双人确认金额时返回 `PlatformSettlePending`（148 号 spec），钱还没动 */
  settlePlatform(amountCents: number, memo = '平台收入结算') {
    return this.request<{ settled_cents: number; balance_cents: number } | PlatformSettlePending>(
      'POST', '/admin/platform-finance/settle', { amount_cents: amountCents, memo },
    );
  }
  settleRequests(status: 'awaiting_second' | 'settled' | 'rejected' = 'awaiting_second') {
    return this.request<PlatformSettleRequestRow[]>('GET', `/admin/platform-finance/settle-requests?status=${status}`);
  }
  approveSettle(requestId: number) {
    return this.request<PlatformSettleApproved>('POST', `/admin/platform-finance/settle-requests/${requestId}/approve`);
  }
  rejectSettle(requestId: number, reason = '') {
    return this.request<PlatformSettleRequestRow>('POST', `/admin/platform-finance/settle-requests/${requestId}/reject`, { reason });
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
    return this.request<LedgerRow[]>('GET', '/wallet/ledger');
  }

  // ---- orchestrator（Agent Harness：发任务给人=工具调用）----
  createMission(body: { goal: string; detail?: string; category?: string; budget_cap_cents: number; max_iterations?: number; acceptance_criteria?: string[];
    allow_agents?: boolean; allow_tools?: boolean }) {
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
  blockchainStatus() {
    return this.request<{ status: string; verified: boolean; note?: string; chain_id?: number;
      contract_address?: string; confirmations?: number; seq_from?: number; seq_to?: number;
      digest?: string; block_number?: number; block_hash?: string }>('GET', '/anchors/blockchain');
  }

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
  /** AGT-084 授权（或收回）编排使用平台经验工具：只影响之后分发的步骤（131 号 spec） */
  setMissionTools(id: number, allowTools: boolean) {
    return this.request<Mission>('PUT', `/missions/${id}/tools`, { allow_tools: allowTools });
  }
  /** AGT-084 采用编排生成的草稿（只是标记，不会替你发给任何人） */
  adoptMissionDraft(missionId: number, stepId: number, invocationId: number) {
    return this.request<MissionDraftDecision>('POST', `/missions/${missionId}/steps/${stepId}/drafts/${invocationId}/adopt`);
  }
  discardMissionDraft(missionId: number, stepId: number, invocationId: number) {
    return this.request<MissionDraftDecision>('POST', `/missions/${missionId}/steps/${stepId}/drafts/${invocationId}/discard`);
  }
  /** AGT-091 编排复盘：花了多少、几轮、哪些步骤整改过、下一步建议（133 号 spec） */
  missionSummary(id: number) { return this.request<MissionSummary>('GET', `/missions/${id}/summary`); }
  /** AGT-092 把复盘存进个人知识库（标签「编排复盘」；再存一次更新同一条） */
  saveMissionSummary(id: number) { return this.request<MissionSummarySaved>('POST', `/missions/${id}/summary/save`); }
  // ---- XAPP 跨 App 助手（161 号 spec）----
  /** 能授权的动作、只能本人亲手做的红线动作、通道顺序 */
  xappCatalog() { return this.request<XappCatalog>('GET', '/xapp/catalog'); }
  /** XAPP-015 一句目标 → 计划草稿（不发起）。隐私沙箱开着时被拦下：用 planXappLocally 在本机出 */
  planXapp(grantId: number, goal: string) { return this.request<XappPlan>('POST', '/xapp/plan', { grant_id: grantId, goal }); }
  createXappGrant(input: { apps: string[]; actions: string[]; days: number; device_label?: string; allow_cloud_vision?: boolean }) {
    return this.request<XappGrant>('POST', '/xapp/grants', {
      apps: input.apps, actions: input.actions, days: input.days,
      device_label: input.device_label ?? '', allow_cloud_vision: input.allow_cloud_vision ?? false,
    });
  }
  xappGrants() { return this.request<XappGrant[]>('GET', '/xapp/grants'); }
  /** 撤销即停：用这个授权还在跑的执行全部叫停 */
  revokeXappGrant(id: number) { return this.request<XappGrantRevoked>('DELETE', `/xapp/grants/${id}`); }
  createXappRun(input: { grant_id: number; goal: string; executor: string; confirm_mode: 'each' | 'red_only'; steps: XappStepInput[] }) {
    return this.request<XappRunDetail>('POST', '/xapp/runs', {
      grant_id: input.grant_id, goal: input.goal, executor: input.executor,
      confirm_mode: input.confirm_mode, steps: input.steps,
    });
  }
  xappRuns() { return this.request<XappRun[]>('GET', '/xapp/runs'); }
  xappRun(id: number) { return this.request<XappRunDetail>('GET', `/xapp/runs/${id}`); }
  /** 执行器：拿下一步 */
  xappNext(runId: number) { return this.request<XappNext>('POST', `/xapp/runs/${runId}/next`); }
  /** 执行器：回报一步的结果 */
  xappReport(runId: number, stepId: number, ok: boolean, summary: string) {
    return this.request<XappStepOutcome>('POST', `/xapp/runs/${runId}/steps/${stepId}/result`, { ok, summary });
  }
  /** 本人确认：普通步确认后才派发；红线步确认表示「我自己做完了」 */
  confirmXappStep(runId: number, stepId: number) {
    return this.request<XappStepOutcome>('POST', `/xapp/runs/${runId}/steps/${stepId}/confirm`);
  }
  /** 一键叫停 */
  stopXappRun(runId: number, reason = '') { return this.request<XappRun>('POST', `/xapp/runs/${runId}/stop`, { reason }); }
  /** AGT-093 复盘一步蒸馏成「我的方法」草稿（154 号 spec）：先存复盘笔记作出处，只收做成了的步骤；确认后调 createMethod */
  distillMissionMethod(id: number) { return this.request<MissionMethodDraft>('POST', `/missions/${id}/summary/distill`); }
  /** REL-110 本月助手花了多少、上限多少 */
  assistantCosts() { return this.request<AssistantCosts>('GET', '/users/me/assistant-costs'); }
  cancelMission(id: number) {
    return this.request<Mission & { closed_open_tasks: number }>('POST', `/missions/${id}/cancel`);
  }

  // ---- decompose / knowledge ----
  propose(taskId: number) {
    return this.request<Decomposition>('POST', `/tasks/${taskId}/decompositions`);
  }
  /** 拆到一半关掉页面，回来接着拆（404 `no_decomposition_in_progress` 表示没有进行中的拆解）。 */
  currentDecomposition(taskId: number) {
    return this.request<Decomposition>('GET', `/tasks/${taskId}/decomposition`);
  }
  /** AI-DEC-041 往下长一层；给 `nodeIds` 则只拆这几步（不给时 JSON 里没有这个键 = 展开整个前沿）。 */
  expandDecomposition(decId: number, revision: number, nodeIds?: number[]) {
    return this.request<Decomposition>(
      'POST', `/decompositions/${decId}/expand`,
      { revision, node_ids: nodeIds },
    );
  }
  editDecompositionNode(decId: number, nodeId: number, revision: number, patch: DecompositionNodePatch) {
    return this.request<Decomposition>('PATCH', `/decompositions/${decId}/nodes/${nodeId}`,
      { revision, ...patch });
  }
  deleteDecompositionNode(decId: number, nodeId: number, revision: number) {
    return this.request<Decomposition>('DELETE',
      `/decompositions/${decId}/nodes/${nodeId}?revision=${revision}`);
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
      /** IM-060 在和谁聊：私聊是对方昵称、任务会话是任务标题、群是群名 */
      title: string;
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
    return this.request<{ answer: string; source: string | null; escalate_to_human: boolean; account_context: { available_cents: number } | null; ticket_id: number | null }>(
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
  /** SC-014 只放点名的、已交付的那几期（146 号 spec）。`expectedTotalCents` 是界面上给人看的合计：
   *  对不上（期间有一期状态变了）就整批不放，不会放出一笔没看到的钱 */
  releaseDelivered(contractId: number, idxs: number[], expectedTotalCents: number) {
    return this.request<Contract>('POST', `/contracts/${contractId}/milestones/release-delivered`,
      { idxs, expected_total_cents: expectedTotalCents });
  }
  /** SC-007b 变更单：金额、截止时间、范围三样可以单独改也可以一起改；只传要改的 */
  proposeChangeOrder(contractId: number, input: { new_amount_cents?: number; new_deadline?: string; scope_change?: string; reason?: string }) {
    // 不改的那几样传 undefined：JSON 序列化时整个键都不出现，服务端就当「这一样不改」
    return this.request<{ id: number; status: string; new_amount_cents: number; new_deadline: string | null; scope_change: string }>(
      'POST', `/contracts/${contractId}/change-orders`, {
        new_amount_cents: input.new_amount_cents, new_deadline: input.new_deadline || undefined,
        scope_change: input.scope_change || undefined, reason: input.reason ?? '',
      });
  }
  proposeChange(contractId: number, newAmountCents: number, reason = '') {
    return this.request<{ id: number; status: string; new_amount_cents: number; new_deadline: string | null; scope_change: string }>('POST', `/contracts/${contractId}/change-orders`, {
      new_amount_cents: newAmountCents, reason,
    });
  }
  /** SC-007 列出变更单。改造前**服务端根本没有这个接口**：
   *  提案建得出来，而对方拿不到 `order_id`，界面上就算有按钮也点不了。 */
  changeOrders(contractId: number) {
    return this.request<ChangeOrderView[]>('GET', `/contracts/${contractId}/change-orders`);
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
  /** CNT-022 关注。**幂等**——重复调用仍然是「已关注」。
   *
   *  改造前这是一个 `POST` toggle：手机上双击、或弱网下自动重试，
   *  用户刚关注的人就被取消了。旧签名没有保留，因为它兼容的是一个
   *  服务端已经不接受的动作（405），留着只会让下一个人以为它能用。
   */
  followUser(userId: number) {
    return this.request<{ following: boolean }>('PUT', `/users/${userId}/follow`);
  }
  unfollowUser(userId: number) {
    return this.request<{ following: boolean }>('DELETE', `/users/${userId}/follow`);
  }
  /** `following` 是**这个人关注了多少人**的计数；
   *  `viewer_following` 才是「我是否已关注他」，匿名时为 `null`
   *  （「没登录所以不知道」与「登录了但没关注」是两件事）。
   */
  followStats(userId: number) {
    return this.request<{ followers: number; following: number; viewer_following: boolean | null }>(
      'GET', `/users/${userId}/follow-stats`,
    );
  }
  /** CNT-023 谁关注了他 / 他关注了谁。游标分页（新的在前）。
   *  资料不公开的人，别人看他的列表得到 403——他的社交圈也不公开；
   *  别人看到的列表里也不会出现资料不公开的人。 */
  followers(userId: number, after = 0, limit = 20) {
    return this.request<{ items: FollowListItem[]; next_cursor: number | null }>(
      'GET', `/users/${userId}/followers?after=${after}&limit=${limit}`,
    );
  }
  following(userId: number, after = 0, limit = 20) {
    return this.request<{ items: FollowListItem[]; next_cursor: number | null }>(
      'GET', `/users/${userId}/following?after=${after}&limit=${limit}`,
    );
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
    return this.request<{
      task_id: number; title: string; status: string;
      summary: string; total_cost_cents: number; planned_budget_cents: number;
      /** AGT-090 按合约放款算的实付（与合作驾驶舱同一口径）；ready：所有步骤都已完成 */
      paid_cents: number; ready: boolean;
      duration_days: number | null;
      children_completed: number; children_total: number;
      deliverables: Array<{ task_id: number; title: string; executor_id: number | null; cost_cents: number; status: string }>;
    }>(
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
  /** LAW-001 法律常识问答。三种结局**含义完全不同**（97 号 spec）：
   *  - `refused_reason: 'high_risk'`：涉人身安全/刑事，唯一正确去处是**外部紧急渠道**，
   *    `remedy` 刻意为 `null`——在它旁边摆一个「发任务」按钮是把紧急情况降级成一笔生意；
   *  - `refused_reason: 'out_of_scope'`：知识库答不了，`remedy` 给出**机器可读**的补救
   *    （发一单法律咨询，类目由服务端从类目表取，客户端不许写死）；
   *  - `refused_reason: ''`：知识库命中。
   *  **不要只按 `refused` 分支**：那会把前两种渲染成同一段话。
   *  `disclaimer` 必须原样展示——平台给的是一般性法律信息，不是法律意见。 */
  legalAsk(question: string) {
    return this.request<{
      answer: string; disclaimer: string; refused: boolean;
      refused_reason: '' | 'high_risk' | 'out_of_scope';
      remedy: { action: string; category: string; label: string } | null;
      /** LAW-060（163 号 spec）运营上线的条目带出处（法规名与条号）；代码里的老条目与拒答为空串 */
      source: string;
    }>('POST', '/legal/ask', { question });
  }
  // ---- LAW-060 / SCN-114 法律常识库的运营草稿流（163 号 spec，合规管理员） ----
  adminLegalFaqs() { return this.request<LegalFaqRow[]>('GET', '/admin/legal/faqs'); }
  adminCreateLegalFaq(input: LegalFaqInput) { return this.request<LegalFaqRow>('POST', '/admin/legal/faqs', input); }
  adminUpdateLegalFaq(id: number, input: LegalFaqInput) { return this.request<LegalFaqRow>('PUT', `/admin/legal/faqs/${id}`, input); }
  /** 雷达上「法律问答答不上」的主题起草成一条草稿：回答与出处留「【待填写】」，填完才能提交 */
  adminLegalFaqFromRadar(topic: string) { return this.request<LegalFaqRow>('POST', '/admin/legal/faqs/radar-draft', { topic }); }
  adminSubmitLegalFaq(id: number) { return this.request<LegalFaqRow>('POST', `/admin/legal/faqs/${id}/submit`); }
  adminApproveLegalFaq(id: number) { return this.request<LegalFaqRow>('POST', `/admin/legal/faqs/${id}/approve`); }
  adminRejectLegalFaq(id: number) { return this.request<LegalFaqRow>('POST', `/admin/legal/faqs/${id}/reject`); }
  adminRetireLegalFaq(id: number, reason: string) { return this.request<LegalFaqRow>('POST', `/admin/legal/faqs/${id}/retire`, { reason }); }
  exportEvidence(disputeId: number) {
    /* `evidentiary_notice` 是这份证据包**证明力边界**的说明——尤其那句
     * 「平台处理决定**不是**法律意义上的仲裁裁决」。此前 SDK 没声明它，
     * 网页下载时用 `{...package, sha256}` 拼文件，于是把它整个丢掉了：
     * 用户交给律师的那份文件里，没有任何一句话说明它能证明什么、不能证明什么。 */
    return this.request<{
      package: Record<string, unknown>; sha256: string;
      integrity: {
        chain_valid: boolean | null; chain_entries: number | null;
        third_party_backed_to_seq: number; uncovered_entries: number;
        receipts: Array<Record<string, unknown>>;
      };
      evidentiary_notice: { signatures: string; chain: string; decision: string };
    }>(
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
  adminVendors() {
    return this.request<{
      vendors: Array<{ kind: string; provider: string; grade: string; calls_24h: number; success_rate: number | null }>;
      blocking_for_production: string[];
      commercial_readiness: CommercialReadiness;
    }>('GET', '/admin/vendors');
  }
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
  /** MOD-060 封禁影响面。**封禁前**调它——`banUser` 是不可逆的处置，
   *  而这个人手上可能有几笔在途合约和一笔托管资金。
   *
   *  此前这里的行内类型还漏了 `open_task_ids` / `open_task_count`：
   *  服务端一直在返回，而类型里没有，于是界面显示不出「几个招募中的任务
   *  会被下架」——又一次「声明了却不给 / 给了却不声明」（V89 那一类）。 */
  banImpact(userId: number) {
    return this.request<BanImpactView>('GET', `/admin/users/${userId}/ban-impact`);
  }
  /** SEC-061b 角色说明与我自己的角色（141 号 spec） */
  adminRoleCatalog() {
    return this.request<AdminRoleCatalog>('GET', '/admin/roles');
  }
  /** SEC-061b 管理员与角色：只有超级管理员能看、能改 */
  listAdmins() {
    return this.request<AdminList>('GET', '/admin/admins');
  }
  setAdminRoles(userId: number, roles: AdminRoleKey[]) {
    return this.request<AdminRow>('PUT', `/admin/admins/${userId}/roles`, { roles });
  }
  /** FIN-061 按期间的平台财务（144 号 spec） */
  platformFinancePeriods(params: PeriodQuery = {}) {
    return this.request<PlatformFinancePeriods>('GET', `/admin/platform-finance/periods${qs(params)}`);
  }
  exportPlatformFinancePeriods(params: PeriodQuery = {}) {
    return this.request<PlatformFinanceExport>('GET', `/admin/platform-finance/periods/export${qs(params)}`);
  }
  /** ADMIN-061 审计日志分页与筛选（143 号 spec）：带总条数 */
  adminAuditLogPage(params: AuditLogFilter & { limit?: number; offset?: number } = {}) {
    return this.requestPage<AdminAuditRow>(`/admin/audit-log${qs(params)}`);
  }
  /** ADMIN-061 导出 CSV：时间是北京时间并在表头写明；导出本身进审计 */
  exportAuditLog(params: AuditLogFilter = {}) {
    return this.request<AuditLogExport>('GET', `/admin/audit-log/export${qs(params)}`);
  }
  /** ADMIN-062 审计日志自检（149 号 spec）：哈希链从头走到链头，指出被改、被删、被绕过的位置 */
  verifyAuditChain() {
    return this.request<AuditChainReport>('GET', '/admin/audit-log/verify');
  }
  /** PAY-043 提现复核台筛选与分页（143 号 spec）：带总条数 */
  withdrawRequestsPage(params: WithdrawQueueFilter = {}) {
    return this.requestPage<WithdrawRequestRow>(`/wallet/withdraw-requests${qs(params)}`);
  }
  adminAuditLog(params: { action?: string; limit?: number; offset?: number } = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<AdminAuditRow[]>(
      'GET', `/admin/audit-log${qs ? `?${qs}` : ''}`,
    );
  }
  resolveReport(reportId: number, action: 'dismiss' | 'remove_content' | 'ban_user') {
    return this.request<{ id: number; status: string; action: string; effect: string }>(
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

  // ---- 运营侧的人审队列（76 号 spec）----
  //
  // 这一组以前**没有一条在 SDK 里**：服务端的队列是通的，而后台没有界面，
  // 于是「提交 → 等人看」的第二步永远不发生。团队企业核验更彻底——
  // 那两条端点此前压根不存在。
  /** QUEUE-011 人审队列概览（78 号 spec）：几件在等、最久多久、超没超 SLA。
   *
   *  催办 job、后台首屏、测试共用这一份——各自去数库就会出现三份不一样的答案。 */
  reviewQueues() {
    return this.request<ReviewQueuesView>('GET', '/admin/queues');
  }
  /** TEAM-031 待核验的团队企业信息（执照影像是鉴权 URL，不是能力 URL）。 */
  pendingTeams(limit = 50, offset = 0) {
    return this.request<PendingTeamRow[]>('GET', `/admin/teams/pending?limit=${limit}&offset=${offset}`);
  }
  /** TEAM-031 核过或驳回。驳回必须写理由——它会被送到 owner 面前。 */
  verifyTeam(teamId: number, approve: boolean, reason = '') {
    return this.request<{ team_id: number; verify_status: string; verify_reason: string }>(
      'POST', `/admin/teams/${teamId}/verify`, { approve, reason },
    );
  }
  /** CERT-030 待核验的受限类目资质申请。 */
  pendingCertifications(limit = 50, offset = 0) {
    return this.request<PendingCertificationRow[]>(
      'GET', `/admin/certifications/pending?limit=${limit}&offset=${offset}`,
    );
  }
  /** CERT-031 按状态列资质。撤销的对象是**已核准**的那些——
   *  一张已经核过的假证件撤不下来，持证人会继续接受限类目的单。 */
  adminCertifications(status: 'pending' | 'approved' | 'rejected' | 'revoked' = 'approved', limit = 50) {
    return this.request<PendingCertificationRow[]>(
      'GET', `/admin/certifications?status=${status}&limit=${limit}`,
    );
  }
  decideCertification(applicationId: number, approve: boolean, reason = '') {
    return this.request<{ id: number; status: string }>(
      'POST', `/admin/certifications/${applicationId}/decide`, { approve, reason },
    );
  }
  revokeCertification(applicationId: number, reason: string) {
    return this.request<{ id: number; status: string }>(
      'POST', `/admin/certifications/${applicationId}/revoke`, { approve: false, reason },
    );
  }
  /** UMOD-030 机审拿不准的图片队列。 */
  pendingUploads(limit = 50, offset = 0) {
    return this.request<PendingUploadRow[]>(
      'GET', `/admin/uploads/pending?limit=${limit}&offset=${offset}`,
    );
  }
  /** UMOD-030 处置：通过，或删除并**告知上传者**（悄悄删掉是最差的处理）。 */
  resolveUpload(name: string, action: 'pass' | 'reject', reason = '') {
    return this.request<{ name: string; moderation_status: string; file_removed?: boolean }>(
      'POST', `/admin/uploads/${encodeURIComponent(name)}/resolve`, { action, reason },
    );
  }
  /** CS-030 工单队列。用户的求助在这里，不回就是 SLA 是摆设。 */
  adminTickets(status = 'open', limit = 50, offset = 0,
    opts: { escalated_only?: boolean; mine?: boolean; sort?: 'id' | 'urgent' } = {}) {
    // ESCA-051（150 号 spec）：只看已升级的、只看我接手的、按最急排
    const extra = qs(opts);
    return this.request<AdminTicketRow[]>(
      'GET', `/admin/tickets?status=${status}&limit=${limit}&offset=${offset}${extra ? `&${extra.slice(1)}` : ''}`,
    );
  }
  /** ESCA-053 先回一句、不结单（157 号 spec）；第一次回复记为首次响应 */
  replyTicket(ticketId: number, reply: string) {
    return this.request<TicketReplied>('POST', `/admin/tickets/${ticketId}/reply`, { reply });
  }
  /** ESCA-054 主管把工单指派给某位客服（只有超级管理员），进审计 */
  assignTicket(ticketId: number, assigneeId: number) {
    return this.request<TicketClaimed>('POST', `/admin/tickets/${ticketId}/assign`, { assignee_id: assigneeId });
  }
  /** ESCA-051 「我来处理」：接手后超时提醒只叫醒接手人；可以从别人手里接过来，进审计 */
  claimTicket(ticketId: number) {
    return this.request<TicketClaimed>('POST', `/admin/tickets/${ticketId}/claim`);
  }
  resolveTicket(ticketId: number, reply: string) {
    return this.request<{ id: number; status: string }>(
      'POST', `/admin/tickets/${ticketId}/resolve`, { reply },
    );
  }
  /** SECEV-030 被封的 IP（误封公司出口 IP 时的补救入口）。 */
  adminSecurity() {
    return this.request<SecurityBoardView>('GET', '/admin/security');
  }
  unbanIp(ip: string) {
    return this.request<{ ip: string; banned: boolean }>('POST', '/admin/security/unban', { ip });
  }
  /** GEO-030 线下任务只能发在已开通城市——没有这两条，城市开通只能改库。 */
  createCity(name: string) {
    // 服务端把 `active` 一起返回了——声明里漏掉它就是 V89 那一类漂移
    return this.request<{ id: number; name: string; active: boolean }>(
      'POST', '/admin/cities', { name },
    );
  }
  updateCity(cityId: number, active: boolean) {
    return this.request<{ id: number; name: string; active: boolean }>(
      'PATCH', `/admin/cities/${cityId}?active=${active}`,
    );
  }
  createCategory(name: string, requiredCert = '') {
    return this.request<{ id: number; name: string }>('POST', '/admin/categories', {
      name, required_cert: requiredCert,
    });
  }
  updateCategory(categoryId: number, params: { active?: boolean; required_cert?: string } = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return this.request<{ id: number; name: string; active: boolean; required_cert: string }>(
      'PATCH', `/admin/categories/${categoryId}${qs ? `?${qs}` : ''}`,
    );
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
  distributeVenture(ventureId: number, amountCents: number, memo = '', proposalId?: number) {
    return this.request<{ id: number; total_cents: number; share_snapshot: ShareRow[] }>(
      'POST', `/ventures/${ventureId}/distributions`, { amount_cents: amountCents, memo, proposal_id: proposalId },
    );
  }
  payoutProposals(ventureId: number) {
    return this.request<PayoutProposalView[]>('GET', `/ventures/${ventureId}/payout-proposals`);
  }
  proposePayout(ventureId: number, amountCents: number, memo: string) {
    return this.request<PayoutProposalView>('POST', `/ventures/${ventureId}/payout-proposals`, {amount_cents:amountCents,memo});
  }
  votePayout(ventureId: number, proposalId: number, approve: boolean) {
    return this.request<PayoutProposalView>('POST', `/ventures/${ventureId}/payout-proposals/${proposalId}/vote`, {approve});
  }
  /** TEAM-066 团队邀请链接（147 号 spec）：所有者生成、列出、作废；被邀请人预览、加入 */
  createTeamInviteLink(teamId: number, input: { spend_limit_cents?: number; max_uses?: number; days?: number } = {}) {
    return this.request<TeamInviteCreated>('POST', `/teams/${teamId}/invite-links`, input);
  }
  teamInviteLinks(teamId: number) {
    return this.request<TeamInviteLink[]>('GET', `/teams/${teamId}/invite-links`);
  }
  revokeTeamInviteLink(teamId: number, linkId: number) {
    return this.request<TeamInviteLink>('POST', `/teams/${teamId}/invite-links/${linkId}/revoke`);
  }
  teamInvitePreview(token: string) {
    return this.request<TeamInvitePreview>('GET', `/team-invites/${encodeURIComponent(token)}`);
  }
  acceptTeamInvite(token: string) {
    return this.request<{ team_id: number; user_id: number; role: string; spend_limit_cents: number }>(
      'POST', `/team-invites/${encodeURIComponent(token)}/accept`);
  }
  /** COOP-060 我收到的、还没过期的合作体邀请（142 号 spec） */
  myVentureInvitations() {
    return this.request<VentureInvitationView[]>('GET', '/ventures/invitations');
  }
  declineVentureInvitation(ventureId: number) {
    return this.request<{ venture_id: number; status: string }>('POST', `/ventures/${ventureId}/invitations/decline`);
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
  /** TEAM-061 驳回时 `reason` 是**服务端强制**的（`reason_required`）。
   *  响应里带回 `decision_reason`，界面当场就能显示——不必再拉一次列表。
   *  改造前平台认真地把这段话收上来存好，**然后不送给任何人**。 */
  decideTeamSpend(teamId: number, requestId: number, approve: boolean, reason = '') {
    return this.request<{ id: number; status: string; decision_reason: string }>(
      'POST', `/teams/${teamId}/spends/${requestId}/decide`, { approve, reason },
    );
  }
  executeTeamSpend(teamId: number, requestId: number) {
    return this.request<{ id: number; status: string; amount_cents: number }>(
      'POST', `/teams/${teamId}/spends/${requestId}/execute`,
    );
  }
  /** TEAM-052 设团队月度预算池（0 = 不设池）。**只有 owner 能改**：
   *  让 admin 自己改池子，等于让他绕过自己受的约束。 */
  setTeamBudget(teamId: number, monthlyBudgetCents: number) {
    return this.request<{ id: number; monthly_budget_cents: number; month_spent_cents: number }>(
      'POST', `/teams/${teamId}/budget`, { monthly_budget_cents: monthlyBudgetCents },
    );
  }
  /** TEAM-030 企业信息转人工核验（沿用 V76 那套：材料是敏感文件）。 */
  submitTeamCompany(teamId: number, companyName: string, taxNumber: string, licenseImages: string[] = []) {
    return this.request<TeamView>(
      'POST', `/teams/${teamId}/company`,
      { company_name: companyName, tax_number: taxNumber, license_images: licenseImages },
    );
  }

  organizationRecords(ventureId: number) {
    return this.request<OrganizationRecordView[]>('GET', `/ventures/${ventureId}/organization-records`);
  }
  addOrganizationRecord(ventureId: number, body: OrganizationRecordInput) {
    return this.request<OrganizationRecordView>('POST', `/ventures/${ventureId}/organization-records`, body);
  }

  // ---- OAPI 开放 API 与 Webhook ----
  async apiScopes() {
    const result = await this.request<{ scopes: Array<{ key: string; label: string }>; events: string[]; notice: string }>(
      'GET', '/developer/scopes',
    );
    return {
      scopes: result.scopes.map(s => ({ name: s.key, description: s.label })),
      events: result.events, note: result.notice,
    };
  }
  grantMachineMandate(keyId: number, body: MachineMandateInput) {
    return this.request<MachineMandateView>('POST', `/developer/api-keys/${keyId}/mandate`, body);
  }
  machineMandate(keyId: number) {
    return this.request<MachineMandateView | null>('GET', `/developer/api-keys/${keyId}/mandate`);
  }
  machineActions(keyId: number) {
    return this.request<MachineActionView[]>('GET', `/developer/api-keys/${keyId}/actions`);
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
  /** API-050 给自己的 Key 设更低的每分钟上限；0 = 恢复平台默认（145 号 spec） */
  setApiKeyRate(keyId: number, ratePerMinute: number) {
    return this.request<ApiKeyRate>('PUT', `/developer/api-keys/${keyId}/rate-limit`, { rate_per_minute: ratePerMinute });
  }
  /** API-052 给自己的 Key 设更低的每日配额（北京时间按天）；0 = 平台默认（152 号 spec） */
  setApiKeyQuota(keyId: number, dailyQuota: number) {
    return this.request<ApiKeyQuota>('PUT', `/developer/api-keys/${keyId}/quota`, { daily_quota: dailyQuota });
  }
  /** API-052 这把 Key 每天用了多少、被挡回去多少、今天还剩多少、几点恢复 */
  apiKeyUsage(keyId: number, days = 14) {
    return this.request<ApiKeyUsageView>('GET', `/developer/api-keys/${keyId}/usage?days=${days}`);
  }
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
  /** GEO-022 行程分享开关。服务端返回的键是 `trip_share_enabled`——
   *  此前 SDK 声明成 `enabled`，**两边都以为自己是对的**。 */
  setTripShare(taskId: number, enabled: boolean) {
    return this.request<{ trip_share_enabled: boolean }>(
      'POST', `/tasks/${taskId}/trip-share?enabled=${enabled}`,
    );
  }
  trip(taskId: number) {
    /* GEO 行程：服务端返回的是**最近一个位置点**，不是轨迹。此前声明成
     * `{ shared, points[] }`——任何读 `trip.points` 的客户端都会拿到 undefined。
     * 没有记录时三个字段都是 null。 */
    return this.request<{ lat: number | null; lng: number | null; at: string | null }>(
      'GET', `/tasks/${taskId}/trip`,
    );
  }
  /** GEO-023 一键求助。**服务端返回的是 `{ ok, guidance }`，不是 `{ id, notified }`**——
   *  声明错了这么久没人发现，因为**两端都没有任何一处调用过它**：
   *  服务端连「求助不该被合规弹窗挡住」（PIPL 十三条四项）都想清楚了，
   *  而那个按钮一直不存在。
   *
   *  `guidance` 要**原样显示**：它是这一刻唯一对用户有用的那句话。 */
  sos(taskId: number, lat: number, lng: number) {
    return this.request<SosResult>('POST', `/tasks/${taskId}/sos`, { lat, lng });
  }
  circleMembers(circleId: number) {
    return this.request<Array<{ user_id: number; nickname: string; credit_score: number }>>(
      'GET', `/circles/${circleId}/members`,
    );
  }
  removeCircleMember(circleId: number, userId: number) {
    return this.request<{ ok: boolean }>('POST', `/circles/${circleId}/members/${userId}/remove`);
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
    return this.request<MyTicket[]>('GET', '/support/tickets');
  }
  /** ESCA-001 工单转纠纷**带上下文**：不带的话用户要把刚说过的话重说一遍，
   *  而两次陈述不一致会在纠纷里被当成翻供。 */
  escalateTicket(ticketId: number, taskId: number, reason: string) {
    return this.request<{ dispute_id: number; ticket_id: number }>(
      'POST', `/support/tickets/${ticketId}/escalate-to-dispute`, { task_id: taskId, reason },
    );
  }
  /** NTF-003/065 可开关的通知类别，**以及哪些关不掉、为什么**。
   *
   *  V82 把响应写成数组是臆造的，**没有任何东西会红**，因为形状闸门
   *  当时只覆盖那六条新线（这正是 CLI-070 要扩覆盖面的理由）。
   *
   *  `always_on` 来自服务端的 `MUST_REACH` 表：界面**不许自己抄一份**——
   *  那张表会变（V65 立、V100 加过一行），抄下来第二天就过期。 */
  notificationPrefs() {
    return this.request<NotificationPrefsView>('GET', '/notifications/prefs');
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
  /** KB-023 脱敏经验卡。
   *
   *  这个声明此前是错的：写着 `body: string`（服务端**从来没给过**这个字段），
   *  而服务端真给的 `city` / `price_actual_cents` / `duration_days` / `outcome` /
   *  `has_decomposition` 一个都没声明——也就是说想按价格或成败筛卡的人，
   *  在类型里**看不见这些字段存在**。V85 建的响应形状闸门只比具名接口的手写案例，
   *  内联类型结构上进不了它的范围（281 个调用点只覆盖 26 个，记台账 CLI-083）。 */
  /** KB-073 子类检索：这一类活儿通常怎么做、通常多少钱（每个结论带样本量）。 */
  knowledgeClusters(category?: string, q = '') {
    const qs = new URLSearchParams();
    if (category) qs.set('category', category);
    if (q) qs.set('q', q);
    const tail = qs.toString();
    return this.request<KnowledgeClusterList>('GET', `/knowledge/clusters${tail ? `?${tail}` : ''}`);
  }
  /** KB-074 子类详情：分布、结果构成、共识与分歧。 */
  knowledgeCluster(clusterId: number) {
    return this.request<KnowledgeClusterDetail>('GET', `/knowledge/clusters/${clusterId}`);
  }
  // ---- KB-070~076 运营面 ----
  knowledgeAdminOverview() {
    return this.request<KnowledgeAdminOverview>('GET', '/admin/knowledge/overview');
  }
  knowledgeUndecided() {
    return this.request<KnowledgeUndecidedRow[]>('GET', '/admin/knowledge/undecided');
  }
  /** 待定区样本：并进某个子类，或以它为第一个样本新建子类（二选一）。 */
  assignKnowledgeCard(cardId: number, clusterId: number | null, newLabel = '') {
    return this.request<KnowledgeCluster>('POST', `/admin/knowledge/cards/${cardId}/assign`,
      { cluster_id: clusterId, new_label: newLabel });
  }
  knowledgeCalibrationPairs(category: string, n = 12) {
    return this.request<KnowledgeCalibrationPair[]>('GET',
      `/admin/knowledge/thresholds/${encodeURIComponent(category)}/pairs?n=${n}`);
  }
  calibrateKnowledge(category: string, pairs: Array<{ a: number; b: number; same: boolean }>) {
    return this.request<KnowledgeThresholdView>('POST',
      `/admin/knowledge/thresholds/${encodeURIComponent(category)}/calibrate`, { pairs });
  }
  retractKnowledgeTask(taskId: number, reason: string) {
    return this.request<{ retracted: number; clusters_recomputed: number[] }>('POST',
      `/admin/knowledge/tasks/${taskId}/retract`, { reason });
  }
  mergeKnowledgeCluster(clusterId: number, targetId: number) {
    return this.request<KnowledgeCluster>('POST', `/admin/knowledge/clusters/${clusterId}/merge`,
      { target_id: targetId });
  }
  renameKnowledgeCluster(clusterId: number, label: string) {
    return this.request<KnowledgeCluster>('PATCH', `/admin/knowledge/clusters/${clusterId}`, { label });
  }
  // ---- KB-080~089 / AGT-080~083 可复用单元与经验工具（109 号 spec）----
  /** KB-086 可复用单元检索：只列在用且有复用授权的。 */
  knowledgeUnits(filter: { category?: string; kind?: ReusableUnitKind; cluster_id?: number; q?: string } = {}) {
    const qs = new URLSearchParams();
    if (filter.category) qs.set('category', filter.category);
    if (filter.kind) qs.set('kind', filter.kind);
    if (filter.cluster_id) qs.set('cluster_id', String(filter.cluster_id));
    if (filter.q) qs.set('q', filter.q);
    const tail = qs.toString();
    return this.request<ReusableUnit[]>('GET', `/knowledge/units${tail ? `?${tail}` : ''}`);
  }
  /** 单元详情：内容、权限清单、贡献者（只列同意了复用的人）。 */
  knowledgeUnit(unitId: number) {
    return this.request<ReusableUnitDetail>('GET', `/knowledge/units/${unitId}`);
  }
  /** 运营：从子类蒸馏一个单元。排除条件与两个授权位必须明说。 */
  distillKnowledgeUnit(clusterId: number, input: ReusableUnitDistillInput) {
    return this.request<ReusableUnitDetail>('POST', `/admin/knowledge/clusters/${clusterId}/units`, input);
  }
  /** 运营：按状态列单元（默认待复核）。 */
  adminKnowledgeUnits(status: 'active' | 'needs_review' | 'retired' = 'needs_review') {
    return this.request<ReusableUnit[]>('GET', `/admin/knowledge/units?status=${status}`);
  }
  /** 运营：复核后重新启用（版本 +1、验证从头算）或下线。 */
  setKnowledgeUnitStatus(unitId: number, status: 'active' | 'retired', note: string) {
    return this.request<ReusableUnitDetail>('PATCH', `/admin/knowledge/units/${unitId}`, { status, note });
  }
  /** AGT-080 调用一个经验工具：产出只是草稿，不花钱、不签约、不发消息。 */
  invokeExperienceTool(unitId: number, taskId: number) {
    return this.request<ExperienceToolDraft>('POST', `/agent/tools/${unitId}/invoke`, { task_id: taskId });
  }
  /** AGT-083 丢弃一份工具草稿（只有调用者本人能丢）。 */
  discardToolDraft(invocationId: number) {
    return this.request<{ invocation_id: number; discarded: boolean }>('POST',
      `/agent/tools/invocations/${invocationId}/discard`);
  }
  knowledgeCards(category?: string, limit = 20) {
    const q = category ? `?category=${encodeURIComponent(category)}&limit=${limit}` : `?limit=${limit}`;
    return this.request<Array<{
      id: number; category: string; city: string; title: string;
      price_actual_cents: number; duration_days: number;
      /** completed / disputed / cancelled —— **失败案例同样入库**（KB-004），
       *  所以读到的不一定是成功案例，界面必须把它显示出来。 */
      outcome: string;
      has_decomposition: boolean;
    }>>('GET', `/knowledge/cards${q}`);
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
  /** TAX-024 申请**平台服务费**发票。声明过的 `scope` 与 `created_at` 服务端
   *  从来没返回过（它给的是 `scope_note` 与 `at`）——「声明了却不给」的
   *  又一处，而这两个方法此前两端都没人调，所以一直没人撞上。 */
  requestInvoice(contractId: number, title: string, taxNo = '') {
    return this.request<{
      id: number; kind: string; amount_cents: number; status: string; scope_note: string;
    }>('POST', '/finance/invoices', { contract_id: contractId, title, tax_no: taxNo });
  }
  myInvoices() {
    return this.request<InvoiceRow[]>('GET', '/finance/invoices');
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
