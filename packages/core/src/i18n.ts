// I18N 错误文案表与语言协商（55 号 spec）。
//
// **这一批最关键的一条判断：错误的稳定契约是 `code`，不是 `message`。**
//
// 平台的错误封装早就是 `{detail: {code, message}}`，而 `code` 已经是一个
// 语言无关的稳定标识符。这意味着用户看到的绝大部分动态文案**不需要服务端
// 翻译**——把 code→文案的映射放在客户端，换语言就是换一张表。
//
// 这条把工作量从「翻译 382 条并维护同步」变成「客户端建一张表」，
// 顺带解决了一个既有问题：同一个 code 在不同端的措辞会漂。
//
// 下面的中文文案**不是我编的**，是从服务端实际抛出的那条 message 搬来的
// （同一 code 多处时取最完整的一条），所以它忠实于既有行为。

export type Locale = 'zh-CN' | 'en';

/** I18N-010 支持列表是**白名单**，不认识的一律回落。 */
export const SUPPORTED_LOCALES: Locale[] = ['zh-CN', 'en'];
export const DEFAULT_LOCALE: Locale = 'zh-CN';

/**
 * I18N-010 语言协商的**唯一解析点**。
 *
 * `zh-TW` 回落到 `zh-CN` 是一个**产品决定**（简繁差异不只是字形）：
 * 在没有繁体文案之前，回落到简体比回落到英文好。
 */
export function resolveLocale(
  acceptLanguage?: string | null,
  userPreference?: string | null,
): Locale {
  // 登录后以用户设置优先——他明确选过的，不该被浏览器设置覆盖
  const candidates = [userPreference, ...(acceptLanguage ?? '')
    .split(',').map((p) => p.split(';')[0].trim())];
  for (const raw of candidates) {
    if (!raw) continue;
    const tag = raw.toLowerCase();
    if (tag.startsWith('zh')) return 'zh-CN';
    if (tag.startsWith('en')) return 'en';
  }
  return DEFAULT_LOCALE;
}

/**
 * I18N-001 错误码 → 中文文案。
 *
 * 键集合必须与服务端能抛出的错误码对齐（见
 * server/tests/test_i18n.py，与 SYNC-002 账本科目同一条规矩）。
 */
export const ERROR_MESSAGE_ZH: Record<string, string> = {
  space_revision_conflict: '空间已在其他窗口更新，请重新打开后编辑',
  change_empty: '变更单至少要改一样：金额、截止时间或范围',
  quote_wrong_party: '报价要发给这单的发布方',
  wb_limit_reached: '数量已达上限，请先归档或删除不用的',
  pack_invalid: '场景包定义有问题，请按提示修改',
  pack_draft_exists: '这个场景包已有一个没上线的版本：先改它，或下线它',
  pack_key_changed: '草稿不能改 key：换 key 等于另一个场景包',
  pack_not_draft: '只有草稿能改或提交；已上线的版本不可变，改动请建新版本',
  pack_not_in_review: '只有待审核的版本能上线或退回',
  pack_four_eyes: '上线需要另一位管理员审核：写它的人不能自己批',
  pack_retired: '这个场景包已经下线了',
  pack_install_limit: '知识库或工作台的数量已到上限，先整理一下再启用',
  pack_unknown_category: '包里用到的类目不存在或已停用，先在「城市与类目」里开好',
  opc_profile_mismatch: '没有登记主体的个人不是增值税纳税人：先选个体工商户或公司',
  opc_bad_period: '期间写成 2026-10（月）、2026-Q3（季）或 2026（年）',
  opc_tax_exceeds_amount: '税额不能大于含税金额',
  opc_platform_entry_locked: '平台导入的收入金额与日期以平台流水为准，不能改；可以补备注、发票号',
  opc_limit_reached: '账目已达上限，请先导出归档后删除旧的',
  skill_alias_taken: '这个写法已经属于别的技能概念：先从那个概念里去掉，再加到这里',
  draft_already_decided: '这份草稿已经采用或丢弃过了，不用再处理',
  sandbox_cloud_ai_blocked: '隐私沙箱开着：这类助手的活在本机做，内容不发到云端。要用云端助手，先在「隐私沙箱」里关掉',
  sandbox_model_exists: '这个模型标识已经登记过了，换一个或者改已有的那条',
  sandbox_model_not_draft: '只有草稿能改或上架：已上架的要先下架，再登记一条新的',
  sandbox_model_four_eyes: '上架需要另一位管理员审核：登记它的人不能自己批',
  sandbox_model_incomplete: '上架前要补齐 sha256、https 下载地址、文件大小、许可证与最低内存——手机下载后要靠这些校验',
  sandbox_model_bad_skill: '本机技能只能是：摘要、拆清单、抽待办、改写、起草回复',
  influence_vouch_self: '不能给自己担保',
  influence_vouch_tier: '在这个类目做到熟手以上（至少完成 3 单、影响力 30 点）才能为别人担保',
  influence_stake_exceeds: '担保额超出可用额度：担保合计不超过你在这个类目影响力的一半，先撤回或等已有的担保结束',
  influence_vouch_task_mismatch: '这一单不在这个类目，或者他没有报名 / 承接这一单',
  influence_vouch_exists: '你已经为他在这里担保过了',
  influence_vouch_closed: '这笔担保已经结束了，不用再撤',
  influence_vouch_locked: '他已经开工了：为这一单的担保要等这一单结束才释放',
  gig_need_location: '先打开「现在有空」，或者带上当前位置',
  gig_need_destination: '选一个目的地（常用地点）',
  gig_places_full: '常用地点最多 10 个，先删掉不用的',
  gig_quote_needs_subject: '给一个任务，或者一个类目',
  nb_limit_reached: '知识库数量已达上限，请先导出后删除不用的',
  nb_revision_conflict: '这条笔记已在其他窗口或设备上改过，请刷新后再改',
  note_empty: '记点什么吧：正文、标题或链接至少一项',
  wb_revision_conflict: '这个任务已在其他窗口或设备上改过，请刷新后再改',
  progress_from_children: '这个任务的进度按清单子项自动计算，不能手填',
  progress_from_platform: '关联了平台任务，进度跟着平台任务走，不能手填',
  only_one_level: '清单只有一层：子项下面不能再加子项',
  project_not_empty: '项目里还有任务：可以先归档项目，或把任务移走后再删',
  routine_needs_time: '一次性的例行任务要给出运行时间',
  routine_time_passed: '运行时间已经过去了',
  profile_private: '请先在账户隐私设置中允许公开个人资料',
  headline_required: '公开前请写一句介绍',
  space_content_rejected: '空间内容需要调整后再发布',
  // V130 起钱包的充值/提现也用这个码（资金类强制带键），不再只是机器写操作
  idempotency_required: '该操作必须携带 1—80 字符的 Idempotency-Key（防止重试导致重复扣款）',
  idempotency_key_invalid: 'Idempotency-Key 至多 80 个字符',
  idempotency_in_progress: '同一笔操作正在处理，请稍后再试',
  // AI-DEC-040~048 逐层拆解（V132）
  decomposition_changed: '这份拆解刚被另一个窗口改过，请刷新后再改',
  already_expanded: '这一步已经拆过了',
  not_a_tree: '这是逐层拆解之前的提案，不能逐步编辑',
  tree_has_depth: '这份拆解已经展开到第二层以下，请逐步编辑',
  no_decomposition_in_progress: '这个任务没有进行中的拆解',
  invalid_executor_hint: '谁来做只能选：交给人做 / 需要资质 / 交给 AI',
  field_not_editable: '这些字段不能改',
  empty_patch: '没有要改的内容',
  category_not_found: '平台没有这个类目',
  step_title_required: '步骤名称不能为空',
  // KB-070~076 经验子类（V134）
  assign_choose_one: '并进已有子类、或新建子类，二选一',
  calibration_too_few: '标注太少：至少 6 对，其中「是一回事」与「不是」各至少 2 对',
  calibration_cross_category: '标注对必须都在同一个大类里',
  card_not_undecided: '这条样本不在待定区',
  cluster_cross_category: '大类不同的样本或子类不能并到一起',
  cluster_label_required: '新建子类要有名字',
  cluster_merge_self: '不能合并到自己',
  cluster_model_mismatch: '子类的质心不是用当前模型算的，先重算',
  invitation_consumed: '邀请已处理',
  // SEC-061（V139）管理员受限访问：读他人私聊 / 证件影像必须写理由并进审计
  admin_access_reason_required: '查看他人私聊或敏感材料必须写明理由（会记入审计）',
  // KB-080~089 / AGT-080~083 可复用单元与经验工具（V135）
  unit_kind_invalid: '单元类型只能是：报价提示 / 验收清单 / 分解流程 / 可执行工具',
  unit_exclusions_required: '必须写明排除条件：什么情况下不该用这个单元',
  unit_scope_invalid: '这一批只开放「全平台」范围',
  unit_no_consented_source: '这个子类里没有双方都同意经验复用的样本，不能注册单元',
  unit_too_few_samples: '这个子类样本太少，不能产出报价提示',
  unit_no_consensus: '这个子类还没有共识流程，产不出清单或流程',
  unit_step_title_required: '每一步都要有名称',
  unit_tool_unknown: '平台没有这个工具',
  tool_unavailable: '这个经验工具在复核中或已停用，暂不可用',
  tool_degraded: '当前经验检索不是语义模型，可执行的经验工具暂停使用',
  tool_over_budget: '这次调用的预估成本超过上限，没有执行；请改为人工处理',
  tool_not_applicable: '这个经验工具不适用于这一单',
  invitation_required: '需要当前成员发出的有效邀请',
  mandate_budget: '超过单笔或累计任务授权额度',
  mandate_category: '任务类目不在授权范围',
  mandate_exists: '授权不可原地扩权；请吊销旧密钥并重新授权',
  mandate_required: '机器授权不存在、过期或不包含此操作',

  account_banned: '账号已被封禁，如有异议请申诉',
  account_deleted: '账号已注销',
  active_contract: '存在未结算合约，请先完成或取消后再注销',
  admin_required: '需要管理员权限',
  agent_run_in_progress: '该任务已有执行在进行中',
  already_applied: '已报名过该任务',
  already_decided: '该贡献已处理',
  already_escalated: '该工单已转纠纷',
  already_friends: '已经是好友',
  already_invited: '已邀请过该用户',
  already_member: '已加入或待审核',
  already_published: '已经是发布状态',
  already_recalled: '已撤回',
  already_releasing: '已开始分期放款，不可整体改价',
  already_requested: '该合约已申请过平台服务费发票',
  already_reviewed: '已评价过',
  already_subscribed: '已订阅',
  already_verified: '已完成实名认证',
  amount_mismatch: '回调金额与订单金额不一致，已挂起人工核对',
  api_key_required: '缺少 X-API-Key',
  application_closed: '该报名已处理，不可撤回',
  application_pending: '该资质已有待审申请',
  auto_criterion_required: '浮动对价至少需要一条由平台判定的客观指标，否则达标与否完全由发布方说了算。',
  bad_credentials: '手机号或密码错误',
  bad_old_password: '原密码错误',
  bad_password: '密码错误',
  bad_request: '请求有误',
  blocked: '无法报名该任务',
  bonus_not_allowed: '仅 outcome 计价支持浮动对价',
  bonus_required: '浮动对价必须给出确定的加付上限金额',
  bonus_too_large: '浮动部分不得超过基础报酬，超出请改为提高基础报酬',
  budget_locked: '已有报名者，预算不可下调（防调包），只能上调',
  budget_required: '预算必须大于 0',
  budget_too_small: '预算不足以拆分名额',
  campaign_budget_exhausted: '活动预算已用尽',
  campaign_closed: '活动已结束',
  cannot_ban_admin: '不能封禁管理员',
  captcha_required: '需要完成人机验证后重试',
  category_exists: '类目已存在',
  certificate_expired: '证件已过期，请提交在有效期内的证件',
  certification_exists: '已持有该资质且在有效期内',
  change_closed: '变更单已处理',
  change_pending: '已有待处理的变更单',
  city_required: '地域圈必须绑定城市',
  conflict: '当前状态下无法执行该操作',
  consent_withdrawn: '你已撤回对证件信息处理的同意，接单与资金操作已停用，可在 设置→隐私 重新授权',
  contract_exists: '该任务已存在合约',
  contract_frozen: '合约处于纠纷冻结中',
  coupon_already_applied: '该订单已使用过优惠券（一单一券）',
  coupon_exhausted: '已被领完',
  coupon_expired: '该券已过期',
  coupon_not_found: '券模板不存在',
  coupon_unavailable: '券不存在或已下架',
  coupon_used: '该券已使用或已失效',
  coupon_window_closed: '不在领取时间内',
  creator_unavailable: '该任务发布方账号已失效，无法报名',
  criteria_required_for_outcome: '浮动对价必须绑定本任务的验收指标——没有判据的「做得好多给钱」是一句无法执行的承诺。',
  cyclic_dependency: '子任务依赖存在环',
  deadline_in_past: '截止时间必须晚于当前时间',
  delivery_note_required: '该任务为浮动对价，提交验收时必须填写交付说明（浮动部分按它对照验收指标判定）',
  direct_upload_unsupported: '当前存储实现不支持视频直传（本地存储没有 CDN）——请配置 PLATFORM_STORAGE_PROVIDER 为支持直传的对象存储',
  dispute_closed: '纠纷已结案，不可再提交陈述',
  dispute_exists: '已存在进行中的纠纷',
  domains_required: '必须声明至少一个能力领域',
  empty_items: '子任务列表为空',
  empty_milestones: '里程碑不能为空',
  escrow_mismatch: '托管余额异常',
  events_required: '必须至少订阅一个事件',
  forbidden: '无权执行该操作',
  frozen_mismatch: '冻结余额异常',
  funds_mandatory: '资金类通知为必达通知，不可关闭',
  holder_mismatch: '证件持有人姓名与实名信息不一致，无法受理。职业资质必须由本人持有。',
  holder_name_mismatch: '收款人姓名须与实名认证一致',
  https_required: 'Webhook 地址必须是 https',
  id_already_bound: '该证件号已绑定其它账号',
  idempotency_key_conflict: '幂等键已用于不同的请求，请更换 Idempotency-Key',
  images_required: '需上传证件影像后再提交',
  insufficient_balance: '可用余额不足，请先充值',
  insufficient_deposit: '可用余额不足以缴纳保证金',
  insufficient_platform_balance: '结算金额超出平台可用余额',
  invalid_action: '非法处置动作',
  invalid_amount: '分配金额必须为正',
  invalid_api_key: '无效的 API Key',
  invalid_category: '非法通知分类',
  invalid_coupon_value: '定额与比例二选一',
  invalid_criteria: '验收标准必须是列表',
  invalid_decision: '非法的复核结论',
  invalid_dependency: '依赖索引非法',
  invalid_image_url: '图片地址不合法，请通过上传接口获取',
  invalid_invitee: '被邀请人不存在或未实名',
  invalid_job_token: '无效的任务令牌',
  invalid_kind: '非法内容类型',
  invalid_member: 'AI 助理、合作体与团队账号不能作为团队成员',
  invalid_milestone_state: '该里程碑已交付或已放款',
  invalid_outcome: '非法核验结论',
  invalid_payload: '回调参数不完整',
  invalid_percent: '折扣比例必须小于 100%',
  invalid_phone: '手机号格式不正确',
  invalid_policy: '非法加入策略',
  invalid_recurrence: '非法周期设置',
  invalid_signature: '回调签名校验失败',
  invalid_split_amount: '分账金额不得为负',
  invalid_target: '非法举报对象',
  invalid_type: '非法任务类型',
  invalid_visibility: '非法可见范围',
  invitation_closed: '邀约已处理',
  invitee_unavailable: '对方已暂停接单',
  ip_assignment_required: '请选择交付成果的知识产权归属（转让 / 独占许可 / 普通许可 / 执行方保留）。不选的话，按《著作权法》著作权默认归执行方——这通常不是发布方想要的。',
  kyc_failed: '实名信息核验未通过，请核对姓名与证件号',
  location_required: '线下任务必须提供位置',
  milestones_locked: '合约签署后不可重定义里程碑，请走变更单',
  minor_not_allowed: '未满 18 周岁不能完成实名认证与接单（涉及合同行为能力与用工合规）',
  mission_closed: '编排已结束，不可继续推进',
  multi_milestone: '多里程碑合约请拆期变更（暂不支持整体改价）',
  muted_in_group: '你已被群主禁言',
  name_taken: '圈层名已存在',
  newcomer_only: '仅限新用户领取',
  no_agent_run: '该任务没有 AI 执行记录，无需核验',
  no_checkin_needed: '线上任务无需到场打卡',
  no_discount: '该券在本单无可用优惠',
  no_executor: '任务尚未成交',
  no_fee: '本合约无平台服务费',
  no_payout_account: '请先绑定收款账户',
  no_proposal: '没有待接受的和解提案',
  no_shares: '尚无已确认贡献，无法计算分配比例',
  no_such_account: '账号不存在',
  not_active: '合约不在执行中',
  not_an_agent: '该任务的执行方不是 AI 助理',
  not_approved: '该申请尚未批准或已执行',
  not_cancellable: '待验收阶段不可单方取消，请验收或发起纠纷',
  not_changeable: '当前状态不可变更',
  not_pending: '该团队没有待核验的企业信息',
  not_circle_member: '需加入圈层后查看',
  not_claimable: '该核验单已被接走或已结束',
  not_claimed: '核验单不在处理中',
  not_completed: '任务闭环后才能发经验帖',
  not_consented: '尚未同意该项，无需撤回',
  not_counterparty: '需由合约对方接受变更',
  not_disputable: '仅托管中的任务可发起纠纷',
  not_editable: '任务已进入执行阶段，不可编辑（请走合约变更单）',
  not_found: '资源不存在',
  not_fundable: '合约需双方签署后才能托管',
  not_in_appeal: '纠纷不在申诉复核中',
  not_in_progress: '任务不在执行中',
  not_party: '仅发布方可申请平台服务费发票',
  not_proposed: '提案已处理',
  not_recruiting: '任务不在招募中',
  not_releasable: '合约不在可放款状态',
  not_settled: '合约完成放款后方可开票',
  not_signable: '合约当前不可签署',
  not_splittable: '合约不在可执行裁决状态',
  open_dispute: '存在进行中纠纷，结案后方可注销',
  order_mismatch: '该订单金额存在异常，已挂起人工处理',
  order_not_found: '支付订单不存在',
  owner_cannot_leave: '群主不能移出自己，请先转让或解散',
  owner_immutable: '不能修改 owner 的角色或额度',
  per_user_limit: '已达每人领取上限',
  percent_needs_cap: '比例券必须设置封顶金额',
  phone_taken: '该手机号已被占用',
  reason_required: '驳回必须写明原因，否则申请人不知道该补什么',
  recall_window_expired: '超过 2 分钟不可撤回',
  request_closed: '该提现申请已处理',
  request_pending: '请求已发出，等待对方确认',
  review_window_closed: '评价期已过',
  revision_required: '结论为「已修正」时必须提交修正稿',
  risk_disclosure_required: '需先签署当前版本的风险揭示书',
  same_phone: '新手机号与当前一致',
  scope_required: '必须至少指定一个权限范围',
  self_apply: '不能报名自己发布的任务',
  self_approval: '不能审批自己发起的支出',
  // DSP-030 申诉的意义在于换一个人再看一遍；只有一个管理员时这条会挡住申诉，
  // 那是流程要求（该去加人），不是权限问题——所以文案要把「第二个人」说出来
  same_arbiter: '申诉复核必须由作出原决定之外的第二个人进行，请转交另一位管理员',
  self_block: '不能拉黑自己',
  self_confirmation: '不能确认自己提交的贡献',
  self_follow: '不能关注自己',
  follow_list_private: '对方未公开资料，看不到关注列表',
  self_friend: '不能加自己为好友',
  self_invite: '不能邀请自己',
  sensitive_file: '该文件为敏感材料，请通过 /files/{name}/secure 读取',
  session_revoked: '登录态已失效，请重新登录',
  skill_tag_required: '能力圈必须绑定技能标签',
  skills_locked: '已有报名者，技能要求已锁定',
  sms_code_expired: '验证码已过期，请重新获取',
  sms_code_invalid: '验证码错误',
  sms_code_locked: '验证码尝试次数过多，请重新获取',
  sms_code_missing: '请先获取验证码',
  stranger_limit: '对方回复前最多发送 5 条消息',
  subsidy_pool_exhausted: '平台补贴额度不足，请稍后再试',
  task_closed: '任务已不在招募中，邀约失效',
  tax_exceeds_balance: '代扣税款超过可用余额',
  title_required: '博客必须有标题',
  trip_share_disabled: '行程共享未开启或任务已结束',
  unauthenticated: '用户不存在',
  unsupported_type: '仅支持 MP4 / MOV / WebM',
  use_account_deactivation: '撤回基础协议等同于终止服务关系，请使用账号注销功能（会先校验无未结资金与纠纷）',
  valuation_required: '确认贡献时必须给出计价',
  verification_closed: '核验单已结束',
  verification_in_progress: '该任务已有进行中的核验单',
  verification_required: '请先完成实名认证再领取',
};

/**
 * I18N-001 这些错误码的服务端消息是**拼出来的**（带类目名、金额、期限等），
 * 客户端编不出等价的文案，所以**必须回落显示服务端 message**。
 *
 * 把它们列出来而不是让它们悄悄落进兜底分支，是为了让「哪些还没本地化」
 * 这件事可数、可查——一个说不清自己覆盖了多少的翻译表，等于没有覆盖率。
 */
export const SERVER_WORDED_CODES: string[] = [
  // AI-DEC-044 消息里点名是哪几步、各差什么，客户端编不出等价文案
  'tree_incomplete',
  // AI-DEC-045 总任务本身拆不下去时，消息说的是停在哪条保险上
  'decompose_stopped',
  // Machine grants and invitation lifecycle carry specific remedial instructions.
  'agent_delivery_blocked',
  'agent_not_eligible',
  'agreement_update_required',
  'below_min_order',
  'budget_cap_exceeded',
  'budget_exceeded',
  // TEAM-052 消息里带着本月已用与剩余金额，客户端编不出等价文案
  'monthly_budget_exceeded',
  // PAY-042 消息里带着**取自配置的门槛金额**（运维改了那句话要跟着变），
  // 客户端编不出等价文案
  'same_approver',
  'capacity_full',
  'category_mismatch',
  'certification_required',
  'city_not_open',
  'content_rejected',
  'credit_too_low',
  'criteria_failed',
  'daily_limit_exceeded',
  'finance_offer_forbidden',
  'funds_remaining',
  'group_too_large',
  'insufficient_role',
  'insufficient_scope',
  'insufficient_team_funds',
  'insufficient_venture_funds',
  'invalid_event',
  'invalid_mission_transition',
  'invalid_scope',
  'invalid_settlement_kind',
  'invalid_split_purpose',
  'invalid_transition',
  'invite_blocked',
  'job_running',
  'join_blocked',
  'moderation_rejected',
  'pricing_not_allowed',
  'rate_limited',
  'reject_limit_reached',
  'response_window_open',
  'temporarily_banned',
  'too_far',
  'too_large',
  'too_many_criteria',
  'unsupported_check',
  'unsupported_provider',
  'verifier_not_eligible',
  'weights_sum_invalid',
];

const _SERVER_WORDED = new Set(SERVER_WORDED_CODES);

/**
 * I18N-002 取一条给用户看的错误文案。
 *
 * 兜底顺序是有意的：本地文案 → **服务端 message** → 通用兜底。
 * 不认识的 code 显示服务端消息（中文，但至少是一句人话），
 * 而不是显示 code 本身或空白——把 `insufficient_balance` 摆给用户看，
 * 和什么都不说差不多。
 */
export function errorMessage(
  code: string | undefined,
  serverMessage?: string | null,
  locale: Locale = DEFAULT_LOCALE,
): string {
  if (code && _SERVER_WORDED.has(code) && serverMessage) return serverMessage;
  if (locale === 'zh-CN' && code && ERROR_MESSAGE_ZH[code]) return ERROR_MESSAGE_ZH[code];
  if (serverMessage) return serverMessage;
  if (code && ERROR_MESSAGE_ZH[code]) return ERROR_MESSAGE_ZH[code];
  return ERROR_MESSAGE_ZH.bad_request;
}

/**
 * I18N-030 金额格式化按 locale。
 *
 * 平台内部一律整数分，**只在展示层格式化**——浮点进业务逻辑是钱出错的
 * 经典途径，这条不因为 i18n 而松动。
 */
export function formatMoney(cents: number, locale: Locale = DEFAULT_LOCALE): string {
  const value = cents / 100;
  if (locale === 'en') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: 'CNY', currencyDisplay: 'code',
    }).format(value);
  }
  return `¥${value.toFixed(2)}`;
}

/**
 * I18N-002 把一个抛出来的异常变成一句给用户看的话。
 *
 * 这个函数存在的理由不只是 i18n：改造前全站有 11 处各自写
 * `err instanceof ApiError ? err.message : '网络错误'`——
 * 同一件事写十一遍，迟早有一处写得不一样，而且**不会有任何东西报错**。
 *
 * 非 ApiError（网络中断、超时、JSON 解析失败）统一归到「网络错误」：
 * 把 `TypeError: Failed to fetch` 摆给用户看没有任何意义。
 */
export function apiErrorText(err: unknown, locale: Locale = DEFAULT_LOCALE): string {
  const e = err as { code?: string; message?: string; status?: number } | null;
  if (e && typeof e.code === 'string' && typeof e.status === 'number') {
    return errorMessage(e.code, e.message, locale);
  }
  return locale === 'en' ? 'Network error' : '网络错误';
}
