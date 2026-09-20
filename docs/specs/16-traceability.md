# 16 · Spec → 实现 → 测试 追溯矩阵

> 状态：MVP + V1~V82 全批次完成（2026-09-20）。
> 后端 875 tests + 前端 76 tests（core 48 + web 28）全绿；`scripts/smoke.py`（mock 态）与
> `scripts/sandbox_check.py`（存管合规态，28 项）两条闭环自检均通过。
> 真实 LLM 分解已接入（有 Key 即用，缺省降级）。
> 剩余项均依赖外部供应商/云服务，见文末。

> **矩阵缺口（如实记）**：V66~V71 只更新了计数与 `docs/DELIVERY.md` 的批次表，
> 没有在这里补分批小节。补六段追溯本身价值不大（DELIVERY 里逐批写了），
> 但缺口要记着，别装作矩阵是完整的。

## 已实现（V82 批次：端上接得到）

> 模块 spec：[57-client-reachability.md](57-client-reachability.md)
>
> 清点结果：**78 个用户可达的服务端端点，共享 SDK 里一个都没有。**
> V73~V79 六个批次的用户侧入口，端上全是空的——服务端完整、测试全绿、
> 文档齐备，而用户点不到。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **CLI-060 覆盖闸门** | 从 `app.openapi()` 取**服务端自己声明的**路由表（不是手抄清单），对比 `client.ts` 里扫出的 URL 字面量；剩下的每条要么有 SDK 方法，要么在 `CLIENT_EXEMPT` 里有理由。与 V60 注销处置表同一种做法：**新增一项就逼作者做一次决定** | `tests/test_client_contract_coverage.py::test_cli060_every_user_facing_endpoint_is_reachable_from_the_client`（红验：临时加一个服务端端点，闸门立刻点名它） |
| **扫描器自己先会红** | 断言「至少扫到 150 条」且已知路径必须在内。SDK 里有 `` `/tasks/mine${qs ? `?${qs}` : ''}` ``——**模板字面量里嵌了第二层模板字面量**，正则会断在第一个反引号上，所以路径提取是手写字符扫描 | `::test_cli061_scanner_actually_finds_paths` |
| **CLI-061 豁免双向对齐** | 豁免值是一句人话理由（`True` 不算）；且豁免表里不能留已不存在的路径——否则它会变成一张没人敢删的历史清单，闸门覆盖面悄悄缩小（SYNC-002 同款） | `::test_cli061_exemptions_carry_a_real_reason`、`::test_cli061_exemption_table_has_no_dead_entries` |
| **CLI-062 补齐 SDK** | agent / 核验 / 合作体 / 团队 / 开放 API / 资质 六条线共约 60 个方法 | `::test_cli062_the_six_feature_lines_are_reachable`、`packages/core/src/client.test.ts` 的「六条线的客户端入口」 |
| **CERT-060 修正漂移的契约** | `addCertification(name, licenseNo)` **调用会 422**：V76 把资质改成了「提交申请 + 证件影像 + 姓名比对」，SDK 停在旧形状上。改为 `submitCertification({...})` | `client.test.ts::黑名单/撤回/资质/存证接口路径`（此前它**断言的就是那个错的契约**） |
| **CLI-063 Web 两个入口** | 任务详情页的「AI 助理」面板（邀请 / 执行 / 交付闸门 / 申请人工核验）与核验台 `/verify`（可接列表 / 接单 / 看产出与判据 / 提交结论） | `web/src/AgentAndVerify.test.tsx` |
| **CLI-064 显示服务端给的原因** | `eligible-agents` 与 `verification-orders` 都专门返回了 `reason`，界面必须原样显示——**空列表看起来更干净**，但发布方不知道是要到场还是超预算，核验人不知道是资格不够还是真没单 | `::CLI-064 不可用的助理显示服务端给的理由`、`::CLI-064 不能接的核验单显示资格原因`（两条都做过红验：把 reason 吞掉即红） |

**这一批真正的教训**：

SDK 的测试打的是 mock fetch，它只验证「我发出的请求长这样」，
**从不验证「服务端认不认这个形状」**。所以 `addCertification` 断言着一个
服务端早就不接受的请求体，测试照样绿了一整个版本周期。

> **断言一个错的契约比不断言更糟——它会让人以为已经验过了。**

闸门只解决了「路径可达」，没解决「请求体形状对不对」（CLI-067 记账）。

## 已实现（V81 批次：agent 交付闭环与产出审核）

> 模块 spec：[56-agent-delivery-closure.md](56-agent-delivery-closure.md)
>
> 起点是一次探针（完整 HTTP 链路，非服务层）：
>
> ```
> RUN STATUS: succeeded | OUTPUT: 交付内容：已完成。
> DELIVER as requester: 403 {'code': 'forbidden', 'message': '仅执行者可提交验收'}
> TASK STATUS after run: in_progress
> ```
>
> **由 agent 执行的任务，在生产里永远交付不了。** 钱躺在托管里，任务停在
> `in_progress`，两边都没有任何按钮能往前走。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **AGT-060 平台代交付** | `agent.service.submit_agent_delivery()`：执行成功即由平台提交交付。**不是**放宽 `deliver` 的身份校验——那条校验同时管着所有人类任务，为一个 AI 的特例放宽一条通用身份闸门代价不对等；而平台本来就是 AI 履约的责任主体（AGT-017 已写进合同条款），由责任主体发起交付身份自洽 | `tests/test_agent_delivery_closure.py::test_agt060_agent_task_can_actually_be_delivered_over_http`（整条链路一次 `SessionLocal` 都不用——这正是改造前做不到的事）、`::test_agt060_requester_still_cannot_press_deliver_himself` |
| **AGT-061 新路必须比原路更窄** | 代交付**调** `delivery_block` 而不重写它。加一条「平台可以代交付」的路径，如果它绕过闸门，48/49 两批建的闸门就全部作废 | `::test_agt061_failed_criteria_still_blocks_the_platform_delivery`、`::test_agt061_low_confidence_still_blocks_the_platform_delivery`、`::test_agt061_gate_is_not_bypassed_when_block_is_non_empty`（指着那一行红） |
| **AGT-062 幂等** | 已 `pending_acceptance` / `completed` 的任务再调不产生第二条交付记录、不重置 `delivered_at` | `::test_agt062_repeated_runs_produce_one_delivery` |
| **AGT-063 核验通过即交付** | 此前闸门解除了却**没有任何东西去推那一下**：核验人交了结论、核验费也付了，任务还停在 `in_progress`。`revised` 时交付物是**修正稿**——修正稿之所以存在正因为原始产出不合格 | `::test_agt063_approved_verification_delivers`、`::test_agt063_revised_delivers_the_revision_not_the_original`、`::test_agt063_rejected_verification_does_not_deliver` |
| **AGT-064 交付物进证据链** | `ProgressLog(kind="delivery")`，`user_id` 写 **agent 的 user 行**：证据链里必须能看出这份交付物是谁交的，写成发布方就是在证据里撒谎。`agent_runs` 与 `progress_logs` 是两本账 | `::test_agt064_delivery_log_is_attributed_to_the_agent`、`::test_agt064_delivery_text_reaches_the_dispute_evidence_export` |
| **AGT-067 判据没过的 run 只有「已修正」能解锁** | 同一形状的第二个死胡同：`failed` 分支排在核验分支前面，发布方自费核验 + 核验人交了**重新过判据**的修正稿，任务照样交付不了。但也不能简单把核验分支提前——那会让 `approved` 覆盖掉客观判据，而 AGT-030 的整个立论就是「不让执行方自己判卷」，换成核验人判也一样 | `::test_agt067_approved_cannot_unlock_a_criteria_failure`、`::test_agt067_revision_unlocks_a_criteria_failure` |
| **AGT-051 产出过内容审核** | V73 记下的欠账。它此前不是紧急的，因为未经审核的产出只有当事人看得见；**本批把产出接到了交付上**（进证据链、被验收、被引用），所以接交付的同一批必须接审核，否则是在给一个已知的洞加流量 | `::test_agt051_output_is_actually_sent_to_moderation`（专防「又一次建好了没接上」）、`::test_agt051_rejected_output_fails_the_run_and_is_not_stored` |
| **AGT-065 审核先于判据** | 一份违规的产出，判据过没过不重要。送审文本**不进 vendor 调用日志**（只记字符数）——抄一份到日志里等于给违规内容多开一个落点 | `::test_agt065_moderation_runs_before_criteria`、`::test_agt065_moderation_text_does_not_leak_into_the_vendor_log` |
| **AGT-066 供应商故障升级人审** | 不放行、也不销毁。与 UMOD-010 的 fail-open **方向一致但程度不同**：上传物的用途是自证，挡住它伤的是被侵害方；agent 产出的用途是换钱，放过它伤的是发布方和平台自己。**分界线是代价落在谁身上** | `::test_agt066_moderation_outage_escalates_instead_of_delivering` |

**这一批真正的教训**，值得单独记（56 号 spec 第 0 节）：

`test_agt019` 里有一句注释——「agent 没有登录态（也不该有），所以交付与验收
走服务层」。**两个分句都对，合起来是个洞**：测试绕开 HTTP 只说明了测试能绕开，
生产里没有人能绕开。注释解释了为什么绕，却没有人问一句「那生产里谁来走这一步」。

> **当一个测试为了「走通」而绕过了入口层，绕过去的那段就是没有被测的那段。**

同一形状此前出现过三次（V59 验证码、V61 纠纷陈述、V64 media_urls）都是
「服务端建了闸门，客户端没有路径满足它」；这次是更彻底的版本——
**服务端建了闸门，连服务端自己都没有路径去过它**。

**查这一批时发现的下一个缺口（AGT-072 / VER-052）**：48、49 两号 spec
从头到尾没有一个字提客户端，`packages/core` 里也没有任何 agent / 核验单的方法。
发布方无法在 Web 上邀请 AI 助理，核验人无法看到、接下、提交任何一张核验单。
服务端完整，端上零入口。单独成批。

## 已实现（V80 批次：先把机制做对，不做一次性的机械搬运）

> 模块 spec：[55-i18n.md](55-i18n.md)
>
> 实测规模：服务端 **382 条**中文消息、**140 个**含中文的 Python 文件，
> Web 侧约 **1197 处**中文字面量。
>
> **这一批刻意不做全站抽取**，三条理由（spec 第 0 节）：
>
> 1. **没有第二个语种可以验证。** 抽完之后唯一能证明「没抽坏」的办法是
>    人肉点一遍全站，而一次抽错（把动态拼接的句子抽成静态 key、
>    把复数形态写死）要等真上了第二语种才暴露。
>    **一个无法验证的大改动，不是进展，是把风险推到以后。**
> 2. 机械抽取会把代码变难读：`t('err_4471')` 比「余额不足」更难维护，
>    而收益要等出海那天才兑现。
> 3. **法律文本不能这么搬**——机器翻译的合同条款是法律负债，不是国际化。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **I18N-001 错误的稳定契约是 `code`** | 平台的错误封装早就是 `{detail:{code,message}}`，**code 已经是语言无关的稳定标识符**（237 个）。把 code→文案放客户端，换语言就是换一张表——工作量从「翻译 382 条并维护同步」变成「建一张表」，顺带解决了「同一 code 在不同端措辞会漂」 | `tests/test_i18n.py::test_i18n001_every_server_error_code_has_client_text_or_is_declared_dynamic` |
| **文案不是编的** | 195 条中文取自服务端**实际抛出的那条 message**，忠实于既有行为 | — |
| **43 个动态码显式声明** | 只有拼接消息的码（带类目名/金额/期限），客户端编不出等价文案，**所以不编**——列出来而不是让它们悄悄落进兜底分支，是为了让「哪些还没本地化」可数可查。**一个说不清自己覆盖了多少的翻译表，等于没有覆盖率** | `::test_i18n001_dynamic_codes_are_not_given_made_up_text`（双向：声明了就不许再编文案，且必须确实没有静态消息） |
| **I18N-002 双向对齐** | 与 SYNC-002（账本科目）同一条规矩 | `::test_i18n002_client_catalog_has_no_codes_the_server_cannot_raise` |
| **兜底顺序** | 本地文案 → **服务端 message** → 通用兜底。把 `insufficient_balance` 摆给用户看，和什么都不说差不多 | `packages/core/src/i18n.test.ts`、`::test_error_message_falls_back_to_server_text_not_to_the_code` |
| **I18N-010/011 语言协商单一解析点** | 白名单回落；**用户偏好优先于浏览器**（很多人的浏览器语言并不是他想看的语言）；`zh-TW` 回落简体是一个**产品决定** | `::test_i18n011_user_preference_wins_over_browser`、`::test_i18n010_traditional_chinese_falls_back_to_simplified_not_english`、`::test_i18n010_server_and_client_support_the_same_locales` |
| **I18N-020 法律文本不进翻译表** | 一份合同的效力取决于当事人对**那一份文本**的合意；交给 key-value 表意味着改一行 JSON 就改了合同内容且无人审阅。这是一条**故意不做**的闸门 | `::test_i18n020_legal_text_is_not_in_the_translation_table`、`::test_i18n020_legal_modules_still_hold_their_own_text` |
| **I18N-030 格式化** | 金额按 locale 格式化，但**整数分只在展示层转换**（浮点进业务逻辑是钱出错的经典途径）；服务端只出 ISO-8601 日期 | `::test_i18n030_server_never_emits_localized_date_strings`（防的是以后有人在服务端拼中文日期） |

**写这批时自己犯并修掉的两个错**：

**① 生成文案表时取「同一 code 最长的那条消息」**，结果 `not_found` 变成了
「Webhook 不存在」——那是几十个场景共用的兜底码，给它一条具体消息是误导。
改为兜底码用通用文案，并留了一条测试钉住。

**② 法律文本闸门第一版按关键词比**（「著作权」等），误伤了一条错误消息：
「按《著作权法》著作权默认归执行方」是在**解释为什么要选归属**，是提示不是条款。
改为比对**实际的法律文本常量**。**宽到误伤的闸门会被人关掉，等于没有闸门。**

**顺带消掉一处重复**：全站 11 处各自写
`err instanceof ApiError ? err.message : '网络错误'`——同一件事写十一遍，
迟早有一处写得不一样，而且不会有任何东西报错。收敛成 `apiErrorText()`。

## 已实现（V79 批次：给机器的钥匙，不能是给人的那一把）

> 模块 spec：[54-open-api-webhooks.md](54-open-api-webhooks.md)
>
> 现状实测：全站唯一的身份是**用户会话 token**（绑 `sid`，改密即全端下线）。
> 那是给**人**用的。最省事的做法是「让集成方存一个用户 token」，三条都不成立：
>
> 1. **会话会被吊销**——用户改一次密码，对方的集成第二天就全挂了，
>    而他们完全不知道为什么；
> 2. **权限全有**——会话 token 能提现、能改密、能注销账号。
>    集成方只想读任务列表，凭什么给他一把能把钱转走的钥匙；
> 3. **没法审计**——出问题时分不清是本人操作还是集成方调的。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **API-001 只存哈希、只显示一次** | 与密码同一条道理：能解出来就意味着有人能解出来。找回的便利不值得拿「库被拖走时所有集成方凭证同时泄露」去换。因此必须提供**轮换**——那是「丢了怎么办」的唯一出路 | `tests/test_open_api_webhooks.py::test_api001_plaintext_key_is_shown_once_and_only_hashed_at_rest`、`::test_api001_rotation_invalidates_the_old_key_immediately` |
| **API-002 没有任何动钱的 scope** | 出金是平台上唯一不可逆的动作，而集成密钥泄露概率远高于用户密码（它躺在 CI 变量、日志、截图里），一次错误出金追不回来 | `::test_api002_there_is_no_money_moving_scope_at_all`（同时扫开放端点路径，禁止出现 withdraw/topup/transfer/password 等） |
| **scope 校验在依赖层** | 不在每个端点写 if——写 if 的话新端点默认是「没检查」而不是「拒绝」，**与 V47 限流那个洞同一形状**（当时限流只有 7 个手写调用点，新端点默认裸奔） | `::test_api002_missing_scope_is_rejected_and_says_which_one`（并要求错误里说清缺哪个） |
| **API-003 不能超过所属用户** | Key 是用户授权给机器的子集，不是独立权限来源。**被封禁的用户其 Key 必须同时失效**，否则封禁只封了人、没封住机器 | `::test_api003_banning_the_user_kills_their_api_key`、`::test_api003_key_only_sees_its_owners_data` |
| **API-004 会话专属端点不接受 Key** | 改密、提现、注销 | `::test_api004_api_key_cannot_call_session_only_endpoints` |
| **HOOK-001 时间戳进签名** | 只签 body 的话，攻击者拿一个旧请求原样重放，签名照样对得上。每个 webhook **独立 secret**——一个泄露不该让所有人的签名都可伪造 | `::test_hook001_signature_covers_the_timestamp`、`::test_hook001_old_requests_are_rejected`、`::test_hook001_each_webhook_gets_its_own_secret` |
| **HOOK-002 重试、停用、通知** | 指数退避；连续失败自动停用（一个挂掉的 endpoint 会让重试队列无限堆积，拖慢所有人），但**停用必须通知到人**——悄悄停掉比不停更坏，对方会以为平台根本没有事件 | `::test_hook002_failure_retries_then_disables_and_notifies`、`::test_hook002_retry_uses_backoff_not_immediate` |
| **投递记录** | 没有记录的话，集成方报「我没收到」时平台只能说「我发了」——两边都无法证明，这种争执没有出口 | `::test_hook002_delivery_record_exists_so_disputes_have_an_exit` |
| **HOOK-003 事件体不带敏感字段** | **webhook 的接收端是我们控制不了的**：一个写进对方日志的手机号，就是我们泄露的手机号。黑名单兜底 + 递归剥离嵌套 | `::test_hook003_sensitive_fields_never_leave_the_platform` |
| **HOOK-051 事件不是全量开放** | 全量开放要先逐个审事件体里有没有敏感字段——**开放一个没审过的事件比不开放更危险** | `::test_unknown_event_is_rejected`（错误里说明为什么不是全量） |

**明确没做也没假装做**：按 key 的独立限流（API-050，需要配额模型）、
OAuth 授权码流程（API-051——当前的 key 是**用户给自己的机器用的**，
不是给第三方应用代表用户用的，两者信任模型不同，混在一起做会两边都不对）。

## 已实现（V78 批次：团队要的不是组织架构，是预算与审批）

> 模块 spec：[53-team-accounts.md](53-team-accounts.md)
>
> 「加个企业账号」很容易做成一个空壳——建个组织、拉几个人、然后什么也没变，
> 每个人还是用自己的钱包发任务。那没有解决任何真实问题。
>
> 企业客户真正会卡住的是四件事：**钱是公司的**（员工用自己钱包垫付再报销，
> 在任何一家公司都走不通）、谁能花多少要事先定、超过某个数要有人批且留痕、
> 发票开给公司。所以这一批的核心**不是组织架构，是预算与审批**。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **TEAM-001 团队独立钱包** | 团队 = 一行 User（`is_team`）。**第三次用同一条架构判断**（V73 agent / V75 合作体 / 这里）：钱包、托管、合约、纠纷、发任务全部以 user_id 为键 | `tests/test_team_accounts.py::test_team001_team_has_its_own_wallet_separate_from_members`、`::test_team040_team_account_is_not_in_the_recommendation_pool` |
| **TEAM-010 三档角色，不做通用 RBAC** | 可配置的权限矩阵在这个阶段只会让人配错；三档覆盖绝大多数团队，每一档「能做什么」一句话说得清。**admin 能批支出但不能改额度**——否则审批这道闸门自己就绕过去了 | `::test_team010_only_owner_can_change_roles_and_limits`、`::test_team010_owner_role_is_immutable` |
| **TEAM-011 单笔额度，不是月度池** | 月度池要处理周期、结转、跨月退款归属，复杂度高一个数量级，而它解决的主要问题单笔额度也能解决大半。额度内直接执行，但**仍然留一条记录**——「谁花了公司多少钱」不该因为在额度内就查不到 | `::test_team011_within_limit_spends_execute_immediately`、`::test_team011_within_limit_spends_are_still_recorded` |
| **TEAM-020 审批期间不预扣** | 预扣会让一堆待批的申请把预算占死，而审批本来就可能被驳回 | `::test_team011_over_limit_becomes_an_approval_and_does_not_move_money`、`::test_team020_approved_then_executed_moves_the_money` |
| **TEAM-022 不预扣的代价要明确承担** | 批准到执行之间余额可能已被占用 → **明确报错，不产生半截状态**，并在错误里说清楚为什么会这样 | `::test_team022_execution_fails_clearly_when_funds_ran_out` |
| **TEAM-021 不能自己批自己** | 与 COOP-010（贡献不能自己确认）、VER-021（当事人不能核验）同一条规矩 | `::test_team021_cannot_approve_your_own_request`、`::test_team021_members_cannot_approve_anything` |
| **TEAM-030 未核验不能开票** | 一张开给未核验抬头的发票，是税务风险不是便利。营业执照沿用 V76 的敏感材料通道（匿名读拒绝 + 鉴权端点） | `::test_team030_unverified_team_cannot_invoice`、`::test_team030_license_images_are_marked_sensitive` |
| **TEAM-041 资金守恒** | 团队资金变动全部走既有 `transfer()`，五条不变量仍成立 | `::test_team041_team_money_flows_keep_the_invariants` |

**合作体与团队的区别要说清楚，否则两者会混**：

| | 合作体（COOP） | 团队（TEAM） |
|---|---|---|
| 成员关系 | 平等协作，**贡献即份额** | 有层级，**角色即权限** |
| 钱从哪来 | 合作产生的收入 | 公司充值 |
| 钱怎么分 | 按份额分配收益 | **不分配**，只用于支出 |

一句话：**合作体是分钱的，团队是花钱的。** 两者都需要资金池但规则完全相反，
所以是两个模块而不是一个带开关的模块——有一条测试钉住「团队没有分配这个动作」。

## 已实现（V77 批次：花钱买的 logo，默认不属于你）

> 模块 spec：[52-ip-confidentiality-outcome-pricing.md](52-ip-confidentiality-outcome-pricing.md)
>
> **实测缺陷**：`contract/service.py` 生成的条款有四段——金额、验收、争议、
> 性质声明。**没有知识产权归属，没有保密条款。**
>
> 按《著作权法》第十七条：委托作品，受托人与委托人没有约定或者约定不明的，
> **著作权属于受托人**。翻译成平台上的事实：发布方花 ¥3000 买一套 logo，
> 著作权归执行方，他拿到的只是一份范围不明的使用许可；执行方拿到发布方的
> 客户名单和后台密码，**没有任何保密义务的书面约定**。
>
> 而 `软件开发` 类目的发布模板里写着 checklist「约定源码归属」——
> **平台自己提示用户去约定，然后没有提供任何约定的地方。**

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **IPC-001 归属必须选，无默认值** | 四档（转让 / 独占许可 / 普通许可 / 保留）。**最容易犯的错是「默认归发布方」**：对执行方不公平，对通用组件与含第三方素材的交付物直接就是错的。拒绝时说清楚不选的后果，否则用户只会随便选一个 | `tests/test_ip_and_outcome_pricing.py::test_ipc001_publishing_without_choosing_ip_assignment_is_rejected`、`::test_ipc001_all_four_assignments_are_accepted` |
| **IPC-003 人身权不可转让** | 条款写明署名权等归执行方。**把「著作权全部转让」写进合同是一句无效的话**，而写无效的话比不写更糟——当事人会以为自己拿到了实际上没有的东西 | `::test_ipc003_moral_rights_are_not_claimed_to_be_transferable` |
| **IPC-002 保密双向** | 发布方侧与执行方侧都列举，并写例外情形（已公开 / 独立开发 / 依法披露）。**只约束一方的保密条款在谈判上站不住** | `::test_ipc002_confidentiality_is_mutual` |
| **IPC-004 归属随已签版本走** | 条款在生成时固化。不这样做就有个洞：事后改一下任务字段，等于单方面改了归属 | `::test_ipc004_changing_the_task_does_not_change_a_signed_contract` |
| **OUT-001 挂交付成果不挂收益** | 浮动部分必须绑定本任务的 `acceptance_criteria`，且至少一条是平台判定的客观指标——全是人工确认的话，达标与否完全由发布方说了算 | `::test_out001_outcome_pricing_requires_criteria`、`::test_out001_outcome_pricing_requires_at_least_one_objective_criterion` |
| **OUT-002 必须封顶** | **有确定上限的附加对价是价款，随收益浮动的比例是分配**——封顶是把两者分开的关键 | `::test_out002_bonus_must_be_a_capped_positive_amount` |
| **OUT-003 浮动部分一并托管** | 不托管的话「做得好多给钱」就只是口头承诺：执行方干到了水平，发布方不给，平台没有任何东西可以执行 | `::test_out003_bonus_is_escrowed_upfront` |
| **OUT-004 平台判达标** | 达标付、不达标原路退回，两条路径资金都守恒 | `::test_out004_bonus_is_paid_when_the_platform_criteria_pass`、`::test_out004_bonus_is_refunded_when_criteria_fail`、`::test_out004_money_is_conserved_either_way` |
| **金融红线不动** | `outcome` 是与交付成果挂钩，不是与收益挂钩；「按下载量分红」照样被拒 | `::test_finance_redline_still_blocks_revenue_sharing` |

**这一批自己差点犯的错，和为它建的闸门**：

服务端加了必填项 `ip_assignment`，而 Web 发布表单没跟上——**那意味着
发布功能整个不可用**。这正是 V59（人机验证服务端门没有客户端能满足）、
V61（纠纷端点无入口）、V64（`media_urls` 从没传下去）反复出现的同一个形状。
补了两条闸门：客户端确实传了这个字段、且服务端认的四个档位客户端都有中文名
（双向，与 SYNC-002 同一条规矩）。**已实测：把提交那行删掉即变红。**

**另外两处判断**：
- **金融红线的判定要排在归属之前**。一个「按利润分红」的任务是平台根本不能
  做的业务，这时回一句「请选择知识产权归属」既没用又误导——他会以为选完就能发。
- 浮动退回**复用既有的 `refund` 分账类型**，不新造一个近义的
  （`bonus_refund` 被分账类型白名单当场挡下，那个闸门起了作用）。

**存量数据的判断**：迁移把 `tasks.ip_assignment` 回填为**空串**而不是 `assign`。
回填成 `assign` 等于**替当事人做一个他们从没同意过的决定**；
存量任务的合同已经签了，按签署时的条款走，新任务才强制选。

## 已实现（V76 批次：一道一直是虚的门）

> 模块 spec：[51-certification-verification.md](51-certification-verification.md)
>
> 需求原话：「受限类目资质需要单独处理，必须要对相关证件，用户身份实名审核才行。」
>
> **实测现状**：`POST /users/me/certifications` 的实现是一行
> `user.certifications += [body.name]`，注释写着「模拟审核即通过」。
> 也就是说任何实名用户 POST 一个字符串就拿到「电工」资质，
> 而 `task/service.py` 正是用这个字段拦住电工维修、燃气维修、法律咨询的接单，
> 管理后台里连审核队列都没有。**这道门一直是虚的。**
>
> 这一批的完成定义不是「加了个审核页面」，而是
> **在资质被人工核过之前，那个类目的接单准入一次都不放行**。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **CERT-001 提交的是申请不是资质** | 端点语义改变，核准前 `user.certifications` 一个字不加 | `tests/test_certification.py::test_cert001_submitting_does_not_grant_the_certification`、`::test_cert004_only_after_approval_can_you_take_the_job` |
| **CERT-002/003 材料与姓名** | 必须附证件影像；**证件姓名与实名严格比对**——这条最容易漏，漏了前面全白做：**一张别人的电工证也是一张真证件** | `::test_cert002_application_without_images_is_rejected`、`::test_cert003_holder_name_must_match_the_verified_identity` |
| **CERT-004 人工审核** | 队列 + 通过/驳回 + 审计；**驳回必须带理由**（只说「未通过」，申请人只会一遍遍重交）。队列直接显示「证件姓名 vs 实名是否一致」——让审核员在两个页面间比对，迟早比错 | `::test_cert004_rejection_must_say_why`、`::test_admin_queue_surfaces_the_name_match` |
| **CERT-005 有效期** | 准入读「已核准**且未过期**」，不是名字在不在列表里。过期记录保留（留痕），仅不再满足准入；到期前可查 | `::test_cert005_expired_certification_does_not_admit`、`::test_expiring_soon_finds_certificates_about_to_lapse` |
| **CERT-006 存量数据** | 迁移把存量自助资质转成 `pending` 申请（用户看得到「待补充材料」）并清空快照字段。三选一里保留会让这批白做、直接清空会让用户一头雾水 | `::test_cert006_admission_reads_the_application_table_not_the_snapshot`；**已用真实数据实测迁移**：清空生效、两条申请可见 |
| **CERT-010 证件影像不能匿名读** | `/files/{name}` 是匿名能力 URL，安全性只建立在「名字不可猜」上。对任务配图这个权衡是对的，**对身份证/电工证不是**——URL 一旦出现在日志、浏览器历史或转发截图里就等于把证件交出去了。加 `sensitive` 标记：匿名读一律拒绝，另开鉴权端点只给本人与管理员，且 `no-store` | `::test_cert010_certificate_images_are_not_anonymously_readable`、`::test_cert010_owner_and_admin_can_read_it_through_the_secure_endpoint`、`::test_cert010_sensitive_files_are_not_cached` |
| **CERT-011 注销删影像** | 申请记录保留（审计），**影像物理删除**——留着一张能被管理员看的身份证，等于注销没有完成 | `::test_cert011_deactivation_physically_removes_certificate_images` |

**测试抓到的一个真实 bug**：`decide()` 改完 status 后直接查 `active_certifications()`
算快照，但 session 是 `autoflush=False` 的，查询看不到刚改的值，
快照被算成空——核准了却显示没有资质。补 `db.flush()`。

**没做也没假装做（CERT-050）**：**没有接真实的资质核验机构**。
现在是「管理员看图判断」，挡得住「拿别人的证」和明显伪造，挡不住高仿。
代码里留了位置但没有实现，默认实现如实上报 `manual_only`。

## 已实现（V75 批次：份额不是分的，是长出来的）

> 模块 spec：[50-early-cooperation.md](50-early-cooperation.md)
>
> 需求定位是**颠覆公司组织形式**：可追溯（有智能合约）、能获得支持
> （agent / 法律顾问 / 政策 / 发任务给特定人）、持续帮助迭代。
>
> **与公司股权最本质的区别**：传统公司先分股权再干活——分的那一刻谁干多少
> 还不知道，干到一半有人不干了股权还在他手里，早期合作最常死在这。
> 这里反过来：`份额 = 已确认贡献 ÷ 全体已确认贡献`，**是长出来的**。
> 后果是三条，每条都是有意的：不干活的人会被稀释、中途加入的人能公平进来、
> 份额是**算出来的不是存下来的**（存成字段就会漂，且不会有任何东西报错）。
>
> **合规不当否决项，当成工作流里的一步**（用户明确要求）：
> 合规路径引擎按合作体的客观属性判定需要哪些文书与资质、
> 说明每一项**为什么**需要、给出办理路径，**不阻断任何操作**。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **COOP-010 贡献必须被别人确认** | 提交后是 `proposed`，须**另一名成员**确认才计份额；**计价由确认人给**（贡献人说做了什么，确认人说值多少）——描述与估值分开，防一个人既当运动员又当裁判。自报贡献等于自己发股份，与 agent 自报置信度是同一类无效 | `tests/test_early_cooperation.py::test_coop010_self_reported_contribution_does_not_count`、`::test_coop010_valuation_comes_from_the_confirmer`（提交端点根本不接受金额字段） |
| **COOP-011 份额随贡献动态变化** | 每次现算，不存字段 | `::test_coop011_shares_grow_with_confirmed_contributions`、`::test_coop011_not_contributing_gets_you_diluted` |
| **COOP-012 合计恒为 10000 bps** | 余数归最后一个，不各自取整——各自取整合计会差几个基点，分配时就少分或多分 | `::test_coop012_shares_always_sum_to_exactly_10000`（用除不尽的组合专门试） |
| **COOP-020 只分已实现收益** | 钱只能来自合作体钱包可用余额。**代码里根本不存在「预期收益」这个字段**——这不是法务加的限制，是让模型落在合作内部分配而非涉众性金融的设计本身 | `::test_coop020_can_only_distribute_money_actually_received`、`::test_coop020_distribution_follows_shares_and_conserves_money` |
| **分配快照留痕** | 份额是算出来的，但分配依据必须留痕，否则事后重算会得到不同数字 | `::test_coop020_distribution_snapshot_is_kept` |
| **COOP-021 邀请制** | 没有公开加入/浏览端点。邀请人**不能代签**风险揭示书——代签的知情同意不是知情同意 | `::test_coop021_no_public_join_endpoint` |
| **COOP-022 份额不可转让** | **故意不做，不是以后再说**：一旦可转让，它就是一张可流通的权益凭证，性质全变 | `::test_coop022_shares_cannot_be_transferred`（同时扫源码禁止出现转让实现） |
| **COOP-030/031 风险揭示是前置** | 不签不能加入，发起人也要签（他承担的风险不比别人少）。四条必备内容在代码里是**常量**，不是运营可改的文案——改软了整个模式的性质就变了 | `::test_coop030_risk_disclosure_is_required_to_join`、`::test_coop031_risk_disclosure_says_the_four_things_that_matter`（逐条断言，不是断言「非空」） |
| **COOP-040 合规路径只提示不阻断** | 按成员数/资金/累计分配/类目判定文书清单与登记门槛，每项写明**为什么**——只给清单不说理由，用户不知道哪些能省。显式声明**不是法律意见** | `::test_coop040_compliance_path_informs_and_does_not_block`、`::test_coop040_thresholds_trigger_registration_advice`、`::test_coop040_restricted_category_points_at_certification` |
| **单人合作体的死角被明说** | 只有一个人时没人能确认贡献——合规路径**主动说出来**，而不是让用户自己撞上去 | `::test_coop040_single_member_venture_cannot_confirm_anything` |
| **COOP-050 合作体有钱包、能发任务** | 合作体 = 一行 User（`is_venture`），与 V73「agent 是 User」同一条理由：钱包/托管/合约/纠纷/发任务全部以 user_id 为键 | `::test_coop050_venture_can_publish_a_task_with_its_own_funds`、`::test_venture_account_is_excluded_from_the_recommendation_pool`（是 User 但不是「人」） |
| **COOP-060 可追溯 = 哈希链** | 「可追溯」的真实含义不是「有一张表存着」，而是改一条历史记录必须重写整条后继链才不被发现 | `::test_coop060_contribution_and_distribution_are_anchored` |

**与 `finance/compliance.py` 那条红线的关系**（两者方向相反但不冲突）：
那条管**任务发布**——报酬必须是劳务对价，出现「分红/股权/保本」就拒绝，
防的是面向不特定多数人发行可分享收益的权益。这里管**合作体内部**——
已实名成员之间、按已确认贡献、分已经到账的钱。
两者靠三条结构性设计分开：**邀请制、只分已实现收益、份额不可转让**，
而那三条在代码里是硬的。

**明确留给用户决定的一条（COOP-051）**：成员退出时历史份额怎么算？
按当前模型他的历史贡献仍在分母里、仍参与后续分配——这可能是对的
（他确实贡献过），也可能不是（他不再承担风险）。**这需要一个产品判断，
我不替用户定**；在定下来之前，退出只是「不再贡献」，份额自然被稀释。

## 已实现（V74 批次：升级不是换个人重做，是让人来判 AI 做得对不对）

> 模块 spec：[49-verification-and-escalation.md](49-verification-and-escalation.md)
>
> **补 V73 留下的 AGT-050**：`escalated` 当时只做到「拦住 + 可退款」，
> 没有接到人类专家。需求那句「agent 无法完成或者需要人类专家核验」，
> 核心是**后半句**。
>
> **最重要的一条判断：核验不是重做。** 「AI 做完了但没把握」和「AI 做不了」
> 对应的成本差一个数量级。把核验做成「重新发一个任务招人干」，
> 就是按重做收费——**发布方为 AI 的不确定性付了两次全价**，产品立刻不成立。
> 所以核验是独立实体、按原价 5%~20% 定价。
>
> **不复用 Task 与 V73「复用 User」方向相反，标准却是同一条**：
> 复用能省掉重复实现的就复用（托管/纠纷/信用/账本全以 user_id 为键，
> 不复用得各写第二遍）；复用只带来仪式的就不复用
> （核验是一笔 ¥10~50 的活，且常见情形下付款方是平台自己，
> 让平台对自己做资金托管，除了复杂度什么也没换来）。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **VER-002 谁付费（有立场的判断）** | agent 置信度不足是**平台的问题**，平台付；发布方主动要核验的自己付。后果是阈值调越松平台掏越多——**这正是该有的激励**，调的人承担成本 | `tests/test_verification_escalation.py::test_ver002_escalation_is_paid_by_the_platform`、`::test_ver002_voluntary_verification_is_paid_by_the_requester` |
| **VER-000 按核验定价不按重做** | 原价 15%，上下限封顶 | `::test_ver000_verification_is_priced_as_review_not_redo` |
| **VER-020 agent 不能当核验人** | **让 AI 核验 AI 的产出，是把同一个不确定性叠两遍，不是降低它。** 整条升级链路的价值建立在「最后有一个人负责」上 | `::test_ver020_an_agent_cannot_be_a_verifier` |
| **VER-021 利益冲突不靠自觉** | 本单当事人、付费方一律拒；需该类目完成记录 + 信用达标。不能接的**说明理由**（只给空列表，核验人不知道是资格不够还是没单） | `::test_ver021_parties_to_the_task_cannot_verify_it`、`::test_ver021_needs_a_completion_record_in_that_category`、`::test_open_orders_explain_why_not_claimable` |
| **VER-022 三档结论各有出口** | approved/revised 解闸门，rejected 不解。没有「部分通过」——不可执行的结论等于没有结论 | `::test_ver022_approved_unblocks_delivery`、`::test_ver022_rejected_does_not_unblock` |
| **VER-030 修正稿要重新过判据** | **人工核验是加上去的一道，不是用来豁免原有那道的。** 不重跑就有洞：核验人想早点结单，提交一份同样不过判据的修正稿却被放行 | `::test_ver030_revision_must_still_pass_the_platform_criteria` |
| **VER-040 经验回流** | `KnowledgeCard` 只记类目/价格/工期，**记不下「怎么做才对」**。核验结论恰好是带标注的那份信息，是「持续帮助迭代」的真正载体 | `::test_ver040_verification_writes_a_lesson_without_personal_data`（同时断言经验表不存任何人的 id） |
| **VER-010/041 资金** | 预扣→支付/退款；超时未接单自动退款，**已接单的不自动退**（钱退了人还在干是更糟的状态） | `::test_ver010_verifier_gets_paid_and_invariants_hold`、`::test_ver041_unclaimed_orders_expire_and_refund` |
| **ESCA-001 工单转纠纷带上下文** | 不带的话用户要重说一遍——而**两次陈述不一致会被当成翻供**，在纠纷里对他不利 | `::test_esca001_ticket_escalates_to_dispute_with_context`、`::test_esca001_cannot_escalate_the_same_ticket_twice` |
| **ESCA-002/003 证据包含 AI 履约记录** | 平台是责任主体，agent 的 run 与核验结论必须在材料里，否则「谁做的、做成什么样、谁核过」是空白。诚实标注置信度是**自报**的 | `::test_esca002_evidence_package_includes_ai_execution`、`::test_esca002_absent_ai_trail_says_absent_rather_than_empty` |

**过程中两处自查，都值得记：**

**① 我先自己写了一个证据导出端点，然后发现 `legal` 里已经有一个更完整的**
（带哈希链验证、第三方存证回执、证明力边界声明）。删掉自己那个、去扩展既有的，
才是对的——**同一个动作两条路正是 V58 修过的缺陷**。
留了一条测试钉住「全站只有一个证据导出端点」。

**② 平台给自己预扣核验费，被对账不变量当场抓到。**
付款方是平台时，`acct` 与 `platform` 是同一个账户：先减后加净额为零，
却记了一行 -3000 的流水，于是账实不符。正确做法是**平台自付时不做预扣**——
预扣本来就是防「付款方不付」，而平台既是付款方又是代管方，防不了自己。

**③ 平台账户允许为负**（这是个选择，不是疏忽）：平台的钱来自佣金收入，
冷启动时是 0。因为「平台没钱」而拒绝下核验单，结果是**用户卡在一个
交付不了的任务上**——他没做错任何事却要为平台的现金状况买单。
而负余额本身是有意义的经营信号（核验成本超过佣金收入），
该出现在财务看板上被看见，不该被一句「余额不足」挡掉。

## 已实现（V73 批次：定位是「AI 驱动」，而 LLM 只用在一个点上）

> 模块 spec：[48-agent-execution.md](48-agent-execution.md)
>
> **检视结论**：产品一句话定位是「AI 驱动的任务协作平台」，但实测下来
> LLM 只用在「任务分解」一个点上——`orchestrator/service.py:52` 里
> 编排器唯一的 tool 是 `publish_task`，**它只会把活派给人**。
> 「调用特定领域 agent」这一项，代码里一行都没有。
>
> **架构上先定的一件事**：agent 复用 `User` 体系（一行 User + 一行 profile），
> 不另建平行实体。理由不是省事——托管、纠纷、信用、账本、风控**全部以
> `user_id` 为键**，做成平行实体等于把它们各写第二遍，而第二遍必然抄漏。
> 这正是 V58 修过的形状：同一个动作两条路，最常走的那条抄了近道。
>
> **写的过程中改过一次设计**：本想用 AST 扫 `_log()` 凑账本科目全集，
> 写到一半发现 `transfer()` 是 `_log(db, id, f"{kind}_out", …)`——
> 科目是拼出来的，前半截只能靠猜。**靠猜的闸门不是闸门**，
> 改成服务端显式声明 + 写入点拒收。
>
> **顺带查出两条既有缺陷**（都不是这一批引入的）：

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **AGT-010 只能接远程任务** | 排第一位的闸门。平台上大量保洁/跑腿同样有类目、有预算、在招募中——不拦的话 agent 会报名一个上门保洁单，然后交付一段文字 | `tests/test_agent_execution.py::test_agt010_agent_cannot_take_onsite_tasks` |
| **AGT-011/012 领域与预算上限** | 领域不命中就明确拒绝（好过输出一堆看着像那么回事的东西）；金额超上限交人工——依据是**赔付能力** | `::test_agt011_category_must_be_in_domains`、`::test_agt012_budget_ceiling_is_enforced` |
| **AGT-013 置信度闸门不是死路** | 低于阈值 → `escalated` + 拒绝交付，但发布方仍可取消退款。建一道没有出口的闸门比不建更坏。拿不到置信度按**最低**处理 | `::test_agt013_low_confidence_escalates_and_blocks_delivery`、`::test_agt013_escalation_is_not_a_dead_end`、`::test_agt013_missing_confidence_is_treated_as_lowest` |
| **AGT-030 不让 agent 给自己判卷** | 验收判据由**平台**执行，agent 只拿到任务描述。置信度是自报的，正因为自报才需要一道独立的客观闸门压在上面 | `::test_agt030_platform_judges_not_the_agent`（agent 自报 99% 置信度、判据不过 → 仍然失败） |
| **AGT-031 判据在发布环节校验** | 写错的判据要在开工前发现，不是等 agent 跑完才报错；`manual` 项记 `passed=None` 而不是 False——「还没人判」和「判过没通过」必须分得开 | `::test_agt030_bad_criteria_are_rejected_at_publish_time`、`::test_agt031_manual_criteria_do_not_block_but_are_recorded` |
| **AGT-015 失败不假装成功** | 与任务分解**故意相反**：分解失败降级到模板是对的（模板分解仍有用、发布方会自己看），交付物降级成模板就是拿废品换钱。所以这里不降级 | `::test_agt015_backend_failure_does_not_fake_success`、`::test_local_runner_cannot_look_like_it_works` |
| **AGT-016 成本必须落库** | 平台自有 ⇒ API 钱是平台出的 ⇒ **毛利可算**。未验收的任务不计收入而成本已付——把未完成算成收入就是把亏损记成盈利 | `::test_agt016_every_successful_run_records_its_cost`、`::test_agt016_unfinished_tasks_do_not_count_as_revenue` |
| **AGT-017 责任主体写进合同** | 平台自有 ⇒ 平台是责任主体，写进**当事人合意**而非只写在平台规则里（与 FIN-022 同一理由）。agent 无登录态由平台代签，但照常绑定条款哈希并标明 `platform_auto` | `::test_agt020_agent_goes_through_the_whole_contract_flow` |
| **AGT-018 不污染普通推荐池** | agent 全部满足「实名 + 开启接单 + 非发布者」，不排的话每个保洁单的推荐里都有 AI 助理 | `::test_agt018_agents_do_not_pollute_the_normal_recommendation_pool`（同时断言真人没被误排） |
| **AGT-019 收入归集不破坏不变量** | 不另开放款路径，照常 `escrow_release` 再用既有 `transfer()` 归集 | `::test_agt019_earnings_are_swept_to_the_platform_account` |
| **既有缺陷①：对账不变量是手抄清单** | 平台账户不变量原本是 fee / platform_topup / platform_settle / subsidy_* / adjust_* **五组科目各写一个 term 相加**——加一种新科目就误报。改为**按账户求和**（自维护），失配时附科目构成 | `::test_platform_invariant_is_self_maintaining`、`::test_platform_invariant_still_catches_tampering`（证明没变弱） |
| **既有缺陷②：连接池的过期读快照（CONC-020）** | SQLite 连接池跨请求留下提交前的 WAL 读快照，**已吊销的会话仍能通过鉴权**。改用 NullPool；只影响 SQLite，生产 Postgres 有真正的 MVCC | `::test_conc020_sqlite_must_not_pool_connections` |

**关于缺陷②的定位过程**（值得记，因为我先判断错了一次）：
全链路验收「注销后登录态失效」间歇性变红。我先用一次 stash 对比就断言
「是本批引入的」——**这是错的**，重复跑之后 stash 前的版本同样会红。
真正定位靠的是在鉴权处打点：库里 `is_deleted=1`/`revoked=1`，
而请求读到的是 `False`/`False`。换 NullPool 后打点变成 `True`/`True`，
冷启动三连跑 47/47。**一次对比不足以归因一个间歇性缺陷。**

**这条闸门断言的是配置不是行为**：TestClient 单线程、连接不复用，
这个缺陷在 pytest 里根本复现不出来（改坏之前 703 个测试全绿）。
写一条复现不了的行为测试，等于造一个永远不会红的闸门——那比没有闸门更坏。

## 已实现（V72 批次：手抄一份的约定，和一个从没装上过的 App）

> 模块 spec：[47-shared-contract-drift.md](47-shared-contract-drift.md)
>
> **起点是三次实测，不是一次代码审阅**：
>
> 1. `cd app && npm install` → **E404**。`app/package.json` 写的是
>    `"@platform/core": "*"`，而 `app` 不在根 `workspaces` 里，
>    npm 于是去公共 registry 找一个不存在的包。
>    **`app/README.md` 里那条运行命令，从落笔那天起就没成功过一次。**
> 2. 把它装起来、配上 `tsconfig.json`，第一次 `tsc --noEmit` 立刻查出
>    `Property 'deposit_cents' does not exist on type 'Contract'`。
>    服务端是对的、App 是对的，**只有共享类型是错的**。
> 3. 顺着 2 往下跑一遍闭环，查出这批真正贵的那条：
>    执行方接单时 `freeze_deposit()` 把钱从可用划到冻结，而
>    **合约页不提保证金、App 连「冻结中」都不显示、账单流水里那一行写着
>    `deposit_hold`**。一个中文界面里，用户的 ¥50 不见了，
>    唯一的解释是一行英文标识符。
>
> **两条根因是同一件事**：跨边界的约定被手抄了一份，然后没人对过。
> 服务端能产生 20 种账本科目，网页的 `KIND_LABEL` 只有 8 条；
> 而渲染写的是 `KIND_LABEL[kind] ?? kind`——**少一条不会红、不会崩，
> 只会默默给用户看英文**。又是那个反复出现的形状：写错了不会报错的声明。
>
> **检视时改过一次设计**：第一版打算用 AST 扫 `_log()` 凑出科目全集，
> 写到一半发现凑不全——`transfer()` 是 `_log(db, id, f"{kind}_out", …)`，
> 前半截要靠猜调用方传了什么。**靠猜的闸门不是闸门**，改成服务端显式声明
> `LEDGER_KINDS` 并在 `_log()` 写入点拒收未声明科目。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **SYNC-001 文案全仓唯一一份** | 标签表从 `web/src/pages/Wallet.tsx` 搬进 `packages/core/src/ledger.ts`，Web 与 App 共用。留在 Web 里，App 要显示流水就只能再抄一份，两份变三份 | `tests/test_shared_contract_drift.py::test_sync002_server_kinds_and_sdk_labels_match_exactly` |
| **SYNC-002 科目全集显式声明，写入点拒收** | `wallet.LEDGER_KINDS` 20 条；`_log()` 遇到未声明科目直接 `ValueError`。在写入点炸掉，比写进账本后靠肉眼在账单里发现一行英文便宜得多 | `::test_sync002_log_rejects_undeclared_kind_at_write_time`、`::test_sync002_transfer_rejects_undeclared_prefix`；已实测漏声明一条即 4 项变红 |
| **SYNC-002 双向比对** | 服务端全集 ↔ SDK 键集合，缺一条（用户看英文）与多一条（服务端已删而文案没跟）都判失败 | 已实测：SDK 删一条 → 3 红；SDK 多一条 → 1 红 |
| **SYNC-003 扫描器自己不许静默失败** | AST 扫 `_log()` 字面量科目校验声明表。**我先把 kind 按 `args[1]` 取，扫出零个——而零个会让比对全绿通过**。硬编下界 ≥14 与三个必中科目 | `::test_sync003_every_logged_kind_is_declared`、`::test_sync003_label_parser_fails_loudly_rather_than_returning_empty` |
| **SYNC-004 前后端约定对齐** | 真的下一单、真的取一次 `GET /contracts/{id}`、真的对键集合与 `interface Contract` 的字段。反方向只提示不失败（`milestones?` 这类可选字段本来就可能不出现） | `::test_sync004_contract_response_keys_are_all_declared_in_sdk`；已实测类型里删掉字段即变红 |
| **SYNC-005 保证金终于有人说得清** | 共享类型补 `deposit_cents`/`deposit_status`；Web 合约卡片显示金额与状态（冻结中会说明何时退还、何时罚没）；App 补「冻结中」一栏与保证金状态；12 条缺失中文名补齐 | `::test_sync005_no_ledger_row_reaches_the_user_without_a_chinese_label`（复现起因：修前这条是红的） |
| **APPB-001 app 装得上了** | `"@platform/core": "file:../packages/core"`。不并进根 workspaces 是有意的——否则 Web 的流水线要为它不碰的一个端装下整个 react-native。实测 1139 包 / 29 秒 | `::test_appb001_core_dependency_is_resolvable`；已实测退回 `"*"` 即变红 |
| **APPB-002/003 能起得来** | 补 `babel.config.js`（没有它 Metro 没有 `babel-preset-expo`，第一个 `<View>` 就是语法错误）与 `metro.config.js`（core 是 app/ 之外的 TS 源码，要 `watchFolders` + `nodeModulesPaths`） | `::test_appb002_babel_config_exists_with_expo_preset`、`::test_appb003_metro_config_reaches_the_workspace_package` |
| **APPB-004/005 插件↔依赖必须成对** | `app.json` 声明了 `expo-image-picker` 却没装也没 import → `expo prebuild`/EAS build 直接失败在插件解析。删声明（没有功能在用它），并加闸门。VID-041 查 `import`，**看不见配置文件里的插件名** | `::test_appb005_every_declared_expo_plugin_is_an_installed_dependency`；已实测加回一个没装的插件即变红 |
| **APPB-006 App 真的被类型检查了** | `tsconfig.json`（`strict`）+ `npm run typecheck` + CI `app-typecheck` job。了结挂了很久的 PRLX-041 / DSPR-042 | `::test_appb006_typecheck_is_configured`、`::test_appb006_ci_runs_app_typecheck`；已实测删掉类型字段则 `tsc` 退出码 2 |

**VID-050 部分兑现**：V71 的三个新依赖在本环境装上了并通过类型检查——
`expo-av@14.0.7`、`expo-network@6.0.1`、`@react-native-async-storage/async-storage@1.23.1`。
**但「装得上、类型对」不等于「在真机上跑得起来」**，VID-050 降级保留不销账；
`metro.config.js` 是本批唯一没被机器验证的改动（验它要真起 Metro，要设备）。

## 已实现（V65 批次：配了却从不告警的监控，比没有监控更危险）

> 模块 spec：[40-ops-drills.md](40-ops-drills.md)
>
> **检视结论**：前面几十批修的都是「代码里有个洞」。这一批不一样——
> 代码可能是对的，但**没有任何证据**。备份从没恢复过、`/metrics` 没有任何
> 东西消费、容量一无所知、依赖从没扫过。
>
> **写告警规则的过程本身就抓到一个洞。** 我写完 `deploy/alerts.prom.yml`
> 去核对指标名，发现最重要的三条——资金对账不平、定时任务静默、上传审核
> 积压——引用的指标 `/metrics` **根本不暴露**。告警规则不会因为指标名写错
> 而报错，**它只是永远沉默**。没有监控时你知道自己是瞎的；
> 配错了的监控让你以为自己被盖住了。这和这一路修下来的是同一个形状：
> **写错了不会报错的声明**。
>
> **依赖扫描第一次跑就有真东西**：11 条（1 critical / 4 high / 6 moderate）。
> 但数字会误导，必须分清哪些真的发给用户——`--omit=dev` 下只有 2 条，
> 全是 react-router。其中 SSR 那条对纯客户端 SPA 不适用；开放重定向那条
> 要求把用户可控字符串当跳转目标，我核对了全部调用点，当前没有暴露面。
> **但「当前没有」不是一个可以维护的状态**，所以直接升到 react-router 7
> 把问题消掉，而不是写一份「暂不受影响」的说明。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **DRILL-041 告警引用的指标必须真的存在** | 补出 `platform_reconcile_ok` / `platform_jobs_unhealthy` / `platform_uploads_pending_review`；断言规则文件里每个 `platform_*` 都在 `/metrics` 里 | `tests/test_ops_drills.py::test_drill041_every_alerted_metric_is_actually_exposed`；已实测改坏一个指标名即变红 |
| **对账指标真的在算** | 把钱凭空加进钱包，指标必须从 1 翻成 0——防的是写成常数 | `::test_drill040_the_reconciliation_metric_reflects_reality` |
| **DRILL-042 单个聚合出错不能让所有告警一起瞎** | 指标端点容错，算不出来按最坏情况上报 | `::test_metrics_endpoint_survives_a_broken_aggregate` |
| **DRILL-010 恢复校验单一实现** | 提成 `scripts/consistency_check.py`，`restore.sh` 改为调用。此前它是一个需要完整生产栈 + 人工敲 yes 才跑得到的 heredoc——**一段从没跑过的校验代码，和没有校验没有区别** | `::test_drill010_restore_script_uses_the_shared_consistency_check` |
| **DRILL-020 真的删库再恢复** | `scripts/restore_drill.py`：造真实闭环 → 备份 → 删文件 → 恢复 → 跑同一段校验 → 核对余额原样回来。进 CI | `::test_drill020_restore_drill_actually_runs_and_passes`；已实测跳过恢复步骤则退出码 1 |
| **DRILL-030 压测** | `scripts/loadtest.py`，纯标准库，输出吞吐/错误率/p50-p95-p99。**不设阈值断言**：容量取决于机器，写死数字只会在别人机器上误报 | `::test_drill030_loadtest_reports_the_numbers_that_matter` |
| **DRILL-050/051 依赖扫描** | CI `dependency-audit`：`pip-audit` + `npm audit --omit=dev`（阻断）+ 全树（仅报告）。升级 react-router 7 / vite 7 / vitest 5，全树归零 | `::test_drill050_ci_runs_the_audits_and_the_drill` |

**首批实测容量**（本容器 / SQLite / 单 worker / 并发 16）：
读 129 rps、p50 121ms、p95 175ms；写 87 rps、p50 60ms、**p95 769ms、p99 1872ms**。
写路径 30 倍长尾是 SQLite 单写锁的签名。**这些是地板，不是容量规划。**

## 已实现（V64 批次：预留了 media_urls，却从来没人传过）

> 模块 spec：[39-upload-moderation.md](39-upload-moderation.md)
>
> **检视结论**：平台有内容安全供应商抽象、有举报流程、有审核队列、
> 生产启动自检把 `moderation` 列为 P0 能力——**但图片从来不过审核**。
>
> 全仓唯一一处调用是 `get_provider("moderation").check("text", text)`，
> 只有任务文本。而 `check()` 的第三个参数就叫 `media_urls`，
> `LocalModerationProvider` 里甚至专门为它写了：
>
> ```python
> if media_urls:
>     # 本地实现看不了图/视频——明确标记为需人工复核，而不是假装通过
>     return VendorResult(..., status="review", data={"reason": "media_not_inspectable"})
> ```
>
> **这段分支从来没有被执行过。** 接口预留了、桩实现写好了、生产自检拦着
> 不让用 mock，唯独没人调用——又是「建好了却没接上」。
>
> V62 刚把「这张图是谁传的」落了库，当时给的理由是「归属落库后处置才成为
> 可能」。**处置就是这一批**——没有它，V62 建的那张表只是一张没人查的表。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **UMOD-010/042 图片真的过审了** | 上传落盘后 `check("image", "", [url])`，走既有的 `vendor_base.call`（幂等/熔断/留痕） | `tests/test_upload_moderation.py::test_umod042_moderation_actually_receives_the_image_url`——断言供应商收到的 `media_urls` 非空，专防「又一次建好了没接上」 |
| **UMOD-011/040 reject 不留痕迹** | 删命名条目、不落库、400 并说明命中标签 | `::test_umod011_rejected_upload_is_refused_and_leaves_nothing_behind` |
| **UMOD-041 删一个不伤别人** | 只删名字不动 `blobs/<sha256>`——这正是 V62 改用随机名 + 硬链接的目的 | `::test_umod041_rejecting_one_upload_does_not_break_another_users_copy` |
| **UMOD-012 review 是队列不是拒绝** | 本地实现对任何图片都返回 `review`，当拒绝会让所有非生产部署完全传不了图——那不是安全，是瘫痪 | `::test_umod012_review_passes_through_but_lands_in_the_queue` |
| **UMOD-013 供应商故障 fail open** | 本批唯一一个犹豫过的判断：上传物主要是交付凭证与纠纷证据，运维手册自己写着「交付凭证传不上去等于没有证据」。第三方抖一下的代价会落在**被侵害方**而不是违规者身上，所以故障时标 `review` 放行进队列 | `::test_umod013_provider_failure_does_not_block_the_upload` |
| **UMOD-020/021/022 人审处置** | `GET /admin/uploads/pending`、`POST /admin/uploads/{name}/resolve`；驳回＝物理删除 + 通知上传者 + 记审计。悄悄删掉让页面变裂图是最差的处理 | `::test_umod021_admin_reject_removes_the_file_and_tells_the_uploader`、`::test_umod021_admin_pass_clears_it_from_the_queue`、`::test_upload_queue_is_admin_only` |
| **UMOD-030/031 存储删除原语** | `LocalStorageProvider.delete(name)`：幂等、拒绝路径穿越、不动 blob。同时是 ACCDEL-041 将来要用的同一个原语 | `::test_umod031_delete_is_idempotent_and_refuses_traversal` |
| **UMOD-014 进 V60 处置表** | `moderation_status` / `moderation_labels` 均 `RETAIN`——这是**平台的处置留痕**，不是注销者的画像数据 | `tests/test_account_deletion.py::test_accdel021_...` 自动覆盖 |

## 已实现（V63 批次：只在开始时响一次的闹钟）

> 模块 spec：[38-dispute-respondent-reach.md](38-dispute-respondent-reach.md)
>
> **检视结论**：V61 修好了「被诉方在客户端上是哑的」——**但只修了 Web**。
> `app/App.tsx` 的任务详情里，纠纷相关的按钮只有一个：发起纠纷。
> 能开，不能答。而线下服务的执行方主要在 App 上，于是修完之后的分布是
> **最可能坐在被告席上的那群人，恰恰是唯一仍然开不了口的那群人**——
> 这比原来「所有人都开不了口」更糟，因为它看起来已经修好了。
>
> 另一半：开得了口不等于知道要开口。此前只有开案时一条通知，答辩期
> 48 小时静默过去就变成缺席裁决。**一个只在开始时响一次的闹钟，
> 和没有闹钟差别不大。**
>
> **为什么这个缺口能一直躺着**：`app/` 不在 npm workspaces 里、没有
> `tsconfig.json`、CI 也不碰它——**从来没有任何东西检查过这个文件**。
> 本批加的是字面量闸门（可靠、不需要装 expo/react-native）；
> 完整的类型检查需要改动整个仓库的 `npm install`/`npm test` 行为，
> 我在本环境无法完整验证，所以**没有推一条自己没跑过的 CI 步骤**，
> 而是记为 DSPR-042。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **DSPR-010/012 App 纠纷区块** | `DisputeBlock` 经 `disputeByTask(taskId)` 进入（App 和 Web 一样，被诉方只知道任务 id），含陈述时间线、答辩框、接受和解、结案后申诉 | `tests/test_dispute_respondent_reach.py::test_dspr010_app_can_reach_every_respondent_action`；已实测改坏 App 里任一方法名即变红 |
| **DSPR-011 说清沉默的代价** | 被诉方未答辩且未结案时显著提示「逾期平台可仅凭对方的陈述作出处理决定」+ 剩余小时 | `::test_dspr011_app_states_the_cost_of_staying_silent` |
| **DSPR-013 结案收起表单** | 服务端本来就会 409，但不该让人在手机上打完一段话才被拒 | `::test_dspr013_app_hides_the_form_once_the_dispute_is_closed` |
| **不重算服务端规则** | App 用 `response_deadline` / `appealable` 字段，不自己算 48 小时也不自己判断可否申诉——否则就是同一条规则的第三份实现 | `::test_dspr010_app_does_not_recompute_server_side_rules`（并断言 App 里不出现硬编码 48） |
| **DSPR-020/021 提醒 job** | `POST /disputes/jobs/remind-response`，周期 1h，登记进 `app/core/jobs.py`。提前量按**答辩期的 1/4** 算而非写死小时数——写死「截止前 12 小时」在把答辩期调成 6 小时的部署里永远不触发，是 DSPC-012 那个硬编码 48 的同类错误 | `::test_dspr020_respondent_is_reminded_before_the_window_closes`、`::test_dspr021_lead_time_follows_the_configured_window` |
| **DSPR-022/030 幂等** | `Dispute.response_reminded`（迁移 `a71e3f9d2b46`）。没有它，「距截止不足 N 小时」每次跑都成立＝每小时一条骚扰 | `::test_dspr030_running_the_job_twice_produces_one_reminder` |
| **DSPR-023/024 必达且不扰民** | `force=True` 绕过通知开关；已答辩的不催、已结案的不催 | `::test_dspr023_reminder_ignores_the_notification_switch`、`::test_dspr024_*` 两项 |
| **DSPR-031 新 job 自动被核对** | 调度表 ↔ 路由 ↔ `/jobz` 三方一致由 V57 的 JOB-002 自动覆盖，本批没有新写断言 | `tests/test_job_orchestration.py` 12 项全绿 |

## 已实现（V62 批次：用文件内容当文件名，等于把钥匙印在锁上）

> 模块 spec：[37-upload-capability-urls.md](37-upload-capability-urls.md)
>
> **检视结论**：`GET /api/v1/files/{name}` 完全匿名。这本身不是错误——
> `<img src>` 带不了 Authorization 头，接真实对象存储后 URL 直接指向 CDN，
> 读取端必然是匿名的。业界的标准做法是**能力 URL**：知道 URL 即有权读。
> 这个模式成立**有且只有一个前提：URL 不可猜**。
>
> 而名字是：
>
> ```python
> digest = hashlib.sha256(data).hexdigest()[:32]
> name = f"{digest}{ext}"     # 文件名就是文件内容的指纹
> ```
>
> 探针实测：
>
> ```
> A url: /api/v1/files/04523bfdcb1918b37b179fd3010ceabb.png
> B url: /api/v1/files/04523bfdcb1918b37b179fd3010ceabb.png
> same object across users: True
> offline-computed name matches: True
> anonymous GET: 200 208 bytes
> cache header: public, max-age=31536000, immutable
> ```
>
> 三件事同时成立，各自独立：
>
> 1. **能力 URL 的前提不成立。** 内容哈希对任何持有该内容的人都是公开的，
>    端点因此变成一台**存在性预言机**：拿一张候选图片离线算一次 sha256，
>    就能问平台「这张图在不在你这儿」，200 即「在」。不需登录、不留痕迹。
>    我**没有**声称的是暴力枚举——128 位枚不动；问题是这个值**不是秘密**。
> 2. **跨用户去重把两个人的数据物理合成了一份。** 省空间是对的，
>    但省的应该是磁盘、不是 URL。V60 刚建立的删除权机制管不到这里：
>    甲注销要删的对象可能同时是乙的证据，删了破坏乙的证据链，不删就是
>    没执行删除权——**内容寻址在一个有删除义务的系统里是结构性错误**。
> 3. **这个能力无法吊销。** 名字由内容决定，重新上传还是同一个名字；
>    URL 一旦泄露就没办法换，而响应还带着 `immutable` 缓存一年。
>    一个不能轮换的凭证不是凭证。
>
> 外加一条独立的缺口：**平台答不出「这张违规图片是谁传的」**——上传要求
> 登录，却没有任何地方记下上传者（`VendorCall` 只记 provider/operation/摘要）。
>
> **一个佐证**：沙箱的直传实现 `sign_upload` 用的是 `uuid.uuid4().hex`。
> 真实对象存储的形态本来就是随机令牌，**只有实际在跑的那条本地路径跑偏了**——
> 而它才是所有测试与冒烟走的路径。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **FILE-010/021 名字来自 CSPRNG** | `secrets.token_hex(16)`，与内容无关；同一份内容重复上传得到不同 URL | `tests/test_upload_capability_urls.py::test_file021_url_is_not_derivable_from_the_file_contents`（断言 sha256 既不出现在 URL 里、也取不到文件）、`::test_file010_name_is_random_so_two_uploads_of_one_file_differ` |
| **FILE-011/022 磁盘去重与 URL 去重分开** | blob 落 `blobs/<sha256>` 存一份，命名条目用 `os.link()` 硬链接；跨设备等 `OSError` 退化为复制（只损失空间，不损失正确性）。引用计数顺带解决删除困境 | `::test_file022_disk_still_dedupes_by_content`、`::test_blob_directory_is_not_itself_readable_through_the_endpoint` |
| **FILE-020 跨用户互不可达** | 甲乙上传同一份字节得到两条独立 URL 与两条归属记录 | `::test_file020_two_users_uploading_the_same_bytes_stay_separate` |
| **FILE-012/023 归属落库** | 新表 `uploaded_files`（name/owner_id/sha256/content_type/size_bytes），迁移 `f0a4c81d5e27` | `::test_file023_upload_is_attributable_to_a_user` |
| **FILE-013 把前提写下来** | `read_file` 的 docstring 写明这是能力 URL，且它能安全匿名的**唯一**依据是名字来自 CSPRNG——改 `put()` 的人必须先读到这句 | 代码注释 |
| **FILE-014 进 V60 的处置表** | `UPLOADED_FILE_DISPOSITION` 全部 `RETAIN`：上传物是交付凭证与纠纷证据，属于**交易对手方的凭证**与法定可追溯性。这是一个决定，不是默认值 | `tests/test_account_deletion.py::test_accdel021_...` 参数化新增 `UploadedFile`——V60 定的「新增一列就逼作者做一次决定」第一次真的被使用 |
| **非回归** | 匿名读、长缓存、`nosniff`、路径穿越拒绝全部不变 | `::test_upload_and_anonymous_read_still_work`，`tests/test_uploads.py` 全套 |
| **原测试的修正** | `test_upload_is_content_addressed` 原本断言两次上传 URL **相等**，把缺陷钉成了规格。改名为 `test_upload_dedupes_on_disk_but_not_in_the_url` 并断言不等 | `tests/test_uploads.py` |

## 已实现（V61 批次：被告席上没有麦克风）

> 模块 spec：[36-dispute-client-loop.md](36-dispute-client-loop.md)
>
> **检视结论**：纠纷开出来以后，当事人在客户端上是**哑的**。
> `client.ts` / `web/src` / `app` 全文搜 `statement` / `答辩`：**零命中**。
> 七个当事人侧端点里客户端只接了一个：
>
> | 端点 | 作用 | SDK | UI |
> |---|---|---|---|
> | `POST /tasks/{id}/disputes` | 发起纠纷 | ✅ | ✅ |
> | `GET /disputes/{id}` | 看这场纠纷 | ❌ | ❌ |
> | `POST /disputes/{id}/statements` | **答辩 / 举证** | ❌ | ❌ |
> | `GET /disputes/{id}/statements` | 看双方陈述 | ❌ | ❌ |
> | `POST /disputes/{id}/settlement` | 和解提案 | ✅ | ❌ |
> | `POST /disputes/{id}/settlement/accept` | 接受和解 | ✅ | ❌ |
> | `POST /disputes/{id}/appeal` | 申诉 | ❌ | ❌ |
>
> 和解的两个 SDK 方法写好了却没有任何界面调用——**死方法**，和没写一样。
>
> **后果不是「慢一点」。** 服务端把两造兼听当作裁决的硬性前置：
>
> ```python
> if not _respondent_had_voice(db, dispute, task):
>     raise conflict("被诉方尚未答辩且答辩期未过，暂不可裁决", "response_window_open")
> ```
>
> 而被诉方永远不可能答辩——没有任何客户端能写入 `DisputeStatement`。
> 于是这个判断的第一条分支在生产里是**死代码**，每次都落到「等满 48 小时」：
> **平台上线后的每一份处理决定都是缺席裁决**，被诉方从未获得陈述的手段，
> 而审计记录会显示 100% 的纠纷在「被诉方无陈述」的状态下结案。
> DSP-005 整条就是为了防止这件事，它写在服务端、有测试覆盖、**且无法实现**。
>
> 更糟的是**被诉方连这场纠纷在哪都找不到**：开案通知只说「任务 #N 有纠纷」，
> 而全站没有任何「按任务查纠纷」的端点；`dispute_id` 只在发起方那一侧的
> 返回值里。那句「请在 48 小时内协商或提交证据」还是**硬编码的 48**，
> 运维改了 `PLATFORM_DISPUTE_RESPONSE_HOURS`，它会继续理直气壮地说 48。
>
> **这是 V59 那个缺陷的第二次出现**（服务端竖起门、没有客户端能过），
> 所以这次留下机器闸门。但 V60 的教训同样适用：**闸门本身不能是一个
> 写错了不会报错的东西**。我先试过用正则扫 `client.ts` 统计覆盖率，
> 三次跑出三个不同的数字（46 / 78 / 152）——模板字符串、跨行泛型、
> 查询串拼接都能骗过正则。一个会漏报的检查器去防漏报，是自欺。
> 所以闸门做成**枚举 + 精确正则**：枚举来自 FastAPI 路由（不会抄漏），
> 匹配是按路径逐条构造的精确式（不会误判），只覆盖这一个模块。
> 宽而不准的检查没有价值。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **DSPC-001 被诉方真的能开口** | 完整当事人路径：从任务 id 找到纠纷 → 读事由 → 答辩 → 裁决前置立刻满足，不必等满答辩期 | `tests/test_dispute_client_loop.py::test_dspc001_respondent_can_speak_and_that_unblocks_the_verdict` |
| **DSPC-010 按任务查纠纷** | 新增 `GET /tasks/{task_id}/dispute`。被诉方只知道任务 id——这是他进入这场程序的唯一一条路；非当事人 403，无纠纷 404 | `::test_dspc010_respondent_cannot_be_locked_out_by_not_knowing_the_dispute_id`、`::test_dspc010_task_without_dispute_returns_404` |
| **DSPC-011 服务端给出客户端算不出的事实** | `_dump` 增加 `response_deadline` / `resolved_at` / `appealable` / `respondent_id` / `respondent_spoke`。答辩期长度与申诉窗口都是服务端配置 | `::test_dspc011_deadline_comes_from_config_not_from_a_hardcoded_48` |
| **DSPC-012 通知不再说谎** | 带上任务号，小时数取自 `settings.DISPUTE_RESPONSE_HOURS`，并指明逾期会缺席裁决 | `::test_dspc012_open_notification_carries_the_task_and_the_configured_hours`（断言改配置后正文里不再出现 48） |
| **DSPC-013 陈述权不能被通知开关放弃** | `notify(..., force=True)`：此前只有 `funds` 类必达，纠纷开案属于 `task` 类，用户关掉就收不到——等于用一个开关放弃了自己的答辩机会 | `::test_dspc013_dispute_notice_ignores_the_category_switch` |
| **DSPC-020/021 SDK 与网页面板** | `dispute` / `disputeByTask` / `disputeStatements` / `addDisputeStatement` / `appealDispute`；`web/src/DisputePanel.tsx` 提供陈述时间线、答辩框（显示截止时间）、和解提案与接受（把两个死方法接上）、结案后的申诉入口 | `packages/core/src/client.test.ts::DSPC-001/020` 三项，`npm run build:web` 通过 |
| **DSPC-030 `appealable` 与端点同一个判断** | `_appeal_block()` 是唯一实现，端点与客户端按钮共用。此前三条规则只长在端点里，客户端要画按钮就得再实现一遍 | `::test_dspc030_appealable_flag_and_the_appeal_endpoint_never_disagree`（双向）、`::test_dspc030_expired_appeal_window_closes_the_flag_too` |
| **DSPC-040 机器闸门** | 纠纷模块所有 `get_current_user` 端点（排除 job）的路径必须在 `client.ts` 里有对应调用 | `::test_dspc040_every_party_facing_dispute_endpoint_is_reachable_from_the_sdk`、`::test_dspc040_the_four_actions_that_were_missing_are_named_explicitly`；已实测：把 SDK 里任一路径改坏，两条都变红 |

## 已实现（V60 批次：把钱锁在一个再也登不上的账户里）

> 模块 spec：[35-account-deletion.md](35-account-deletion.md)
>
> **检视结论**：注销是全站唯一一个「用户主动把自己永久锁在门外」的操作——
> `is_deleted` 置位、手机号改写、全部会话吊销，此后登录态 403、密码登录 400。
> **闸门放行一次，就等于永久锁门一次。** 探针跑下来，它错了三处。
>
> **一、钱包是三态的，闸门只看了一态。**
>
> ```
> WITHDRAW:   200 {'status': 'pending_review', 'available_cents': 0, 'frozen_cents': 1500000}
> WALLET:     {'available_cents': 0, 'escrow_cents': 0, 'frozen_cents': 1500000}
> DEACTIVATE: 200 {'deleted': True}
> ```
>
> 一笔 ¥15,000 的提现进了 AML 人工复核，钱从可用挪到冻结、可用归零，
> 于是 `if acct.available_cents > 0` 认为「没钱了」，放行。
> 复核**驳回**时 `available_cents += amount` —— ¥15,000 退回一个再也登不上、
> 手机号已改写、连密码登录都被拒的账户，永久搁浅。
> 而驳回不是意外：大额提现进人审的全部意义就是它可能被驳回。
>
> **二、拦截条件是两张手抄的白名单，已经抄漏了一个。**
> `Dispute.status == "open"` 漏掉了 `appealed`（申诉复核中，`appeal-verdict`
> **会重新分账**）；模型上那行注释 `# open/resolved/settled` 自己也漏了它——
> **注释和代码同时错，还互相印证**，这是最难发现的一种错。
>
> **三、注销后银行卡号原样留在库里。**
> `users.real_name` 被小心地清成了 `""`，而 `payout_accounts` 里
> 一模一样的姓名加一张完整卡号（`6222021234567890123` / `张三`）原样留下。
> 不是「该不该留」的问题——是**没有人做过这个决定**：注销就是一段手写的
> 六行赋值，凭作者当时想得起来的字段，以后每加一列默认行为都是「悄悄留下」。
>
> **关键判断：不能一删了之，删过头本身违法。**《反洗钱法》第十九条要求客户
> 身份资料与交易记录至少保存五年；《个人信息保护法》第四十七条也给删除权
> 写了「法定保存期限未届满」的例外。所以正确形态是**逐字段三选一**
> （删除 / 脱敏保留 / 原样保留），而且这张表必须是**声明**——
> 新增一列就逼作者做一次决定，而不是让它默默留下。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **ACCDEL-010 闸门看钱包三态之和** | `available + escrow + frozen > 0` 一律拒绝。钱本身是事实来源，任何单态都不是 | `tests/test_account_deletion.py::test_accdel010_pending_withdrawal_review_blocks_deactivation` |
| **ACCDEL-011 一次说全** | 三个态在一条消息里各自给出金额与可执行指路，别让用户逐个撞墙；错误码 `funds_remaining` | `::test_accdel011_message_names_every_blocking_bucket_at_once` |
| **ACCDEL-012 反向判断终态** | `contract.SETTLED_STATUSES` / `dispute.CLOSED_STATUSES` 声明「已出账终态」，不在其中的一律算进行中。新增状态忘了登记 → **多拦一次注销**（安全侧），而不是放走一笔钱 | `::test_accdel012_settled_status_sets_are_declared_not_hand_copied` |
| **ACCDEL-013 `appealed` 必须拦** | 申诉复核会重新分账，此刻注销等于放弃一笔还没算完的钱 | `::test_accdel013_appealed_dispute_blocks_deactivation` |
| **ACCDEL-020/021 处置表逐列覆盖模型** | `app/modules/account/deletion.py` 的 `USER_DISPOSITION` / `PAYOUT_DISPOSITION` 声明每一列是删除/脱敏/保留，`erase_personal_data()` 是唯一执行入口；反射比对，多写或漏写都红 | `::test_accdel021_disposition_table_covers_exactly_the_model_columns`（参数化 User + PayoutAccount） |
| **ACCDEL-022/023 脱敏而非清空** | `real_name → 张*`、`account_no → 6222****0123`、`holder_name → 张*`。掩码后**不足以再发起打款**，这是有意的 | `::test_accdel022_027_dispositions_are_actually_applied` |
| **ACCDEL-024/025 权限与封禁** | `is_admin` 置 `False`（注销一个管理员却留着管理员标记 = 留了一枚定时炸弹）；`is_banned` **不清**，注销不是洗白封禁的手段 | 同上、`::test_accdel025_deactivation_does_not_wash_away_a_ban` |
| **ACCDEL-027 对手方的凭证保留** | 信用分与评价聚合不是注销者一个人的数据 | `::test_accdel022_027_dispositions_are_actually_applied` |
| **ACCDEL-030 闸门不是死路** | 复核出结果、冻结清零后照常可注销；断言三态全零这条不变量本身，而不是「某几个 409」 | `::test_accdel030_review_cleared_then_deactivation_leaves_all_buckets_zero` |
| **ACCDEL-032 扫全表** | 已注销用户名下不得再有连续 12 位以上纯数字的卡号——查整张表，而不是只看刚注销的那一行 | `::test_accdel032_no_full_card_number_survives_deletion` |

## 已实现（V59 批次：门建好了，却没有钥匙孔）

> 模块 spec：[34-captcha-e2e.md](34-captcha-e2e.md)
>
> **检视结论——这是我上上批（V56）自己挖的坑。** 服务端把人机验证阶梯做得
> 很完整：`CaptchaProvider` 抽象、软阈值、事件留痕、错误验证码计入失败，
> 还写了测试。**但是没有任何一个客户端能满足这道门：**
>
> ```
> packages/core/src/client.ts:
>   login(phone, password) { ... { phone, password } }   // 没有 captcha_token
> web/src/pages/Login.tsx:   没有任何验证码 UI
> app/App.tsx:               同上
> ```
>
> 默认 `CAPTCHA_PROVIDER=none` 是直通实现，所以当前一切正常。
> 但 `docs/OPERATIONS.md` 明明白白建议「配 `PLATFORM_CAPTCHA_PROVIDER`
> 接第三方」——**运维照做，全站登录立刻半死**：任何连续输错 3 次密码的用户
> 都交不出令牌，被锁在门外直到窗口过期，然后重复。
>
> 我建这道阶梯的理由是「给被误伤的真人一条自证的路」。
> **没有客户端支持时，它反而变成了一堵比封禁更早生效的墙。**
>
> 这和 V51 的教训是同一句话的两半：「接口预留了却跑不通，等于没预留」——
> 而这里是**门建好了却没有钥匙孔**。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **CAP-030 端到端真的走得通** | 提交 → `captcha_required` → 拉配置 → 带令牌重试 → 登进去 | `tests/test_captcha_e2e.py::test_cap030_documented_client_flow_can_actually_get_through` |
| **CAP-010/031 SDK 真的把令牌发出去** | `login(phone, password, captchaToken?)`。UI 做了而 SDK 不传等于没做——V56 就是这么留下缺口的 | `packages/core/src/client.test.ts::CAP-031 login 确实把验证码令牌发出去了` |
| **CAP-002/032 公开配置端点** | `GET /auth/captcha-config` 返回 provider / enforcing / site_key / script_url。**无需登录**——登录页还没有 token | `::test_cap032_config_endpoint_needs_no_login` |
| **CAP-003/033 反应式，不主动问** | 客户端**不**预先询问「我现在需不需要验证」：那等于把「这个 IP 已触发风控」告诉任何人，白送一个探测风控状态的接口。断言触发前后该端点响应逐字节相同 | `::test_cap033_config_does_not_leak_whether_this_ip_is_under_suspicion` |
| **CAP-011/012 Web 挑战组件** | 登录页捕获 `captcha_required` → 拉配置 → 渲染。按 hCaptcha/Turnstile/腾讯云**共同的形状**实现（脚本 + 站点公钥 + 回调拿 token），接哪家只改环境变量；没有脚本地址时退化为可输入的令牌框并**如实标注是什么**，不画假滑块 | `web/src/CaptchaChallenge.tsx`，构建通过 |
| **CAP-020/034 机器闸门** | 生产 + 会真的拦人的实现 + 没配站点公钥 → **拒绝启动**。这不是「配置不全」，是登录不可用 | `::test_cap034_production_refuses_enforcing_captcha_without_a_site_key`、`::test_passthrough_captcha_does_not_need_a_site_key`（直通不被误伤） |
| **CAP-035 不回归** | 默认配置下登录流程与改造前完全一致；老客户端不带该字段照样能登 | `::test_cap035_default_configuration_behaves_exactly_as_before`、`::test_login_still_accepts_a_request_without_the_captcha_field` |

## 已实现（V58 批次：同一个动作两条路，最常走的那条抄了近道）

> 模块 spec：[33-moderation-actions.md](33-moderation-actions.md)
>
> **检视结论**：封禁一个用户在这个系统里有两条路，做的事完全不一样。
>
> `/admin/users/{id}/ban`（OPS-013 那条，写得很仔细）：算影响面 →
> 通知在途合约对手方 → 关闭待处理报名并通知 → 走状态机下架挂单 → 记审计。
>
> `/admin/reports/{id}/resolve` 且 `action="ban_user"`（**审核队列**那条）：
>
> ```python
> user.is_banned = True
> db.add(user)
> ```
>
> **就这两行，上面五件事一件都没做。** 而审核队列恰恰是审核员日常真正在用的
> 那个界面——写得仔细的那条反而在另一个页面上，用得更少。
>
> 后果不是「少了点提示」：在途合约的对手方**永远不会被告知**他的钱还托管在
> 一个已被封禁、永远不会来验收的人那里。OPS-013 整节就是为了防止这件事，
> 结果最常用的入口把它完全绕开了。而这个函数的 docstring 写着
> 「处置留痕（RISK-002/006）」——**它一条审计都没记**。
>
> 同一个函数里还有一处绕过状态机：`task.status = "cancelled"` 直接赋值，
> 不派发 `task.cancelled` 事件。今天只是少个事件（当前订阅者恰好提前返回），
> 但**下一个给这个事件加订阅者的人——比如托管退款——会发现它在这条路径上
> 根本不触发**。发布者也收不到任何通知：任务就这么消失了，无从申诉。
>
> 和 [32 号](32-job-orchestration.md) 是同一类问题的另一种形态：
> 32 号是「同一份清单抄在两处」→ 漂移；这里是「同一个动作实现在两处」→
> **能力不对等**。两者都不会报错，区别只在于后者错在**用户的钱和知情权**。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **MOD-001 单一实现** | 处置副作用全部收进 `admin/service.py`：`ban_user()` / `takedown_task()` / `takedown_content()`，两个端点都调它，端点只管鉴权取参 | 全量回归 532 tests |
| **MOD-023 两条路径逐项对等（核心用例）** | 同样的封禁，从审核队列进和从用户页进，封禁状态/挂单状态/待处理报名数快照必须一模一样 | `tests/test_moderation_actions.py::test_mod023_both_ban_paths_have_identical_side_effects` |
| **MOD-020 对手方通知** | 在途合约对手方必须被告知——他的钱还托管在一个被封的人那里 | `::test_mod020_ban_from_report_queue_notifies_the_counterparty` |
| **MOD-021 报名关闭** | 报名者不该继续等一个永远没人来选他的任务 | `::test_mod021_ban_from_report_queue_closes_pending_applications` |
| **MOD-022 挂单下架走状态机** | 走了 `transition()` 才有 `task.cancelled` 事件；断言发件箱里确实有这条事件 | `::test_mod022_ban_from_report_queue_takes_down_listings_via_the_state_machine` |
| **MOD-003/024 下架要告诉受影响的人** | 发布者收到**带原因**的通知（否则无从申诉），报名者收到关闭通知；已成交（有托管）的任务**拒绝**被审核单方作废，指向纠纷流程 | `::test_mod024_task_takedown_notifies_creator_and_applicants`、`::test_takedown_refuses_tasks_that_already_have_escrow` |
| **MOD-004/025 每次处置都记审计（含驳回）** | 驳回同样是决定：谁在什么时候驳回了哪条举报，是事后复盘的关键。只写 `report.handled_by` 不够——审计日志按动作查询时看不到它 | `::test_mod025_every_resolution_including_dismiss_is_audited`、`::test_takedown_and_ban_actions_are_individually_queryable` |
| **MOD-011/026 状态机唯一入口机器强制** | 全仓库 **AST** 扫描：`task.status = ` 只允许出现在 `transition()` 内。用 AST 而不是正则——第一版正则把**讲这件事的文档字符串**也当成了违规 | `::test_mod026_nothing_bypasses_the_state_machine` |

## 已实现（V57 批次：从来没有被架起来过的那道安全网）

> 模块 spec：[32-job-orchestration.md](32-job-orchestration.md)
>
> **检视结论**：拿 `scripts/cron.py` 的调度表和代码里的 job 端点对了一遍，对不上：
>
> ```
> 代码里的 job 端点： 14
>   ✗ /admin/jobs/reconcile            没有任何调度器会触发它
>   ✗ /contracts/jobs/expire-unsigned  没有任何调度器会触发它
> cron 表里但代码里找不到的： ['/jobs/expire-unsigned']
> ```
>
> **缺口一（最严重）**：`/admin/jobs/reconcile` 是五条资金不变量的日终对账，
> OPERATIONS 把它列为最高优先级告警「直接推值班手机」。但它既不在调度表里，
> 鉴权还是 `require_admin`——**调度器根本调不动**。所谓「日终对账」实际上是
> 一个需要有人每天记得手动点的按钮。**这门生意最重要的那道安全网，
> 从来没有被架起来过。**
>
> **缺口二**：cron 写的是 `/jobs/expire-unsigned`，真实路径是
> `/contracts/jobs/expire-unsigned`（合约路由带前缀）。一直在打 404，
> 而这个 job 负责解冻超期未签合约的执行者保证金——钱一直冻着。
>
> **缺口三（让前两条得以长期存在）**：`/jobz` 遍历 `JobLock` 表，
> **从未被调用过的 job 根本没有行**，于是在监控里干脆不存在；
> 告警规则遍历的也是已有记录，缺席的那个不触发任何东西。
> **专门用来发现「job 静默不跑」的监控，对最严重的那种静默完全免疫。**
> 冒烟脚本每次打印「0 个 job 有记录」，我读过很多遍都当成了正常输出——
> **空列表看起来太像一切正常了。**
>
> 三个缺口是同一个根因的三种表现：**调度表是手抄的**，和端点定义分处两地。
> 手抄的清单一定会漂移，区别只是什么时候被发现——而它漂了不会报错。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **JOB-001 唯一事实来源** | `app/core/jobs.py::JOBS` 一份声明（路径 + 周期 + 锁名 + 用途），`cron.py` 直接 import 它，不再手抄路径 | `tests/test_job_orchestration.py::test_cron_reads_the_single_declaration_instead_of_a_hand_copied_list` |
| **JOB-002/030 漂移在 CI 里就红** | 测试**从 OpenAPI 自动发现** job 端点，与声明表双向核对：多一个少一个都失败。这条比前一条更重要——它让不同步不用等人想起来去对 | `::test_job030_declared_jobs_and_actual_routes_match_both_ways` |
| **JOB-034 逐条打过去确认不是 404** | 路由表对得上还不够，真发一次请求才算数（缺口二的直接反面） | `::test_job034_every_scheduled_path_actually_routes` |
| **JOB-010/012/031 监控对照期望而非罗列现状** | `/jobz` 以声明表为基准，从未跑过的显式标 `never_run` 并**留在列表里**；stale 按**每个 job 自己的周期**判定（一天一次的清理和两分钟一次的补做用同一个绝对阈值只会同时误报和漏报） | `::test_job031_jobz_lists_every_expected_job_including_never_run`、`::test_never_run_flips_after_the_job_actually_runs` |
| **JOB-011/035 指标** | `platform_jobs_never_run` / `platform_jobs_stale` | `::test_job035_metrics_expose_never_run` |
| **JOB-020/032 资金对账终于能被调度器触发** | 鉴权改为「job 令牌**或**管理员」，加单实例锁，纳入调度表（周期一天） | `::test_job032_reconcile_can_be_triggered_by_the_scheduler`、`::test_reconcile_still_works_for_admins_and_rejects_everyone_else` |
| **JOB-021/033 告警闭环仍然成立** | 调度器触发时差错工单归属平台账户（不是某个碰巧在场的管理员），照常通知全体管理员 | `::test_job033_scheduler_triggered_mismatch_still_raises_the_alarm`（人为制造不平，断言工单与通知都出来了） |
| **JOB-023 修正 expire-unsigned 路径** | 补上 `/contracts` 前缀 | 由 JOB-030/034 覆盖 |
| 锁名与端点一致 | `lock_name` 与端点上 `job_slot()` 的参数对不上，`/jobz` 会永远显示 never_run | `::test_lock_names_are_unique_and_match_the_endpoints` |
| 冒烟脚本不再放过空列表 | 那行输出从「0 个 job 有记录」变成断言**全部应有 job 都在监控里** | `scripts/smoke.py` |

## 已实现（V56 批次：一句说谎的注释——跨副本封禁与人机验证）

> 模块 spec：[31-security-events.md](31-security-events.md)（落地 SEC-021/022/023）
>
> **检视结论**：`app/core/guard.py` 里原本写着
>
> ```python
> # 封禁本身落 DB（SecurityEvent），因此跨副本仍能看到。
> _banned_until: dict[str, float] = {}
> ```
>
> **那个表根本不存在。** 全仓库 grep 只有这一行注释提到它，封禁就是一个
> 进程内 dict。三副本部署下：攻击者换个连接打到别的副本照样过；
> 每副本各自计数，有效阈值被放大三倍；管理员解封**只解了一个副本**，
> 被误封的公司出口 IP 之后还有 2/3 概率被拒——用户报「有时候能登录
> 有时候不能」，客服根本复现不出来。**时好时坏的故障比稳定的故障
> 难查一个数量级。**
>
> 同一批还有第二处：`docs/OPERATIONS.md` 写着人机验证「抽象位已留（SEC-021）」，
> 而全仓库没有一行 captcha 代码。读文档的人会以为接入只是换个环境变量。
>
> **注释和文档比代码更容易骗人，因为没有测试盯着它们。**

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **SECEV-001/002 封禁状态落 DB** | `SecurityEvent` 表真正建出来；封禁以 DB 为准，进程内只保留 5 秒的**有界最终一致**快照（封禁时长以分钟计，几秒滞后对拦截与解封都无所谓，换来不必每个写请求查一次库） | `tests/test_security_events.py::test_secev030_ban_survives_a_process_restart`（清掉进程状态＝「请求打到另一个副本」，改造前这里会放行） |
| **SECEV-003/032 失败计数跨副本累计** | 计数同样落 DB，否则 N 个副本把有效阈值放大了 N 倍 | `::test_secev032_failures_accumulate_across_replicas`（每次失败都「换个副本」，仍能累计到阈值） |
| **SECEV-021/031 解封全局生效** | 解封改 `expires_at` 并写 `unban` 事件，**不删记录**——删了就没法回答「这个 IP 什么时候被封过、谁解的」 | `::test_secev031_unban_takes_effect_globally` |
| 实现中被测试逮到的真实缺陷 | 解封接口自己也走全局写限流中间件，而中间件按 IP 拒绝被封的来源。误封整个公司出口 IP 时管理员很可能就坐在那个 IP 后面——**补救路径恰好在最需要它的时候不可用**。只放行安全处置路径（仍要求管理员身份） | `::test_the_unban_endpoint_is_not_blocked_by_the_ban_itself` |
| **SECEV-004/036 写入量天然有界** | 封禁检查在计数**之前**，被封的 IP 不再产生新失败记录，单 IP 每窗口最多写「阈值」条。这不是巧合，是把顺序排对了才有的性质 | `::test_secev036_failure_records_per_window_are_bounded_by_the_threshold` |
| **SECEV-010 `CaptchaProvider` 真的建出来** | `NoCaptcha`（诚实命名：它不验证任何东西）+ `SandboxCaptcha`（**真的会拒**，不是只返回 True 的桩）+ 注册进 vendor registry，面板里如实标注等级 | `::test_no_captcha_is_honestly_named_as_not_enforcing`、`::test_captcha_provider_appears_in_the_vendor_panel` |
| **SECEV-011 验证码是给被误伤的人一条自证的路** | 没有它时风控的唯一升级手段是封禁——手滑输错几次的真人和撞库脚本得到的处置完全一样。加入后阶梯变成 正常 → 要求验证 → 封禁：**误封率下降，拦截率上升** | `::test_secev011_captcha_gives_a_real_person_a_way_out_instead_of_a_ban`（真人带验证码登进去了，且没被封） |
| **SECEV-013 错误验证码计入失败** | 否则可以用无限次错误验证码把真正的登录尝试藏在噪音里 | `::test_secev013_wrong_captcha_counts_as_a_failure` |
| **SECEV-014 直通实现也留痕** | 没接真实供应商时风控趋势仍然看得见 | `::test_secev034_passthrough_provider_still_records_the_event` |
| **SECEV-020 看板读 DB** | 全局封禁列表 + 观察名单 + 窗口内验证码触发数；封禁条目带**原因** | `::test_secev020_board_reads_shared_state`、`::test_secev037_board_requires_admin` |
| **SECEV-006 保留期分级** | 清理 `auth_failure` 这类高频噪音；**封禁与解封是运营处置留痕，不随保留期清理** | `::test_secev006_purge_keeps_disposition_records` |

## 已实现（V55 批次：反洗钱——把金额减 1 元多点几次就能绕过的门槛）

> 模块 spec：[30-aml.md](30-aml.md)（落地 FIN-040）
>
> **检视结论（探针复现，不是推测）**：提现风控此前判的是**单笔** ≥¥1 万转人审。
> 同一账号连续提现 5 笔 ¥9,999：
>
> ```
> 五笔 ¥9999 提现结果： [(200,'done'), (200,'done'), (200,'done'), (200,'done'), (200,'done')]
> 进入人审的笔数： 0
> ```
>
> **¥49,995 出账，零人审。** 不需要任何技术手段——把金额减 1 元，多点几次。
> 拆分（structuring）是绕过单笔门槛最古老最简单的手法，恰恰是反洗钱监测的头号目标。
>
> **本批次刻意划定的边界**：接存管后直接报送义务在持牌机构一侧，
> 但存管机构只看到资金流、**看不到业务语义**——哪笔钱对应哪个任务、
> 双方是不是同一个人的马甲。代码做的是「平台看得见而存管方看不见」的那部分，
> 不假装能替代持牌机构的报送系统。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **AML-001/040 阈值从「单笔」改为「累计」** | 单笔 ≥ 门槛**或**当日累计 ≥ 门槛都转人审——直接堵掉探针复现的洞 | `tests/test_aml.py::test_aml040_structuring_no_longer_slips_through`（第一笔正常放行，2~5 笔全部转人审；改造前是 0 笔）、`::test_aml001_single_large_withdrawal_still_reviewed` |
| **AML-003/041 判定在锁内** | 风控判定与余额判断共用同一个 `today_withdrawn`，都在钱包锁内——并发提现各自读到「还没超」再分别放行，和拆分是同一个洞的两种利用姿势 | `::test_aml041_concurrent_withdrawals_cannot_dodge_the_cumulative_threshold`（真多线程，至多一笔即时出账） |
| **AML-010 拆分识别带数值** | 滚动窗口内多笔金额接近但均低于单笔门槛 → 记形态，触发依据带出具体区间与笔数 | `::test_aml010_structuring_pattern_is_identified_with_numbers` |
| **AML-011/042 快进快出** | 充值后短时间内几乎原样提现**且中间无真实成交**。「无成交」是关键：有成交说明钱是挣来的，那是正常业务 | `::test_aml042_passthrough_is_detected`、`::test_passthrough_not_flagged_when_the_money_was_earned` |
| **AML-013/043 收款账户聚集** | 多个用户绑同一张卡。一人多号已由证件号摘要拦住，但**收款账户**这一维度此前没人看。**只标记不拦截**——夫妻共用一张卡、帮父母代收都是真实场景 | `::test_aml043_shared_payout_account_is_flagged_but_not_blocked` |
| **AML-030/031/045 不得泄露（tipping-off）** | 《反洗钱法》第五条要求对反洗钱工作信息保密。用户只看到中性措辞「该笔提现需人工复核」；**绝不回 reasons**——那既违反保密义务，也直接教会对方下次怎么规避 | `::test_aml045_user_facing_message_is_neutral`（扫「可疑/反洗钱/拆分/风控」等字样）、`::test_aml044_suspicious_flags_do_not_leak_into_data_export`（LAW-032 的导出权在这里让位） |
| **AML-021 不自动报送** | 代码只识别、留痕、转人审、可导出。报送是合规官的动作，要人判断要签字；自动报送既不合规也不负责任 | `::test_compliance_officer_reviews_and_records_the_conclusion` |
| **AML-046 只有管理员能读** | 整个 AML 路由**没有任何面向用户的端点**——这是刻意的 | `::test_aml046_only_admins_can_read_the_suspicious_list` |
| **AML-047 不能误伤正常用户** | 风控做得太紧等于停业：小额提现照常即时到账 | `::test_aml047_ordinary_withdrawals_are_not_held` |
| 实现中补的真实缺口 | 最初只有「拆分」和「大额报告线」会留痕，单纯因累计达线被扣下的提现**什么都不写**。复核的人打开队列看到一堆没有说明的条目只能全部放行——那等于风控没做，还平白让用户等了一天。改为**被扣下的提现必须带着理由**，`needs_review` 与 `reasons` 等价 | `::test_every_held_withdrawal_carries_a_reviewable_reason` |
| **AML-023 保存期与删除权的冲突** | 反洗钱要求交易记录保存 5 年，与 LAW-032 删除权真实冲突且反洗钱法优先（PIPL 第四十七条把「法律另有规定」列为删除义务例外） | 见 30 号 spec 第 D 节 |

## 已实现（V54 批次：个税代扣代缴——平台一直在做扣缴义务人该做而没做的事）

> 模块 spec：[29-tax-withholding.md](29-tax-withholding.md)（落地 FIN-030/031/032）
>
> **检视结论**：`release()` 一直只有**两个**收款方——执行者和平台。
> 平台向自然人支付报酬，却一分税没扣、没有任何完税记录。
> 《个人所得税法》第九条：以支付所得的单位或者个人为扣缴义务人；
> 《税收征收管理法》第六十九条：应扣未扣，**处应扣未扣税款 50% 至 3 倍罚款**。
>
> 这不是代码疏漏，是这门生意的合规底座缺了一块。
>
> **代码不替你选按哪种所得课税**（劳务报酬 vs 经营所得委托代征 vs 自行申报，
> 这是税务与法律决定），但它做三件事：把三条路都变成可执行可测试的实现、
> **逼你必须显式选一条**（不选生产不让启动）、无论选哪条钱都必须守恒可对账。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **TAX-042 劳务报酬预扣预缴** | `LaborIncomeTax`：≤4000 元减除 800、>4000 减除 20%，三档预扣率与速算扣除，全是现行规定的真实算法而非占位 | `tests/test_tax_withholding.py::test_tax042_labor_income_brackets`（7 个分档）、`::test_tax042_bracket_boundary_is_not_off_by_one`（四千元分界最容易把 `<` 写成 `<=`，写反的后果是每笔四千上下的报酬都扣错） |
| **TAX-002 三条路都能跑** | `NoWithholdingTax`（诚实命名，不叫 Default）/ `LaborIncomeTax` / `CommissionedCollectionTax`，注册进 vendor registry | 同上 `::test_commissioned_collection_uses_configured_rate`（说明里写明「以委托代征协议为前提」——没有协议按这个税率扣是另一种违法） |
| **TAX-001/044 上线红线** | 生产 + `TAX_MODE=none` → 启动自检失败。允许选 `self_declared`（不扣），但**必须是显式选择**：默认的 none 意味着「没人想过这件事」 | `::test_tax044_production_refuses_to_start_without_a_tax_decision`、`::test_declaring_withholding_without_a_rule_is_also_refused`（配了一半比没配更危险）、`::test_self_declared_passes_the_gate` |
| **TAX-010/012 代扣的钱独立成户** | `TAX_USER_ID = -1` 专户。它既不是平台收入也不再是执行者的钱，混进佣金账户的后果是账面上平台「赚」多了，等缴库才发现那笔钱早被当成收入结算走了 | `::test_tax012_withheld_money_is_not_mixed_into_platform_income` |
| **TAX-011 三方分账（FIN-031）** | 放款分账变成执行者 / 平台 / 税款专户三个收款方，`purpose="tax"` | `::test_tax040_payout_is_split_three_ways`（含分账守恒） |
| **TAX-012 第五条不变量** | `税款专户余额 == Σ代扣 − Σ已缴库`；全局守恒把 `tax_remit` 计入流出 | `::test_tax041_all_five_invariants_hold`、`::test_tax045_remit_zeroes_the_account_and_is_not_double_counted` |
| **TAX-047 四条路一条都不能漏** | 整体放款 / 分期放款 / 裁决执行 / 取消补偿共用 `_withhold()`——只改整体放款会让所有分期合约悄悄免税 | `::test_tax047_milestone_release_also_withholds`、`::test_verdict_execution_also_withholds` |
| **TAX-021/046 措辞准确** | 出具的是**代扣明细**不是完税证明：劳务报酬是预扣预缴，年度汇算还要并入综合所得多退少补。让用户以为能直接抵扣是在帮他犯错 | `::test_tax046_executor_sees_detail_and_it_does_not_claim_to_be_a_tax_certificate` |
| 流水如实反映收入与扣除 | 先全额确认收入、再从中代扣两条流水；按净额直接入账会让执行者在流水里**看不到自己被扣过税** | `::test_executor_ledger_shows_income_then_withholding` |
| **TAX-022 平台服务费发票（FIN-032）** | 只开佣金部分。平台没有为劳务报酬开票的资格，含糊其辞地"帮你开全额发票"是虚开不是服务 | `::test_tax022_invoice_covers_only_the_platform_fee`、`::test_invoice_only_for_the_paying_party_and_only_once` |
| **TAX-043 向后兼容** | 默认 `none` 模式行为与改造前**逐字节一致**（不扣税、两方分账）——向后兼容不能靠嘴说 | `::test_tax043_none_mode_behaves_exactly_as_before` |
| **TAX-014 已代扣不自动冲回** | 申诉改判发生在申报之后时，正确做法是**更正申报**而非账上偷偷冲销——装作能自动冲回，会做出一套和税局对不上的账 | 写入 spec 与代码注释，由人处理 |
| 合规态自检扩展 | `scripts/sandbox_check.py` 现在跑「存管 + 可靠签名 + 第三方存证 + **个税代扣**」28 项，含三方分账、五不变量、缴库后仍守恒 | CI 作业 `sandbox-compliance` |

## 已实现（V53 批次：事件投递——别让锦上添花拖死存在理由）

> 模块 spec：[28-event-delivery.md](28-event-delivery.md)（覆盖 CONC-030/031 与 SEC-040）
>
> **检视结论（用探针复现过，不是推测）**：`app/core/events.py` 原本十七行，
> 同步派发、无隔离。`task.completed` 上挂着 **6 个** handler，
> 和真正的放款在**同一个事务同一个请求**里。把知识卡片 handler 改成抛
> `RuntimeError`（真实诱因：卡片生成走 LLM，超时很正常），
> 验收接口直接崩、**执行方一分钱拿不到**。
>
> 这是本末倒置：知识库是锦上添花，放款是这个平台的存在理由。
>
> 顺带堵掉最容易想到的那个「修法」——`try: ... except: pass`。
> 那会把事故从「崩掉」变成「静默丢失」：用户永远收不到那条通知，
> 而没有任何人知道。**后者比前者更糟。**

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **EVT-010/040 失败隔离** | 每个 handler 在 `begin_nested()` 的 SAVEPOINT 里跑，失败只回滚它自己那一段，业务事务与其它 handler 不受影响 | `tests/test_event_delivery.py::test_evt040_derived_handler_failure_does_not_roll_back_the_payout`（验收照常成功且到账 27600）、`::test_evt040_savepoint_rolls_back_only_the_failing_handler` |
| **EVT-011 绝不静默** | 失败写 `EventDelivery(status=failed)` + 结构化告警日志；记录写在**业务会话**里，业务回滚则记录一起消失（那件事本来就没发生） | 同上（断言 `last_error` 含异常类型） |
| **EVT-012/041 critical 例外** | 判定标准不是「重不重要」（那样人人都想标 critical），而是**这个副作用缺失会不会让已提交的业务事实无法自圆其说**。存证入链属于此类：签了字却没有链上记录，等于平台承诺的证据能力有洞 | `::test_evt041_critical_handler_failure_aborts_the_business_transaction`（钱一分没动） |
| **EVT-001/045 事务性发件箱** | `publish()` 在业务事务内写 `OutboxEvent`，与业务改动同生共死；记录发布副本 | `::test_evt045_rolled_back_transaction_leaves_no_event`、`::test_evt001_committed_transaction_records_the_event` |
| **EVT-002/043 恰好一次** | `(event_id, handler)` 唯一约束——不是靠代码自觉，是靠数据库；跨副本同样成立 | `::test_evt043_drain_recovers_and_does_not_double_apply`（重复 drain 不重复补） |
| **EVT-021 / CONC-031 / SEC-040 跨副本补做** | drain job 从库里的发件箱补做，受 `job_slot` 单实例锁保护：**任何副本都能补做任何副本发布的事件**，不需要 Redis/Kafka。刻意选发件箱而非 MQ：同库同事务天然没有两阶段提交问题，真要上 MQ 让它从发件箱消费即可，业务代码一行不动 | 同上 |
| **EVT-020/046 必填的重试声明** | `subscribe(..., retry=)` 是必填关键字参数。**检视时改过一次名**：最初叫 `idempotent`，但有了 SAVEPOINT，失败的写入已被回滚干净，纯 DB handler 几乎自动可重试——真正的问题是**时序**：「隔一段时间再补做，还对吗」 | `::test_evt046_subscribe_without_retry_declaration_is_rejected`、`::test_every_registered_handler_declared_its_retry_policy`（全站扫一遍，不允许绕过声明） |
| **EVT-022/044 死信** | `retry=False` 的失败直接进死信。当前唯一这样标的是**周期任务自动续期**——它会创建一个带预算的新任务，几小时后由后台悄悄补出来一单，比缺这一期更糟。存证入链同样 `retry=False`：几小时后补进去的条目 `seq` 会排在真实发生更晚的事件之后，链所声称的「按此顺序发生」就成了假话，而这条链是要拿去举证的 | `::test_evt044_non_retryable_handler_goes_straight_to_dead_letter`、`::test_evt022_dead_letters_are_visible_to_operators` |
| **EVT-023 重试上限** | 5 次后转死信，避免无限重试打爆日志与数据库 | `::test_evt023_repeated_failures_become_dead_letters` |
| **EVT-004 保留期** | 清理只删**已完成**的旧事件；失败与死信连同它们的事件一起留着（否则重试时读不到 payload） | `::test_evt004_purge_keeps_unfinished_deliveries` |
| **EVT-030/031 可观测** | `/metrics` 出 `platform_event_pending_retry` 与 `platform_event_dead_letters`；`/events/health` 按 handler 聚合。死信堆积是「有功能已经悄悄坏了」的最早信号——业务面上一切正常，只有这个数会涨 | `::test_evt031_health_and_metrics_expose_backlog` |
| 全部 12 个既有 handler 重新分类 | 存证 4 个 → `critical=True, retry=False`；周期续期 → `retry=False`；通知/经验/分解/分析/IM/订阅推送 → `retry=True`，每处都写了理由 | 全量回归 452 tests |

## 已实现（V52 批次：协议版本化、单独同意与撤回的**实际后果**）

> 模块 spec：[26-legal-enforceability.md](26-legal-enforceability.md) 第 D 节（LAW-005/030/031/032）
>
> **检视结论**：V50 把 `AGREEMENT_VERSION` 加进了配置，**却从未被任何代码读过**——
> 这正是我在 AIO-003 批评过的「存了但从不使用」，只不过这次是我自己留下的。
> 一个存在但没人读的版本号，比没有更糟：它让人以为协议版本管理已经做了。
>
> 实现时的三个判断，每个都可以反着做，所以写下来：
> 1. **注册即同意三份文书，但敏感项不在此列**。注册页展示协议是业界标准，
>    强行让用户注册完再点一次「我同意」不增加任何法律效力；真正有意义的是
>    **版本变更后重新同意**。而证件/位置/支付必须由各自的动作单独同意——
>    PIPL 第二十九条明确禁止把敏感项塞进总协议一揽子勾选。
> 2. **只拦关键动作，不拦全站**。协议过期时若连协议本身、账号注销、数据导出
>    都打不开，用户会卡进「要同意才能用、要能用才看得到要同意什么」的死循环——
>    那是把合规做成了拒绝服务。
> 3. **撤回必须有实际后果**。只写一条 revoked 记录、依赖它的数据原样留着、
>    能力照样能用，那这个按钮就是骗人的。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **LAW-030 三份文书版本化 + 变更重新同意** | `legal/consent.py::UserConsent`（只增不改的同意流水）、`current_version()` 读 `AGREEMENT_VERSION`、`require_current_agreement()` 挂在发布/报名/托管/提现四个关键动作上 | `tests/test_consent_and_rights.py::test_law044_agreement_update_blocks_key_actions` |
| **LAW-044 合规不得变成拒绝服务** | 协议过期时读协议、看资料、浏览广场、导出数据一律放行 | 同上 `::test_law044_reading_agreements_is_never_blocked` |
| **LAW-031 敏感项单独同意** | `SENSITIVE_SCOPES`（证件/位置/支付）各自独立；`consent.ensure()` 在实名、绑收款账户、到场打卡三处随动作记录同意 | 同上 `::test_law031_sensitive_consent_granted_by_the_action_that_needs_it`、`::test_law031_checkin_grants_location_consent` |
| **LAW-031 撤回后不得「自动重新同意」** | `ensure()` 区分「从未同意」与「已撤回」：前者随动作记录，后者硬拒，必须显式重新授权 | 同上 `::test_law032_revoked_consent_is_not_silently_reacquired` |
| **LAW-032 撤回的实际后果** | 撤回支付 → 解绑收款账户；撤回证件 → `require_verified` 停用接单与资金操作；撤回位置 → 清空已结束任务坐标、拒绝后续打卡 | 同上 `::test_law032_revoking_payment_unbinds_payout_account`、`::test_law032_revoking_identity_disables_verified_only_actions` |
| **LAW-032 删除权 vs 举证需要** | 进行中/纠纷中任务的打卡坐标**依法保留**（争议解决所必需，PIPL 删除权例外），其余立即清空——全删会让「你根本没到场」变成各说各话 | 同上 `::test_law032_revoking_location_keeps_live_task_checkins_as_evidence` |
| **LAW-032 数据主体权利入口** | `status()` 返回 rights 映射（查询/导出/更正/删除/撤回），Web 端 `Profile.tsx::PrivacyConsents` 渲染成可点的界面；`/users/me/export` 补上同意历史 | 同上 `::test_law032_rights_map_points_at_endpoints_that_exist`（逐个打过去看通不通）、`::test_law032_export_includes_consent_history` |
| **LAW-032 撤回前先告知后果** | `revocation_effect` 随状态一起返回，前端在确认框里先展示再执行 | 同上 `::test_revocation_effect_is_disclosed_before_revoking` |
| **LAW-005/045 未成年人拦截** | 实名时从证件号派生出生日期判断成年，**只落 `is_adult` 标记不存明文**；15 位老证件等解析不了的一律放行（拦截基于确证事实，不基于解析失败） | 同上 `::test_law045_minor_cannot_complete_verification`、`::test_law045_unparsable_id_is_not_blocked` |
| 实现中修正的自身缺陷 | 支付同意校验原本插在 `no_payout_account` 之前，把「你还没绑卡」这个能照做的提示换成了「请先同意支付信息处理」——一句让人去点空设置页的话。合规校验只管「撤回后必须停」，「从未同意」交给更具体的业务校验 | 同上 `::test_law031_never_consented_gets_the_actionable_error_not_a_consent_lecture` |

## 已实现（V51 批次：沙箱桩——让预留的接口真的跑得通）

> 模块 spec：[27-sandbox-stubs.md](27-sandbox-stubs.md)
>
> **检视结论**：V43/V49/V50 依次抽出了接口，但每个 kind **只发布了退化实现**——
> `CustodyLedger` 遇到 `MockPaymentProvider`（没有 `split_settle`）直接抛错，
> **整条存管路径零测试覆盖**；`qualified` 签名与 `backed` 存证也只在测试里
> 临时定义一个类，没有随代码发布。
> **接口预留了却跑不通，等于没预留**：换供应商那天才第一次执行到这些分支，
> 而那正是最不能出错的时刻。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **STUB-002 补桩不削弱拦截（最容易做错的地方）** | 生产判定从「等于 mock 名」改为「属于该 kind 的**非生产实现集合**」，sandbox 与 mock 一视同仁地被拒；签名/存证供应商也纳入自检 | `tests/test_sandbox_stubs.py::test_sandbox_providers_still_rejected_in_production` |
| **STUB-010/011/012 存管形态支付** | `SandboxCustodyPayment` + 独立的**存管账簿**：付款进存管专户而非平台账户，平台只能通过 `split_settle` 下达分账指令——用代码证明「钱不经过平台」这个形态真的走得通 | 同上（`test_full_loop_runs_in_custody_mode` 断言专户余额与分账落账；`test_money_invariants_hold_in_custody_mode`） |
| **STUB-013/052 失败注入** | `PLATFORM_SANDBOX_FAIL_MODE` 让分账/打款/签名/存证按操作名注入失败——**失败路径比成功路径更需要提前跑过** | 同上（分账失败整体回滚、钱没动、失败指令不入库；注入按操作名精确生效不误伤） |
| **STUB-020/022/053 可靠签名沙箱** | `SandboxCaSignature` 返回签名 + 证书 + 时间戳令牌，`reliability=qualified`，且 `verify` **真的能验**——只返回固定值的桩没有意义 | 同上（证明力声明升级、篡改仍被检出、换人/换文本/伪造签名三种情况都验不过） |
| **STUB-021/054 第三方存证沙箱** | `SandboxNotary` 返回 `backed=True` 与可质证编号，覆盖区间变为全量 | 同上 |
| **STUB-030/056 eKYC 三态** | 按证件号尾号触发 `passed/failed/manual`，让转人工分支可测 | 同上 |
| **STUB-031/055 严格短信路径** | `SandboxSmsProvider` 不回显验证码，覆盖 mock 固定码所绕过的「必须先请求验证码、有效期、尝试次数上限」 | 同上（不先请求就注册失败、错码被拒、正确码通过） |
| **STUB-032/033 审核与存储** | 审核三态（有媒体一律转人工，与真实供应商的保守取向一致）；存储签发直传 URL 形态 | 同上 |
| **STUB-003 供应商三态** | `provider_grade()` 区分 production / sandbox / mock，后台面板与自检共用 | 同上 |
| **STUB-040/041 合规态自检脚本** | `scripts/sandbox_check.py` 装上全套沙箱桩跑完整闭环（22 项断言），**同时是对接验收脚本**：真实供应商实现同一组方法后换名再跑，全绿即契约对齐；已并入 CI 与既有 mock 冒烟并行 | CI 作业 `sandbox-compliance` |
| **VND-002 补齐**（实现中发现的缺口） | `VendorError` 此前**没有 API 边界处理器**——存管分账失败会变成未处理异常 500，既丢语义又让调用方分不清「重试有用」和「重试没用」。补统一处理器：502（可重试）/ 400（明确拒绝） | 同上（失败注入用例依赖它返回 4xx/5xx 而非崩溃） |
| `STORAGE_PROVIDER` 配置项补齐 | storage 已注册但没有配置键，无法切换 | 同上 |

## 已实现（V50 批次：法律效力——诚实标注证明力边界）

> 模块 spec：[26-legal-enforceability.md](26-legal-enforceability.md)
>
> **前提澄清**：「智能合约」在中国法下不是独立法律主体，是合同的自动履行工具。
> 出纠纷靠的是三样东西：有效成立的合同、经得起质证的证据、可执行的争议解决条款。
> 本批次把第 2 项做扎实，把第 1、3 项的接口与用词做对；
> ⚖️ 律师定稿的文本与 CA/存证签约仍需用户提供。

| Spec 功能点 | 检视发现的问题 → 实现 | 测试 |
|---|---|---|
| **LAW-001/002 签署绑定合同全文** | 原「双签」只是数据库里两个布尔位，**不构成《电子签名法》第十三条的可靠电子签名**——对方一句「不是我签的那份」平台拿不出任何反驳。新增 `ContractSignature`：绑定**签署那一刻的合同全文哈希** + 签名值，事后改条款则校验失败（篡改自证）；签署事件一并入存证链 | `tests/test_legal_enforceability.py::test_tampering_terms_after_signing_is_self_evident` |
| **LAW-013 诚实标注证明力（本批次的核心态度）** | `PlatformWitnessSignature` 明确标注 `reliability="platform_witness"`：能证明「平台记录到该次同意且文本未改」，**不能独立证明签名人身份**；`LocalNotary` 明确返回 `backed=False`。**冒充证明力比没有证明力更糟**——上了法庭才发现顶不住就晚了 | 同上（`test_platform_witness_signature_does_not_claim_to_be_qualified`、`test_local_notary_declares_no_third_party_backing`） |
| **LAW-001/010 供应商可替换** | `SignatureProvider`（接 CA 后升级为 `qualified`）与 `NotaryProvider`（接司法链后 `backed=True`），证明力声明随之如实升级 | 同上（`test_qualified_provider_upgrades_the_notice`、`test_third_party_backed_notary_reported`） |
| **LAW-003 签署前置实名** | 签名要指向一个可确认的人。守卫独立成立，不依赖「上游报名时拦过一次」——实名可能被风控撤销 | 同上 |
| **LAW-004 版本化签署（实现中修正了 spec）** | spec 原写「变更单生效即触发对新版本的双签」；实现时判断这是**多余的仪式**——变更单本身就是要约+承诺，再走一次签署不增加任何法律效力。改为：接受变更单时直接为双方各记一条新版本签名，绑定变更后条款。旧版本签名对不上当前条款是**正常的**，不判为篡改 | 同上（`test_change_order_creates_new_version_signatures`） |
| **LAW-011 第三方存证锚定** | `AnchorReceipt` + `/anchors/jobs/notarize`（已排入 cron）：定期把链 head 交存证机构，增量覆盖不重复出回执；`/anchors/coverage` 显示哪些区间有背书 | 同上（`test_notarize_is_incremental`） |
| **LAW-012/014 证据包升级** | 原导出只有纠纷那几个字段。现覆盖完整时间线：合同全文与签署校验、分账指令、执行留痕与图片凭证、双方陈述与平台处理决定，附哈希链验证报告与存证回执，并**写明未被第三方覆盖的部分** | 同上（`test_evidence_package_covers_full_timeline`、`test_evidence_package_states_its_limits`） |
| **LAW-021 用词切分** | 平台内部处理是「依当事人事先约定作出的合同履行调整」，**不是法律意义上的仲裁裁决**，没有强制执行力。全站文案统一改为「平台处理决定」；用扫描测试锁住——只有「不是法律意义上的仲裁裁决」这一句允许出现该词 | 同上（`test_platform_decision_is_not_called_arbitration_award` 扫描全部源码） |
| **LAW-020/022 争议解决与升级路径** | 合约条款与法律问答统一表述：先经平台处理 → 不服可依条款提请**约定的仲裁机构**或向法院起诉，平台提供证据包 | 同上 |
| SDK 同步：`contractSignatures`、`anchorCoverage` + 类型 | `packages/core/src/{client,types}.ts` | web 构建通过 |

**仍必须由用户提供**（⚖️）：律师定稿的用户协议/隐私政策/合同模板、
与真实仲裁机构或调解组织的合作及有效的争议解决条款、第三方 CA 与司法存证签约、
劳务关系定性与保险方案。

## 已实现（V49 批次：资金合规——把「不能这样上线」变成机器闸门）

> 模块 spec：[25-financial-compliance.md](25-financial-compliance.md)
>
> ⚠️ **本批次不能让当前形态变得合规**。平台自建账本托管资金 = 资金池 + 二清，
> 这是资金的**法律路径**问题，代码解决不了；能做的是：把接口留好、
> 把红线做成硬拦截、把资金流做成可审计，并让**未接存管的生产环境根本起不来**。

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| **FIN-050/051 `LedgerBackend` 抽象** | `InternalLedger`（平台内账本，仅限开发/演示）与 `CustodyLedger`（持牌存管，钱不经过平台）。切换只改 `PLATFORM_LEDGER_BACKEND` | `tests/test_financial_compliance.py::test_custody_backend_requires_provider_support`（切 custody 但供应商没实现分账 → 明确报错，**不静默退回内部账本**） |
| **FIN-052 生产拒绝启动（本批次最重要的一条）** | `ENV=prod` 且后端为 internal → `startup_check` 抛错，且拦截理由写明「涉嫌资金池与二清（无证从事支付结算）」。配置疏忽和业务违规要说清楚是哪一种 | 同上（`test_production_refuses_internal_ledger` 断言消息含「资金池」「二清」） |
| **FIN-053 沙箱标识** | `/version` 返回 `sandbox` 与 `ledger_backend`，避免有人误以为这是真实资金 | 同上 |
| **FIN-010/011/012/013 分账指令模型** | `SettlementOrder` + `SettlementSplit`：放款/分期/退款/取消补偿/裁决执行五类路径全部产出一条指令；平台佣金作为**独立收款方**出现，与用户资金天然隔离，不靠代码自律 | 同上（放款两方拆分、退款、裁决三方拆分、分期逐期累计） |
| **FIN-060 守恒并入日终对账** | splits 之和必须等于总额；存管模式下无流水号视为异常。并入 `risk.reconcile`，不守恒即报 | 同上（`test_broken_settlement_is_detected`：人为改一分钱，对账必须报出来而不是悄悄放过） |
| **FIN-042 资金流向可审计** | `GET /contracts/{id}/settlements`：谁付的 → 指令 → 谁收的，当事人与管理员可见 | 同上（含越权拒绝） |
| **FIN-020 分利模式白名单** | `pricing` 只允许 `fixed/milestone/hourly/bidding`——**收益分成与股权对价一律拒绝** | 同上（`test_pricing_whitelist_rejects_revenue_share`） |
| **FIN-021 金融话术拦截** | 独立词表（分红/股权/原始股/期权/保本/年化/众筹/代币…），与普通违禁词**刻意分开**：这些词的问题是把劳务合同变成金融产品，需要独立的拒绝理由。「投资」只在与回报承诺连用时才拦，避免误杀「投资人对接」 | 同上（5 类话术被拦且理由说明为什么；3 类正常任务不被误杀；风控过严和过松一样是失败） |
| **FIN-022 合约条款定性** | 条款写入「承揽/服务合同，报酬系劳务对价，不构成投资/入股/合伙/保本安排，不成立劳动关系」——**定性写进当事人合意才有对抗力**，只写在平台规则里没用 | 同上 |
| SDK 同步：`contractSettlements` + `SettlementOrderView` | `packages/core/src/{client,types}.ts` | web 构建通过 |

**仍必须由用户提供**（⚖️ 代码无法替代）：持牌机构的担保交易/资金存管产品与签约、
平台经营资质、税务代扣与发票方案、反洗钱制度与报送通道。

## 已实现（V48 批次：AI 编排闭环——从「数状态」到「看成果」）

> 模块 spec：[24-ai-orchestration.md](24-ai-orchestration.md)（已按代码检视结论重写）

本批次的四项修改都来自对 `orchestrator/service.py` 的逐行复查，
每一项对应一个让循环**闭不上**的具体缺陷：

| Spec 功能点 | 检视发现的缺陷 → 实现 | 测试 |
|---|---|---|
| **AIO-024/025/026 预算语义拆分（先修地基）** | `_dispatch_step` 在**发布任务时**就 `spent_cents += budget` 且流单后**从不退还**——字段注释写「已承诺」，行为却是「累计尝试」。两个语义混在一起的后果是取消的任务永久占着额度，首轮全部流单后 agent 就被一堆**已经不存在的占用**饿死。拆成 `committed_cents`（占用，取消即释放）与 `spent_cents`（实付，完成放款才计）。护栏改为 `spent + committed + 本步 <= cap`——**已付出去的钱不可逆，必须占额度**，否则「完成→评审不达标→重发」会让实际支出翻倍 | `test_orchestrator.py::test_cancelled_step_releases_budget_and_remedy_dispatches`（取消后能继续）、`::test_real_overspend_still_blocks`（真超支仍挂起） |
| **AIO-001/002/003 验收要点显式化** | `acceptance_criteria` 字段**存了但从不使用**，执行者不知道怎样算做完 → 规划为每步产出验收要点，写入任务描述并随合约条款留痕；模板引擎路径同样有要点，不依赖 Key | `test_orchestrator_review.py::test_acceptance_criteria_reach_the_worker` |
| **AIO-010/011/013 成果评审网关** | `evaluate()` 只数 `task.status == "completed"`——交一句「做完了」和交合格产出**没有区别** → `ReviewGateway` 抽象；`RuleReview` **基于可观测事实真打分**（留痕条数、图片凭证、打卡、交付说明、驳回次数），不是占位符；`ModelReview` 走 JSON Schema 强约束，异常降级；`StepReview` 留痕（模型、提示词版本、脱敏输入摘要、耗时） | 同上（`test_rule_review_distinguishes_evidence_quality` 证明有凭证的交付得分更高、`test_review_is_recorded_with_provenance`、`test_model_review_falls_back_on_bad_output`） |
| **AIO-012 模型永远不能单独动钱（第一性约束）** | `pass` 只作建议，放款仍由发布方确认；`revise`/`fail` 生成整改要点与人工复核，**零资金动作**。模型会错，而资金操作不可逆——AI 只做「谁该看一眼」的分诊 | 同上（`test_review_verdict_never_moves_money`：判 fail 时双方钱包与合约状态逐字段不变） |
| **AIO-020/047 质量闸门** | 达标条件从「全部完成」改为「全部完成**且**均分过线」，低分步转整改而非直接算完成；新增 `quality_pct` | 同上（`test_low_quality_does_not_count_as_success`、`test_quality_pct_reported`） |
| **AIO-021 修复步带整改要点** | `_make_remedy_steps` 是**同规格重发**（`args=dict(s.args)`）——同样的标题、预算、技能要求再发一次，凭什么这次会成功 → 把上一轮 `missing` 写进任务描述；连续两轮不达标则**上浮预算重新招募** | 同上（`test_remedy_carries_fixup_notes`、`test_repeated_failure_boosts_budget`） |
| **AIO-022 修复步幂等改用外键** | 原先靠标题字符串匹配 `title == f"[修复] {s.title}"`，脆且多轮后标题变成 `[修复] [修复] [修复] X` → 改用 `parent_step_id`，标题保持稳定，轮次由 `attempt` 表达 | 同上（`test_remedy_is_idempotent_by_parent_fk`） |
| **AIO-023/049 迭代时间线** | `MissionEvent` 记录每轮「做了什么 / 现在怎样 / 下一步」——**agent 必须可解释，否则没人敢授权它自动花钱** | 同上（`test_timeline_is_human_readable`） |
| **AIO-034/043 模型调用配额** | Mission 级上限，达上限降级规则评审，不静默烧 API 账单 | 同上（`test_model_call_quota_degrades_to_rule`） |
| **AIO-033/044 送模型脱敏** | 证据只取结构化事实、不取聊天记录；留痕摘要复用日志同一套 `redact` | 同上 |
| **闭环验收** | 「首轮全部流单 → 整改 → 真正 succeeded」——此前会因预算被虚耗卡在 `blocked` | `test_full_loop_recovers_from_first_round_failure` |
| SDK 同步：`committed_cents`/`quality_pct`/`timeline`/`stepReviews` | `packages/core/src/{client,types}.ts` | web 构建通过 |

## 已实现（V47 批次：抗攻击硬化——从「按账号限流」到「换号也挡得住」）

> 新增模块 spec：[23-network-security.md](23-network-security.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SEC-011 **客户端 IP 解析（本批次最关键的一小段代码）**：常见错误是取 `X-Forwarded-For` 第一个 IP——那是客户端可伪造的，攻击者每次带一个不同的假 IP 就能让按 IP 的限流与封禁彻底失效。改为只信任反代注入的**最后一跳**（`TRUSTED_PROXY_HOPS`），XFF 比预期短则退回 socket 对端 | `core/clientip.py` | `tests/test_security_hardening.py`（伪造 XFF 绕不过；取右侧跳不取左侧） |
| SEC-011 **账号 + IP 双维度限流**：原实现只按手机号限，攻击者每次换号计数器永远是 1，批量注册完全不受影响。所有认证类端点（注册/登录/短信码/改密/换绑/重置）改走 `guard()`，任一维度超限即拒 | `core/guard.py::guard`、`account/router.py` | 同上（换号不换 IP 被拦；同号高频仍被拦） |
| SEC-012 **全局写限流兜底**：此前限流是「在每个敏感端点手写一行 check()」，只有 7 处，新端点默认裸奔。改为中间件按 IP 限所有写操作——**新端点默认受保护**；读请求与探针不受影响 | `core/guard.py::WriteRateLimitMiddleware` | 同上（未单独加限流的端点也被兜住；GET 不误杀） |
| SEC-020/023 认证失败自动封禁：窗口内失败达阈值临时封禁 IP，封禁期内正确密码也拒；**成功登录清零计数**（偶发手滑不该累积成封禁）；管理端安全看板与**人工解封**（误封公司出口 IP 会挡住一整栋楼） | `core/guard.py::{note_auth_failure,ban_remaining,unban}`、`admin/router.py` | 同上 |
| SEC-002 安全响应头：nosniff / frame DENY / CSP（`frame-ancestors 'none'`）/ Referrer-Policy / Permissions-Policy；**HSTS 只在 prod 下发**（开发环境发了会把本地浏览器锁死在 HTTPS） | `core/headers.py` | 同上 |
| SEC-003 生产关闭 API 文档：`/docs`、`/redoc`、`/openapi.json` 在 `ENV=prod` 且未显式开启时不挂载——把全部端点与模型结构送给攻击者是没必要的慷慨 | `main.py` | 同上（dev 下仍可访问） |
| SEC-033 上传响应加固：读取端点补 `nosniff` + `Content-Disposition` + `CSP: default-src 'none'; sandbox`，即便有人构造出「既是合法图片又是合法脚本」的文件也无法在本源执行 | `files/router.py` | 同上 |
| SEC-001/004/010/013 生产 Nginx：强制 TLS（≥1.2、HSTS、OCSP stapling）、三档 IP 令牌桶（普通/写/认证，认证类最严）、资金类端点单独收紧、`limit_conn` 与超时防慢速攻击、`/metrics` `/jobz` 仅内网、SW 不缓存 | `deploy/{nginx.prod.conf,proxy_common.conf,docker-compose.prod.yml}` | 配置随栈交付；应用侧行为由上述用例覆盖 |
| SEC-030/053 生产自检扩展：CORS 为 `*`、暴露 API 文档、`TRUSTED_PROXY_HOPS` 未设（反代后取不到真实 IP，限流全失效）→ **拒绝启动**；`up.sh` 增加缺 TLS 证书的拦截 | `vendors/registry.py::startup_check`、`deploy/up.sh` | 同上 |

## 已实现（V46 批次：增长、运营与市场——把运营手册落成功能）

> 新增模块 spec：[22-growth-ops.md](22-growth-ops.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| GRW-001/005 券模板：定额/比例二选一，**比例券必须带封顶**（没封顶的比例券遇大额单会烧光预算）；发放/核销/成本报表；可暂停发放且不追溯作废已领权益 | `growth/{models,service}.py`、`growth/router.py::{create_coupon,coupon_report,pause_coupon}` | `tests/test_growth.py` |
| GRW-002 领取与核销：一人限领、一单一券（`UniqueConstraint(contract_id)` DB 层兜底）、满减门槛、类目限制、有效期；**合约取消 → 券退回可再用且补贴款退回平台** | `growth/service.py::{claim,redeem,release_on_cancel}` + `contract/service.py::_release_coupon` | 同上 |
| GRW-003 **补贴资金口径（本批次最关键）**：补贴不凭空产生，一律「平台账户 → 用户可用余额」走既有账本（`subsidy_out/in` 科目）；平台余额不足即核销失败绝不透支；新增补贴池注资 `platform_topup`（冷启动时平台还没佣金收入）。**同步扩展资金第 4 不变量**为「平台可用 == Σ佣金 + Σ注资 - Σ结算 + Σ补贴净额 + Σ调整净额」——不改口径的话每发一张券日终对账就误报一次 | `wallet/service.py::{transfer(kind=),fund_platform}`、`risk/service.py::reconcile` | 同上（每个用例结尾都断言四不变量成立） |
| GRW-004 反刷：未实名不得领券（否则批量注册即可薅）、限量与限领 | `growth/service.py::claim` | 同上 |
| GRW-010~014 邀请裂变：**完成首单才发现金奖励**（注册即奖是刷号的邀请函）；一人一次（`invitee_id` 唯一）；反作弊（同收款账户 / 同实名 / 互为邀请 → blocked 转人工不发钱）；邀请战绩页 | `growth/service.py::{grant_referral,_fraud_reason,referral_stats}`、`analytics/service.py` | 同上 |
| GRW-060 合规红线：**奖励仅一级**，邀请人的邀请人不获任何奖励（代码层面就不去追溯上级）；战绩接口显式返回 `levels: 1` | 同上 | 同上（A→B→C 三层，C 成单时 A 得 0） |
| GRW-020 新人任务清单（完善资料/实名/技能/首发/首报/首单）与进度 | `growth/service.py::newcomer_progress` | 同上 |
| GRW-022/023 供需健康度：按城市×类目统计发布数/接单人数/成单率，标出 `supply`（有需求没人接）与 `demand`（有人没活干）两类缺口；发布页供给不足提示 | `growth/service.py::{market_health,supply_hint_text}` | 同上 |
| GRW-030 活动预算硬顶：`spent_cents` 随核销累加，超顶自动停投——没有硬顶的补贴活动是运营事故的标准形态 | `growth/models.py::Campaign` + `service._check_campaign` | 同上（预算 30 元、券 20 元 → 第二张即被拒） |
| GRW-052 北极星指标：成单数与成单 GMV；次级看新用户首单转化与纠纷率 | `growth/service.py::north_star` | 同上 |
| Web 优惠页（新人任务进度 / 领券 / 我的券 / 邀请战绩，含「仅一级」规则说明）+ SDK 同步 | `web/src/pages/Rewards.tsx`、`packages/core/src/{client,types}.ts` | web 构建通过 |

## 已实现（V45 批次：移动端与 PWA——让手机用户真的能用）

> 新增模块 spec：[21-mobile-pwa.md](21-mobile-pwa.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| MOB-001/003/004 响应式（≤640 手机 / ≤1024 平板 / >1024 桌面）：列表转竖排卡片、表单与按钮满宽、表格横向滚动（**绝不让 body 出横向滚动条**）、触控目标 ≥44px、输入框 ≥16px（防 iOS 聚焦缩放）、`viewport-fit=cover` + `env(safe-area-inset-*)` 适配刘海与手势条 | `web/src/styles.css`、`web/index.html` | `web/src/mobile.test.tsx` |
| MOB-002 底部 Tab 导航（广场/发布/消息/我的），手机显示桌面隐藏；消息 Tab 未读红点复用 IM-010 全局未读接口，未读数拿不到不影响导航可用 | `web/src/TabBar.tsx`、`App.tsx` | 同上（四入口渲染、红点数字） |
| MOB-010 `manifest.webmanifest`：standalone、主题色、**maskable 图标**（少了它安卓自适应图标会被裁掉一圈）、快捷方式；apple-touch-icon 与 iOS meta | `web/public/{manifest.webmanifest,icon.svg,icon-maskable.svg}` | 同上 |
| MOB-011/012 Service Worker：外壳预缓存 + stale-while-revalidate；**`/api/` 一律不缓存不兜底**——任务状态/合约状态/钱包余额读到陈旧值会让用户基于错误信息决定付钱，宁可报错不可撒谎；断网落离线页 | `web/public/{sw.js,offline.html}` | 同上（预缓存清单不含 API、离线页在册） |
| MOB-013/014 新版本提示（`SKIP_WAITING` + 刷新，避免旧外壳打新接口）；安装引导可关闭且**记住选择**，隐私模式下 localStorage 抛异常也安静降级 | `web/src/pwa.ts`、`App.tsx` | 同上 |
| MOB-020 定位「附近任务」（既有能力，拒绝授权时降级为全部任务） | `web/src/pages/Square.tsx` | 既有用例 |
| MOB-021 拍照/相册取证：客户端压缩（长边 1280 / JPEG 0.8）后上传——**压缩是必需而非优化**，手机直出 3~8MB 既超服务端上限也让弱网执行者传不上去，而凭证传不上去等于没有证据；进度留痕可附图，纠纷时作为证据 | `web/src/PhotoPicker.tsx`、`pages/TaskDetail.tsx`、`task/{models,router}.py` | `server/tests/test_uploads.py` |
| VND-031 存储供应商抽象 + 上传端点：类型白名单 + 大小上限 + **魔数校验**（只信 Content-Type 等于让上传方自证清白）+ 内容寻址去重 + 登录与限流（否则等于开了免费图床）+ 读取端点禁路径穿越；进度图只接受本平台相对路径（外链不可信且泄露用户 IP） | `app/vendors/storage.py`、`app/modules/files/router.py` | 同上（12 例，多数是拒绝路径） |
| MOB-031/032/033 Expo 配置：bundle id、scheme `taskplat`、Universal Link / App Links、相机与相册权限的中文用途说明；提审清单列出账号注销/举报/拉黑/协议四个**审核必查项**及其后端接口 | `app/app.json`、`app/STORE_CHECKLIST.md` | — （发版需开发者账号） |
| SDK 同步：`uploadImage`、`addProgress` 支持 images | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V44 批次：生产部署、迁移与可观测）

> 新增模块 spec：[20-deployment.md](20-deployment.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| DEP-001/002/003 生产栈 compose（Postgres + Redis + 可扩副本 api + **固定单副本 worker** + Nginx）；`deploy/.env.example` 标注全部「必须修改」项；`deploy/up.sh` **先自检再启动**（弱密钥/默认 token/CORS 为 `*`/四个 mock 供应商全部拦下）；镜像非 root 运行 | `deploy/{docker-compose.prod.yml,.env.example,up.sh}`、`server/Dockerfile` | 自检逻辑与 `startup_check` 同源，见 VND-042 用例 |
| DEP-010/011/012 探针：`/healthz` 存活（不查依赖）、`/readyz` 就绪（DB + 限流后端 + **迁移版本**，不满足 503）、`/version` 构建信息 | `main.py` | `tests/test_deployment.py` |
| DEP-020/021/022 **Alembic 成为生产唯一建表路径**：`init_db` 在 `ENV=prod` 下直接拒绝 `create_all`（多副本并发建表会互相踩）；迁移由一次性 `migrate` 容器执行；库版本与代码 head 不一致则 `/readyz` 不就绪 | `migrations/`、`alembic.ini`、`core/db.py::{init_db,migration_status}` | 同上 + **迁移与模型不漂移**用例（两条建表路径的表/列集合必须一致）+ CI `alembic check` |
| DEP-030/031/032 备份与恢复：`backup.sh`（pg_dump + **存证链 head 单独快照**——只备份库的话，被篡改后再备份就没有独立证据了）；`restore.sh` 导入后**强制跑资金四不变量 + 存证链校验**，不过就明确报失败，不给「大概好了」的错觉 | `deploy/{backup.sh,restore.sh}` | 校验逻辑复用既有 `reconcile` / `verify_chain` 用例 |
| DEP-040/041 结构化 JSON 日志 + `request_id` 贯穿（入站生成或**透传**，随响应头返回）；日志**脱敏**手机号/证件号/银行卡——出事时不能因为日志本身再泄一次 | `core/observability.py` | 同上（三类敏感串各一例、formatter 带 request_id） |
| DEP-042 `/metrics` Prometheus：请求量/延迟直方图 + **资金关键计数**（托管中、待提现、未结纠纷）；用路由模板而非真实路径，避免任务 id 打爆指标基数；与 cron 同一把令牌保护，不对公网裸奔 | 同上 + `main.py` | 同上（含基数用例、鉴权用例） |
| DEP-050/051 worker 驱动全部 job（周期按「延迟一个周期的业务代价」定）；`JobLock.last_success_at` 记录 job 健康，`/jobz` 暴露——job「静默不跑」比报错更危险 | `scripts/cron.py`、`core/locks.py::{_note_job_result,job_health}` | 同上 + **反查路由表**用例：新增 job 端点却忘了排期直接测试失败 |
| DEP-060 冒烟脚本：对已启动实例跑真实 HTTP 主闭环（注册→实名→充值→发布→报名→选人→双签→托管→交付→验收→核对分账→**托管清零**），CI 中执行 | `scripts/smoke.py`、`.github/workflows/ci.yml` | CI 作业 `boot-smoke` |

## 已实现（V43 批次：外部供应商接入抽象层——把「模拟」换成「可换」）

> 新增模块 spec：[19-vendor-integration.md](19-vendor-integration.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| VND-001/041/042 注册表 `get_provider(kind)` + 后台健康面板 `/admin/vendors`（当前实现/是否模拟/熔断/近 24h 成功率）+ **生产启动自检**：`PLATFORM_ENV=prod` 下 P0 能力仍是模拟实现、弱密钥、SQLite 一律拒绝启动（把上线前必须完成的对接变成硬拦截，而不是没人看的日志） | `app/vendors/registry.py`、`admin/router.py`、`main.py` | `tests/test_vendor_integration.py` |
| VND-002 错误收敛 `VendorError(code, message, retryable)` → 502（可重试）/ 400（明确拒绝），**不泄露供应商原始报文** | `vendors/base.py` | 同上 |
| VND-003 调用留痕 `VendorCall`（kind/provider/operation/幂等键/**脱敏摘要**/状态/耗时/外部单号）——对账与客诉排查的唯一依据 | `vendors/models.py::VendorCall` | 同上（手机号与验证码不进摘要） |
| VND-004 幂等：会花钱/会发送的操作带幂等键，重复调用回放首次结果，**不再打供应商** | `vendors/base.py::call` | 同上（三次调用只打一次） |
| VND-005 熔断：连续失败达阈值进入冷却，冷却期快速失败 | 同上 | 同上 |
| VND-010/011 **充值改两阶段**（修复真实支付下的致命结构）：此前「调用即加余额」意味着接真实通道后用户下单不付款也能拿到钱 → `PaymentOrder` pending → 供应商确认 → 才入账。模拟通道即时确认，开发体验与既有测试不变 | `vendors/{payment,payment_service}.py`、`wallet/router.py` | 同上（订单落库、外部单号可对账） |
| VND-012 回调验签 + 回调幂等 + 金额校验：伪造签名一律拒绝（不看金额不查订单）；同一订单重放只入账一次；回调金额与订单不符标记 `mismatch` 挂起人工，且**标记落在独立事务**里（否则会跟着 400 一起回滚，运营再也看不到） | `vendors/payment_service.py::{handle_callback,confirm_topup,_flag_mismatch}` | 同上（三条独立用例） |
| VND-013 提现打款走 `create_payout` 并落 `payout_ref`；供应商失败整体回滚——宁可提现失败重来，也不能「账扣了钱没打出去」 | `wallet/service.py::_send_payout` | 既有提现用例 |
| VND-020/021 短信：`/auth/send-code` 端点（限流同级，防被当短信轰炸机）；验证码服务端生成、**只存哈希**（手机号加盐）、有效期 10 分钟、尝试次数上限 5 次；模拟通道回显 `dev_code`，真实通道永不回显 | `vendors/{sms,sms_service}.py`、`account/router.py` | 同上（哈希不含明文、限流生效） |
| VND-022/023 实名走 `KycProvider`；**证件号不落明文**，只存不可逆摘要 + 掩码串；同一证件号不得绑定多账号（一人多号是补贴套利第一步） | `vendors/kyc.py`、`account/{models,router}.py` | 同上（摘要脱敏、重复证件号 409） |
| VND-030 内容机审改走 `ModerationProvider`（本地词表为缺省实现，行为不变）；本地实现看不了图/视频时明确返回 `review` 转人工，而不是假装通过 | `vendors/moderation.py`、`task/service.py::machine_review` | 同上（违禁词仍被拦） |
| SDK 同步：`sendSmsCode`、`topup` 返回两阶段结果类型 | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V42 批次：并发与生产化硬化——从「单进程正确」到「多副本正确」）

> 新增模块 spec：[18-concurrency.md](18-concurrency.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CONC-001/002 Postgres 支持与连接池参数化（`pool_size`/`max_overflow`/`pool_recycle`/`pool_pre_ping`），SQLite 分支自动跳过池参数；切库只改 `PLATFORM_DATABASE_URL`，业务代码零改动 | `core/db.py::_make_engine` + `core/config.py` | 全量既有测试（同一套代码跑 SQLite） |
| CONC-003 SQLite WAL + `busy_timeout` + 外键约束 PRAGMA：本地并发写不再直接报 `database is locked` | `core/db.py` connect 事件 | 并发用例（多线程打同一端点不报锁错） |
| CONC-004 方言探测 `supports_row_lock()`：Postgres/MySQL 启用真实行锁，SQLite 自动降级 | `core/db.py` | 同上 |
| CONC-010/011/012 **资金写路径行锁**（最关键缺口）：多副本下两进程可同时读到 `funded` 各自放款 → `lock_contract`/`lock_wallets` 取 `SELECT ... FOR UPDATE`；多钱包按 `user_id` **升序**加锁杜绝死锁；接入 fund/release/release_milestone/cancel/execute_verdict/accept_change/withdraw/decide_withdraw/settle_platform/transfer | `core/locks.py` + `contract/service.py` + `wallet/service.py` | `tests/test_conc_hardening.py`（并发验收只放款一次、并发托管只扣一次、并发提现不透支） |
| CONC-013 **乐观锁兜底**：`Contract.lock_version` / `WalletAccount.lock_version` 走 SQLAlchemy `version_id_col`，并发 UPDATE 第二个提交 `StaleDataError`；API 边界统一翻译为 `409 concurrent_modification` 而非 500。与业务版本号 `Contract.version`（条款版本，对外展示）**刻意分离** | `contract/models.py`、`wallet/models.py`、`main.py` 异常处理器 | 同上（丢失更新被拒、409 语义） |
| CONC-020/021/022 分布式限流：`RateLimiter` 协议 + `MemoryRateLimiter`（现状）+ `RedisRateLimiter`（`INCR`+`EXPIRE` 原子窗口）；配 `PLATFORM_REDIS_URL` 自动切换；**Redis 故障连续达阈值即冷却降级为内存**并在探针中可见——限流是防滥用手段，不该拖垮登录 | `core/ratelimit.py` | 同上（降级后仍真限流，不是无脑放行） |
| CONC-040/041 定时任务单实例锁：`JobLock` 表（job_name 主键=天然唯一约束）+ `job_slot()` FastAPI 依赖，**执行完即释放**（串行调用永远可用），崩溃时靠 `expires_at` TTL 抢占，不会永久停摆；接入全部 8 个 cron 端点 | `core/models_infra.py`、`core/locks.py`、各模块 `jobs/*` 路由 | 同上（持有/释放/TTL 抢占/端点并发最多一个 200） |
| DEP-010/011/012 健康探针：`/healthz` 存活（不查依赖）、`/readyz` 就绪（DB 可读写 + 限流后端状态，不满足 503） | `main.py` | 同上 |

## 已实现（V41 批次：编排循环 Agent Harness——发任务给人 = 工具调用）

> 新增模块 spec：[17-orchestrator.md](17-orchestrator.md)

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| ORC-001/002 Mission/MissionStep 与一次 tick：plan（复用 AI 分解网关）→ observe（读任务真实状态为 observation）→ evaluate（完成度）→ dispatch（真实发布任务 = 调用「人」这个工具）→ 停机判定 | `orchestrator/{models,service,router}.py` | `tests/test_orchestrator.py` |
| ORC-003 编排状态机白名单（planning/running/blocked/succeeded/failed/cancelled），非法流转 409 | `service.transition` + `MISSION_TRANSITIONS` | 同上（结束后不可再 tick） |
| ORC-004 护栏（第一性要求）：预算硬上限超出即 `blocked` 挂起、规划预留金 `ORC_PLAN_RESERVE_BPS`（默认 30%）留给重试、迭代上限触顶 `failed`、人工停机并下架未成交挂单、所有权隔离、心跳 job 需令牌 | 同上 + `config.ORC_PLAN_RESERVE_BPS` | 同上（预算越界挂起、迭代上限放弃、cancel 下架、403 隔离） |
| ORC-005 失败步 → 自动生成修复步再分发（幂等去重）；原步标记 `superseded` 不计入分母，否则一次失败会让编排永远无法 100% | `service._make_remedy_steps` + `evaluate` | 同上（修复步完成后 succeeded） |
| SDK 同步：createMission/myMissions/getMission/tickMission/cancelMission + Mission 类型 | `packages/core/src/{client,types}.ts` | web 构建通过 |

## 已实现（V40 批次：纠纷答辩举证——两造兼听）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| DSP-005 答辩/举证（**修复程序正义硬伤**）：开纠纷仅有发起方 reason + 系统快照，被诉方全程无发声渠道，仲裁员据一面之词即裁决分钱 → 新增 `DisputeStatement` 陈述表（只增）、`POST/GET /disputes/{id}/statements`（当事人可附证据，对方收通知，结案后禁言，仅当事人+管理员可见） | `dispute/models.py::DisputeStatement` + `dispute/router.py` | `tests/test_dispute_statements.py` |
| DSP-005 两造兼听守卫：被诉方未答辩且答辩期（`DISPUTE_RESPONSE_HOURS`，默认 48h）未过 → 裁决被拒（`response_window_open`）；逾期未答辩可缺席裁决，防一方不出面拖死流程 | `dispute/router.py::_respondent_had_voice` + `issue_verdict` | 同上（含缺席裁决路径）；7 个既有裁决测试同步补答辩前置 |

## 已实现（V39 批次：IM 已读位点——未读数与红点）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| IM-010 聊天已读位点（**补聊天标配缺口**）：IM 此前零已读状态，用户无从知道哪个会话有新消息 → 新增 `ConversationRead` 已读位点表；会话列表附 `unread_count` 与最后一条消息预览、有未读优先排序；`/conversations/unread-count` 全局红点；`/conversations/{id}/read` 标记已读（复用参与者鉴权，自己发的消息不计未读） | `im/models.py::ConversationRead` + `im/router.py` | `tests/test_im_unread.py` |
| SDK 同步：conversations 富返回 / imUnreadCount / markConversationRead | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V38 批次：被封发布者挂单下架）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| OPS-013 续：封禁下架未成交挂单（**补 V36 遗漏面**）：V36 处理了在途合约，但被封方**已发布未成交**的任务仍留在广场，工人报名后永远等不到选人 → 封禁时自动取消其 draft/published 任务、关闭并通知全部待处理报名者；影响面预览与审计 detail 含挂单数 | `admin/router.py::_ban_impact/ban_user` | `tests/test_banned_creator_listings.py` |
| OPS-013 防御性过滤：广场排除被封/已注销发布者的任务；报名时校验发布方状态（`creator_unavailable`） | `task/router.py::list_tasks/apply` | 同上（含历史遗留数据场景） |

## 已实现（V37 批次：用户口碑页——评价消费端）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-006 用户收到的评价（**修复信任断链**）：双盲评价的评语/标签此前「只写不读」——公开主页仅 rating_avg 聚合，选人时看不到「为什么是这个分」→ 新增 `/users/{id}/reviews`：收到的评价列表 + 标签计数聚合 + 分页；**严格复用双盲揭晓规则**（盲窗内评价一律不返回），杜绝从用户维度旁路偷看 | `task/router.py::user_reviews` | `tests/test_user_reviews.py`（含盲窗不泄露、窗口到期单边揭晓、标签聚合、分页） |
| SDK 同步：userReviews | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V36 批次：封禁影响面——爆炸半径可见 + 对手方自救）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| OPS-013 封禁影响面（**修复盲拍开关**）：封禁原为静默 flag 翻转，管理员看不到在途合约/涉险托管，对手方也无人告知——被封方无法交付/验收，对方托管资金被无限期困住 → 新增 `/admin/users/{id}/ban-impact` 无副作用预览（在途合约、涉险托管、钱包三态）；封禁响应带影响面并写入审计 detail；**自动通知全部在途对手方**提示取消或发起纠纷 | `admin/router.py::_ban_impact/ban_impact/ban_user` | `tests/test_ban_impact.py`（含对手方取消后托管归零 + 守恒断言） |
| SDK 同步：banImpact | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V35 批次：管理员操作审计——合规留痕）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| OPS-012 管理员操作审计（**补合规缺口**）：~20 个高权限端点原无任何操作留痕，无法回答「哪个管理员何时对谁封禁/裁决/放款」→ 新增 `AdminAudit` 只增审计表 + `record_audit` 助手，接入封禁/解封/纠纷裁决/申诉复核/平台结算/大额提现审批；`/admin/audit-log` 可按动作筛选、分页，管理员限定 | `admin/models.py::AdminAudit` + `admin/router.py::record_audit/audit_log` + 各高权限端点 | `tests/test_admin_audit.py` |
| SDK 同步：adminAuditLog | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V34 批次：验收驳回上限——防无限返工欠薪）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-033 验收驳回上限（**修复工人保护缺口**）：reject_count 原只记录不约束，发布方可无限「驳回返工」变相欠薪 → 达上限（默认 3 次）后禁止再单方驳回，须验收或走纠纷仲裁；每次驳回通知执行者原因与剩余次数 | `task/router.py::reject_delivery` + `MAX_REJECT_ROUNDS` | `tests/test_reject_limit.py` |

## 已实现（V33 批次：任务详情视角上下文）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-017 详情「我与此任务的关系」（**修复体验缺口**）：worker 报名后详情仍显示报名按钮、点了才 409 → GET /tasks/{id} 附 my_application_status / bookmarked；发布者附 applications_count | `task/router.py::get_task` | `tests/test_task_detail_context.py` |
| SDK 同步：Task 类型补视角字段 | `packages/core/src/types.ts` | web 构建通过 |

## 已实现（V32 批次：通知中心——未读徽章 + 全部已读 + 分页）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| NTF-005 未读徽章计数 + 一键全部已读（应用红点标准能力，此前缺失）：`/notifications/unread-count`、`/notifications/read-all`；通知列表补 offset 分页 | `notification/router.py` | `tests/test_notification_center.py` |
| SDK 同步：unreadCount/markAllRead | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V31 批次：我的报名/投标）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| MATCH-010 我的报名（**补配套缺口**）：`/tasks/mine?role=working` 只含已成交单，等待选人的报名无处可查 → 新增 `/users/me/applications`：列出本人投出的报名及所报任务当前状态，可按报名状态筛选、offset 分页、用户隔离 | `task/router.py::my_applications` | `tests/test_my_applications.py` |
| SDK 同步：myApplications | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V30 批次：我的任务中心）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-016 我的任务中心（**补能力缺口**）：广场只展示 published+public，用户无法列出自己的草稿/执行中/已完成任务、也看不到自己执行的单 → 新增 `/tasks/mine`：posted（我发布）/working（我执行）/all，可按状态筛选，offset 分页，用户隔离 | `task/router.py::my_tasks` | `tests/test_my_tasks.py` |
| SDK 同步：myTasks | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V29 批次：任务广场分页）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-003 广场分页（**补能力缺口**）：原只有 limit（≤100）+ 硬性 500 上限、无 offset，超窗旧任务永远翻不到 → 补 DB 层 offset/limit 分页（非地理路径直接 DB 分页，不再拉全表切片）；地理检索按距离排序后分页 | `task/router.py::list_tasks` | `tests/test_task_pagination.py`（页间不重不漏、limit 上限、offset 越界、地理分页） |

## 已实现（V28 批次：密码登录防暴力破解）

| Spec 安全项 | 实现 | 测试 |
|---|---|---|
| ACC-002 密码登录限流（**修复真实漏洞**）：注册/短信登录早有限流，密码登录 `/auth/login` 却完全不限，可对已知手机号无限撞库 → 补同号 60s 内 5 次尝试上限，按手机号隔离 | `account/router.py::login` + `core/ratelimit` | `tests/test_login_ratelimit.py` |

## 已实现（V27 批次：幂等键请求指纹——修复串味/吞单）

| Spec 安全项 | 实现 | 测试 |
|---|---|---|
| 14.6/05.B 幂等键请求指纹（参照 Stripe，**修复两处真实缺陷**）：① 同 key 复用不同金额原返回旧结果（吞单）；② 同 key 跨操作（topup vs withdraw）原按 (user,key) 命中会串味 → 记录 scope+参数指纹，指纹不符 409 `idempotency_key_conflict`；完全相同请求仍正常重放 | `core/idempotency.py::replay_or_run` + `fingerprint` 列 + wallet 路由传参 | `tests/test_idempotency_fingerprint.py` |

## 已实现（V26 批次：内部定时任务鉴权——修复未授权访问漏洞）

| Spec 安全项 | 实现 | 测试 |
|---|---|---|
| OPS-011 cron 端点鉴权（**修复真实漏洞**）：7 个 job（自动放款/合约作废/任务下架/纠纷升级/评分结算/位置清理/逾期预警）原为无鉴权公开接口，任何人可触发改动资金与状态；改为强制携带共享密钥 `X-Job-Token`（生产改强随机） | `core/deps.py::require_job_auth` + `settings.JOB_TOKEN` + 全部 job 端点 | `tests/test_job_auth.py`（穷举 7 端点：无 token/错 token 403，正确放行；用户身份不能绕过） |

## 已实现（V25 批次：过期任务自动下架）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-015 过期任务自动下架（**补执行缺口**：deadline 发布时校验、发布后从不执行 → 僵尸挂单永占广场）：published 且过截止时间未成交 → 转 cancelled，通知发布者与全部待处理报名者；已成交/无 deadline 不受影响；幂等 | `task/router.py::run_expire_tasks` (`/tasks/jobs/expire-tasks`) | `tests/test_task_expiry.py` |
| SDK 同步：expireTasks | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V24 批次：收款账户绑定——提现前置）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| PAY-005 收款账户绑定（**补齐能力缺口**：原提现无收款目标，凭空到账）：绑卡/支付宝、账号脱敏展示、可改绑 | `wallet/router.py::bind/get_payout_account` + `PayoutAccount` 模型 | `tests/test_payout_account.py` |
| PAY-005 提现前置守卫：未绑收款账户不可提现（`no_payout_account`） | `wallet/service.py::withdraw` | 同上 + test_wallet |
| PAY-005 收款人实名一致校验（防代提/洗钱）：holder_name 须等于实名 | `wallet/router.py::bind_payout_account` | 同上 |
| SDK 同步：getPayoutAccount/bindPayoutAccount | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V23 批次：平台佣金收入实收口径 + 结算 + 对账不变量）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SC-009 佣金收入口径修复（**真实缺陷**）：metrics.fee_income 原按 Σ(released×费率) 估算，漏计纠纷/取消场景佣金且有逐笔取整漂移；改为以平台账户实收（fee 流水）为唯一事实来源 | `wallet/service.py::platform_finance` + `admin/metrics` | `tests/test_platform_finance.py` |
| OPS-010 平台收入总览 + 结算：累计佣金/已结算/可结算余额；结算划出（模拟对公），超额拒绝 | `admin/router.py::platform_finance/settle` + `wallet::settle_platform` | 同上 |
| PAY-006 对账新增第 4 条不变量：平台账户可用 == Σ佣金 - Σ平台结算；全局守恒出账口径纳入平台结算 | `risk/service.py::reconcile` | 同上（结算后守恒仍成立） |
| SDK 同步：platformFinance/settlePlatform | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V22 批次：任务编辑防调包 + 截止时间校验）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-014 任务编辑（**补齐能力缺口**：原发布后完全不可编辑）+ 防调包保护：draft 自由改；已发布且有人报名后实质条款受保护（预算只上不下、技能锁定），非实质字段始终可改，实质变更通知报名者 | `task/router.py::edit_task` | `tests/test_task_edit.py` |
| TASK-014 截止时间校验：发布时 deadline 必须晚于当前（防过期任务上架） | `task/service.py::validate_publishable` | 同上 |
| SDK 同步：editTask | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V21 批次：批判性扫描——真双盲评分/变更单文书/换绑手机/平台公告）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-002 真双盲评分（**修复旁道泄露**）：原评分提交即更新对方 rating_avg/信用分，对方看主页分数变化可反推星级并窗口内报复；改为评分聚合延迟到公开时点（双评完/窗口到期）结算，加 `settle-reviews` 兜底 job | `task/router.py::create_review/list_reviews/_settle_reviews` + `Review.rating_applied` | `tests/test_v21_critical.py` |
| SC-007 变更单条款附录（**修复文书矛盾**）：改价后 terms 仍是原金额，导出合约与实际不符；改为以带事由的变更附录追加，导出文书体现新金额 | `contract/service.py::accept_change` | 同上 |
| ACC-008 换绑手机：新号验证码 + 旧密码双重校验，新号查重，限流防刷 | `account/router.py::change_phone` | 同上 |
| OPS-009 平台公告广播：向全体/仅实名活跃用户群发站内通知，非管理员拒绝 | `admin/router.py::broadcast_announcement` | 同上 |
| SDK 同步：changePhone/broadcastAnnouncement | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V20 批次：批判性扫描——收藏/接单开关/新设备提醒/对账告警闭环）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| TASK-013 任务收藏（幂等添加/列表/移除） | `task/router.py` bookmark 路由 + `Bookmark` 模型 | `tests/test_v20_ops_features.py` |
| ACC-014 接单开关（业界「上线/下线」）：关闭后不进推荐、不可被邀约；主动报名不受限 | `User.accepting_orders` + 推荐召回过滤 + 邀约守卫 | 同上 |
| ACC-007 新设备登录提醒：陌生 UA 登录触发站内通知，已知设备静默 | `account/router.py::_issue_token` | 同上 |
| PAY-008 对账告警闭环：不变量校验失败自动开差错工单 + 通知全体管理员（原来只返回结果没人看） | `admin/router.py::run_reconcile` | 同上 |
| SDK 同步：bookmark/unbookmark/myBookmarks | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V19 批次：批判性扫描——提现风控 + 密码管理 + 报名撤回）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| PAY-007 提现风控（业界惯例）：单日限额硬拒（含待审计入）；大额冻结进人审队列，批准划出/驳回解冻；对账冻结口径扩展（保证金+待审提现） | `wallet/service.py::withdraw/decide_withdraw` + `WithdrawRequest` 模型 + 管理端路由 + `risk.reconcile` 口径 | `tests/test_withdraw_risk.py` |
| ACC-004 密码管理：改密验旧密码、忘记密码短信重置，均吊销全部旧会话（防盗号后旧 token 续命）+ 重置限流防爆破 | `account/router.py::change_password/reset_password` | `tests/test_password_and_apply_withdraw.py` |
| TASK-012 报名撤回：pending 可撤、撤后可重报；**修复：撤回的报名仍可被发布者成交（替人签约）**——成交守卫补 `application_closed` | `task/router.py::withdraw_application` + accept 守卫 | 同上 |
| SDK 同步：withdraw 富返回/withdrawRequests/decideWithdraw/changePassword/resetPassword/withdrawApplication | `packages/core/src/client.ts` | web 构建通过 |

## 已实现（V18 批次：纠纷 SLA + 申诉窗口，见提交记录）

## 已实现（V17 批次：双盲互评完整落地 + 并发接单上限）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-002 双盲互评（Upwork 惯例）：修复路人泄露——盲窗内评价对第三方也隐藏（否则换号偷看即破防）；新增 14 天评价窗口，到期单方评价自动公开且不可补评（防看到差评后报复） | `task/router.py::list_reviews/create_review` + `REVIEW_WINDOW_DAYS` | `tests/test_blind_review.py` |
| TASK-011 执行者并发接单上限（零工平台惯例，防过度接单违约）：在途单达上限后报名/选人/接受邀约均拒；完成释放额度；上限以成交时点复核 | `task/service.py::check_executor_capacity` + 三个入口守卫 + `MAX_ACTIVE_TASKS` | `tests/test_executor_capacity.py` |

## 已实现（V16 批次：签署有效期 + App 闭环补齐 + 操作矩阵下沉 SDK）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SC-012 签署有效期（业界 offer 有效期惯例）：成交后 N 天未双签自动作废，释放冻结保证金，防资金卡死 | `contract/router.py::run_expire_unsigned` + `SIGN_EXPIRE_DAYS` 配置 | `tests/test_contract_expiry.py`（含半签超期作废、新鲜/已托管不动、幂等、守恒） |
| 03/05 操作可见性矩阵单一事实来源（Web/App 共用防漂移） | `packages/core/src/actions.ts::taskActions` 纯函数 | `packages/core/src/actions.test.ts`（9 例：角色×状态全覆盖） |
| 13 App 端闭环补齐：报名列表+选人成交+双签+托管+驳回+纠纷+取消（原断档：App 单端走不完闭环） | `app/App.tsx` TaskDetailScreen 由 taskActions 驱动 + 合约卡片（金额/费率/保证金/签署进度） | 逻辑在 SDK 层测试；web 构建通过 |

## 已实现（V14 批次：多人任务预算守恒 + 自动验收边界）

| Spec 不变量 | 测试 | 说明 |
|---|---|---|
| TASK-007 名额拆分预算守恒 | `tests/test_multiperson_autoaccept.py` | 修复：整除余数原被静默丢弃（10000/3 每单蒸发 1 分）→ 余数并入末位名额，Σ名额 == 母任务预算 |
| TASK-007 多名额全周期资金守恒 | 同上 | 各名额分别成交放款，放款额/抽佣与名额预算逐分对应，reconcile 恒成立 |
| TASK-031 自动验收时间边界 | 同上 | 恰好越过 cutoff 的放款、差 1 小时的不动；唯一「无人点击也动钱」路径的守恒断言 |
| TASK-031 job 重跑幂等 | 同上 | 无新到期单时零动作、余额不变 |

## 已实现（V13 批次：分期×纠纷交叉路径守恒）

| Spec 资金不变量 | 测试 | 说明 |
|---|---|---|
| SC-004×DSP-007 部分放款后裁决只分剩余托管 | `tests/test_milestone_dispute_cross.py` | 首期已放款不可追回/不重复计算，裁决基数=剩余托管，钱包金额精确断言 |
| DSP-008 复核基数对外可见 | dispute `_dump` 补 `split_base_cents` | 修复：响应缺字段（申诉复核需展示裁决基数） |
| SC-008 冻结期一切放款被拒 | 同上测试 | 纠纷冻结中里程碑验收 `contract_frozen`、整体取消被拒，资金零变动 |
| DSP-004 和解分账守恒（含保证金） | 同上测试 | 部分放款后和解只分剩余，保证金解冻回可用，reconcile 恒成立 |

## 已实现（V12 批次：变更单资金守恒）

| Spec 资金不变量 | 测试 | 说明 |
|---|---|---|
| SC-007 加价补托管守恒 | `tests/test_change_order_money.py` | funded 态加价→补足差额托管，escrow/available 精确变动，reconcile 恒成立，放款额随新金额 |
| SC-007 减价退款守恒 | 同上 | 减价→差额退回可用余额，放款额随新金额，全程账实一致 |
| SC-007 变更单守卫 | 同上 | 提案方不能自接（not_counterparty）、已有 pending 不可再提（change_pending）、重复接受被拒（change_closed，无二次补托管） |
| SC-007 多轮随机改价守恒 | 同上 | seed 化 8 单×1~3 轮上下浮动改价后放款，每步 reconcile 断言零泄漏 |

## 已实现（V11 批次：存证哈希链防篡改深度校验）

| Spec 安全不变量 | 测试 | 说明 |
|---|---|---|
| SC-011 逐行哈希绕过防护 | `tests/test_anchor_chain.py` | 同步改 payload+payload_hash 骗过逐行校验 → 仍被 chain_hash 抓出 |
| SC-011 多米诺链接（改一行须重写整条后继链） | 同上 | 某行三重哈希全部自洽伪造 → 下一行 prev 链接断裂，定位到 seq+1 |
| SC-011 删除/重排篡改 | 同上 | 删除中间存证 → 后继 prev 断裂；创世锚点脱链 → 首条即断裂 |
| SC-011 链头可公示锚定 | 同上 | 未篡改链 verify.head == 末条 chain_hash（对外锚定基准） |

## 已实现（V10 批次：并发/重复提交防重放硬化）

| Spec 安全不变量 | 测试 | 说明 |
|---|---|---|
| 14.6 一任务一合约（重复接受报名/并发接单不产生第二份合约） | `tests/test_concurrency_guards.py` | 重复接受同一/不同报名均被 `not_recruiting` 拒绝；DB 层 `contracts.task_id UNIQUE` 为最后防线 |
| 05.B 托管资金只扣一次（重复 fund） | 同上 | 第二次 fund 命中 `not_fundable`，托管额恒等于合约金额 |
| 03.A 交付幂等（重复 deliver） | 同上 | 二次交付被状态机 `invalid_transition` 拒绝 |
| 05.B 放款不重复（重复验收/重复里程碑验收） | 同上 | 二次验收命中 `not_releasable`/`invalid_milestone_state`，执行者余额不二次增加；get_db 异常整体回滚保证零副作用 |
| MATCH 报名去重（重复报名） | 同上 | 第二次报名 `already_applied`，仅一条报名记录 |

## 已实现（V9 批次：核心不变量测试硬化）

| Spec 不变量 | 测试 | 说明 |
|---|---|---|
| 03.A 任务状态机 P0（必须严格约束流转） | `tests/test_state_machine.py` | 白名单穷举：每个非法 (from,to) 必拒且错误码为 invalid_transition；终态无出边；状态引用合法；无自环 |
| 05.B/PAY-006 资金守恒（全局守恒/托管有据/冻结有据） | `tests/test_money_property.py` | 随机化 20 条生命周期（验收/取消/仲裁/申诉/多里程碑），每步后 reconcile 断言账实一致 |

## 已实现（V8 批次：工程硬化——非功能需求落地）

| Spec 非功能项 | 实现 | 测试 |
|---|---|---|
| 14.6/05.B 资金操作强制幂等（Idempotency-Key，充值/提现） | `core/idempotency.py` + wallet 路由 | `tests/test_hardening.py` |
| ACC-001 注册/短信登录 60s 防刷限流 | `core/ratelimit.py` + account 路由 | 同上 |
| 14.6 资源级鉴权（越权访问拒绝）回归 | 各模块既有检查 + 集中越权测试 | 同上（跨用户/管理端） |

## 已实现（V7 批次：增长与分析闭环）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| 13.C 埋点事件上报 + 发布漏斗/接单漏斗看板（P0） | `analytics/service.py::funnels` + `router.py` | `tests/test_growth_analytics.py` |
| CNT-022 邀请裂变：邀请码归因 + 首单闭环奖励邀请人（每人一次） | `analytics/service.py::_on_task_completed` + 账户注册 | 同上 |
| SRCH-003 搜索词记录 + 热词榜 + 前缀联想 | `analytics/service.py::trending_terms/suggest_terms` | 同上 |

## 已实现（V6 批次：真实 LLM 网关 + 供需看板 + 演示数据）

| 项 | 实现 | 测试 |
|---|---|---|
| 04.E 真实 LLM 网关 AnthropicLLM（claude-opus-4-8 + adaptive thinking + JSON Schema 结构化输出） | `server/app/modules/decompose/llm.py` | `tests/test_llm_gateway.py`（mock SDK） |
| 04.E 降级路径（无 Key/超时/输出不合规 → 自动回落模板引擎，预算守恒兜底） | `llm.py::AnthropicLLM.decompose` | 同上（三条降级/校验用例） |
| KB-024 类目供需看板（在招需求/闭环数/GMV/供给/供需比） | `knowledge/router.py::category_demand` | 同上 |
| 演示数据脚本（一键生成可交互样例：用户/任务/闭环/圈层/动态） | `server/scripts/seed_demo.py` | 运行验证 |

> LLM 网关设计：`ANTHROPIC_API_KEY` 存在即启用真实模型；缺省与 CI 环境走
> `TemplateLLM`，测试用 `unittest.mock` 打桩 SDK，全程离线可跑。接入真实模型
> 不改任何业务代码——`get_gateway()` 抽象层已就位。

## 已实现（V5 批次：前端覆盖补齐 + 工程化交付）

| 项 | 实现 | 验证 |
|---|---|---|
| Web 发布向导（模板填充/AI 可行性提示/多人/保证金/城市与类目下拉/受限类目提示） | `web/src/pages/Publish.tsx` | 前端测试 + tsc/vite build |
| Web 服务设置（定价/可接单时间/隐私开关）与设备管理/注销 | `web/src/pages/Profile.tsx` | 同上 |
| Web 合约凭证下载 + 经验帖入口 | `web/src/pages/TaskDetail.tsx` | 同上 |
| SDK V3/V4 全量接口（澄清/模板/城市/会话/注销/导出/报价卡/圈层面板） | `packages/core/src/client.ts` | SDK 单测 |
| Docker 交付（server 镜像 + web nginx 镜像 + compose 一键全栈） | `server/Dockerfile`, `web/Dockerfile`, `docker-compose.yml` | YAML 校验 |
| CI 流水线（后端 pytest / 前端 vitest+build / 启动冒烟，PR 自动跑） | `.github/workflows/ci.yml` | PR #5 |

## 已实现（V4 批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| RISK-003 反欺诈（同对手方 7 天 3 单→不计信用+进人审队列） | `risk/service.py` + `task/router.py::_complete_task` | `tests/test_v4_features.py` |
| PAY-006 对账（守恒/托管有据/冻结有据三不变量，篡改可检出） | `risk/service.py::reconcile` + `/admin/jobs/reconcile` | 同上 |
| MATCH-003 订阅推送频控（每人每日 5 条） | `matching/events.py` | 同上 |
| CIR-010 同圈信任加成 + 推荐理由标识 | `matching/service.py` | 同上 |
| CIR-009 圈层数据面板（成员/帖子/成交/GMV，管理员） | `circle/router.py::circle_stats` | 同上 |
| IM-009 结构化报价卡消息 | `im/router.py::send_quote_card` | 同上 |
| ACC-030 隐私设置（非公开档案仅信任摘要） | `account/` | 同上 |
| ACC-013 服务定价与可接单时间（名片页承接下单） | `account/` | 同上 |
| KB-003 闭环任务一键生成经验帖（case 卡挂类目与来源） | `content/router.py::create_experience_post` | 同上 |
| KB-013 估价新鲜度（仅统计近 180 天，过期淘汰） | `knowledge/service.py::price_reference` | 同上 |
| TASK-003 任务模板库（模板+检查清单+参考价） | `task/service.py::TASK_TEMPLATES` | 同上 |
| GEO-030 城市开通管理（线下任务城市门禁） | `task/models.py::City` + `admin/router.py` | 同上 |
| SC-010 合约文本与结算凭证导出（含流水与存证哈希） | `contract/router.py::export_contract` | 同上 |

## 已实现（V3 批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| ACC-005 登录会话/设备管理（列出/踢出，token 绑定会话可吊销） | `account/models.py::LoginSession` + `core/deps.py` | `tests/test_v3_features.py` |
| ACC-006 账号注销（未结算合约/纠纷/余额阻断，脱敏保留） | `account/router.py::deactivate_account` | 同上 |
| TASK-007 多人任务（N 名额子任务，独立合约，母任务自动结项） | `task/router.py::create_task` + `decompose/service.py` | 同上 |
| AI-DEC-001/002 对话式澄清 + 预算可行性预判（对照知识库中位价） | `decompose/router.py::clarify` | 同上 |
| AI-DEC-025 母任务结项报告（成本/工期/交付清单） | `decompose/router.py::final_report` | 同上 |
| OPS-004 类目管理（种子+CRUD+启停校验+资质挂载） | `task/models.py::Category` + `admin/router.py` | 同上 |
| MATCH-008 匹配权重后台可配（实时生效，和为 1 校验） | `matching/models.py::MatchingConfig` + `admin/router.py` | 同上 |
| NTF-003 通知偏好（分类开关，funds 必达不可关） | `support/models.py::NotificationPref` + `notification/` | 同上 |
| CS-013 工单（AI 转人工自动建单→处理→通知） | `support/models.py::Ticket` + `admin/router.py` | 同上 |
| DSP-008 申诉复核（一次，差额纠正性划转终局） | `dispute/router.py::appeal/appeal_verdict` | 同上 |
| CRED-003 信用等级权益（S/A/B/C → 费率 6%/7%/8%） | `account/service.py::credit_level` + 合约生成 | 同上 |
| GEO-021 行程共享（执行者开关，任务结束失效） | `task/router.py::trip-share` | 同上 |
| GEO-023 紧急求助（留痕+通知对方） | `task/router.py::sos` | 同上 |
| GEO-024 位置保留策略（结束 30 天清除精确坐标） | `task/router.py::purge_locations` | 同上 |

## 已实现（V2 批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CRED-005 保证金（成交冻结/闭环退还/违约罚没） | `wallet/service.py` + `contract/service.py::_settle_deposit` | `tests/test_v2_features.py` |
| ACC-022 职业资质 + 受限类目准入 | `account/router.py` + `task/service.py::check_category_qualification` | 同上 |
| LAW-003 律师市场（法律咨询类目 = 持证律师接单） | 同上（复用任务流） | 同上 |
| SC-011 存证哈希链（append-only、防篡改可验证） | `anchor/`（合约签署/托管/放款/裁决自动入链） | 同上（含篡改检测） |
| ACC-033 黑名单（禁私聊/禁报名/推荐排除，双向） | `account/models.py::Block` + im/task/matching 检查点 | 同上 |
| IM-004 消息撤回（2 分钟窗口，审计副本保留） | `im/router.py::recall_message` | 同上 |
| AI-DEC-023 子任务违约自动重新招募 | `decompose/resilience.py` | 同上 |
| AI-DEC-022 逾期预警 job | `decompose/resilience.py::deadline_alerts` | 同上 |

## 已实现（V1 收尾批次）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| SRCH-001 统一搜索（任务/用户/内容/圈层分组） | `server/app/modules/search/router.py` | `tests/test_v1_extras.py` |
| TASK-006 周期任务（闭环自动续期+通知） | `task/events.py` + `Task.recurrence` | 同上 |
| LAW-002 文书生成（催告函/和解协议，自动填充） | `legal/router.py::generate_document` | 同上 |
| ACC-031 个人数据导出（PIPL/GDPR） | `account/router.py::export_my_data` | 同上 |
| OPS 管理后台 Web UI（指标/举报处置/封禁） | `web/src/pages/Admin.tsx` | `web/src/Admin.test.tsx` |
| MATCH-007 竞价发布与报价比选 UI | `web/src/pages/{Publish,TaskDetail}.tsx` | 构建 + SDK 单测 |
| APP-005/006 App 五 Tab + 任务详情操作/钱包/通知 | `app/App.tsx` | 骨架（Expo 运行时验证） |

## 已实现（V1 增量，2026-07-03）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| CNT-001/003 动态与博客（可见性/标签） | `server/app/modules/content/` | `tests/test_content_circle.py` |
| CNT-005 内容挂载服务入口 | `content/models.py::linked_category` | 同上 |
| CNT-006 内容/评论机审 | `content/router.py`（复用 RISK-001 词表） | 同上 |
| CNT-010/011 关注流/最新流 | `content/router.py::feed` | 同上 |
| CNT-020/021 点赞评论/关注粉丝 | `content/router.py` | 同上 |
| CIR-001 三类圈层+自带群聊 | `circle/` | 同上 |
| CIR-002 按技能/城市推荐圈层 | `circle/router.py::discover` | 同上 |
| CIR-003 加入审核+信用门槛 | `circle/router.py::join/approve` | 同上 |
| CIR-004/005 圈层内容流/任务板（仅成员） | `circle/router.py` + Task.visibility | 同上 |
| CIR-006/007 群聊成员同步/移出管理 | `circle/router.py` | 同上 |
| TASK-008 任务可见范围（公开/圈层） | `task/models.py` + router | 同上 |
| SC-004 多里程碑分期交付/放款 | `contract/service.py::define/deliver/release_milestone` | `tests/test_contract_v1.py` |
| SC-007/TASK-025 变更单双签改价（多退少补、版本+1） | `contract/service.py::propose/accept_change` | 同上 |
| 取消/裁决按剩余托管额计算 | `contract/service.py::cancel/execute_verdict` | 同上 |
| MATCH-004 定向邀约（接受即成交） | `matching/router.py` | `tests/test_admin_legal_matching.py` |
| TASK-042 类目+城市订阅→发布通知 | `matching/models.py` + `matching/events.py` | 同上 |
| LAW-001 法律信息 AI（免责声明/高风险拒答） | `legal/router.py` | 同上 |
| LAW-005 证据包导出（SHA256 防篡改） | `legal/router.py::evidence_export` | 同上 |
| RISK-006/007 举报→审核队列→处置（下架/封禁） | `admin/` + `core/deps.py` 封禁拦截 | 同上 |
| OPS-002 用户管理（封禁/解封） | `admin/router.py` | 同上 |
| OPS-007 指标看板（闭环率北极星/GMV/佣金/纠纷） | `admin/router.py::metrics` | 同上 |
| Web 社区/圈层页 + 里程碑操作 + 邀约 + 订阅 | `web/src/pages/{Community,Circles}.tsx` 等 | `web/src/App.test.tsx` + SDK 单测 |

## 已实现（MVP）

| Spec 功能点 | 实现 | 测试 |
|---|---|---|
| ACC-001/002 注册登录（短信码/密码） | `server/app/modules/account/router.py` | `tests/test_account.py` |
| ACC-010/011 资料与技能标签 | 同上 | 同上 |
| ACC-020 实名认证（模拟 eKYC）+ 接单/提现准入 | `account/router.py` + `core/deps.py::require_verified` | `test_account.py`, `test_wallet.py`, `test_task_flow.py` |
| CRED-001/002/004 信用分/双向盲评/违约惩罚 | `account/service.py` | `test_task_flow.py`, `test_im_dispute_support.py` |
| CRED-006 公开信用名片（脱敏） | `account/router.py::public_profile` | `test_account.py` |
| TASK-001/004/005 发布/机审/编辑约束 | `task/router.py`, `task/service.py` | `test_task_flow.py` |
| 任务状态机（03.A，非法流转拒绝） | `task/models.py::TRANSITIONS` + `service.transition` | `test_task_flow.py::test_state_machine_*` |
| TASK-020~024 成交/详情/进度/会话/交付 | `task/router.py` | `test_task_flow.py`, `test_e2e_closed_loop.py` |
| TASK-026 取消规则 | `contract/service.py::cancel` + `CANCEL_RULES` | `test_task_flow.py::test_task026_cancel_rules` |
| TASK-030/031/033 验收/超时自动验收/驳回 | `task/router.py` | `test_task_flow.py` |
| TASK-036 母任务进度聚合 | `decompose/service.py::tree_progress` | `test_decompose_knowledge.py` |
| TASK-040/041 广场/搜索/筛选 | `task/router.py::list_tasks` | `test_task_flow.py` |
| MATCH-001 报名报价 | `task/router.py` | `test_task_flow.py` |
| MATCH-002 AI 推荐（可解释加权打分） | `matching/service.py` | `test_task_flow.py::test_match002_*` |
| MATCH-009 冷启动兜底 | `matching/service.py`（中性分+新人理由） | 同上 |
| AI-DEC-001~015 分解（模板 LLM/编辑/校验/直通） | `decompose/llm.py`, `decompose/service.py` | `test_decompose_knowledge.py` |
| AI-DEC-020 依赖顺序自动发布 | `decompose/service.py::_on_task_completed` | `test_decompose_knowledge.py`, `test_e2e_closed_loop.py` |
| AI-DEC-021 驾驶舱数据 | `decompose/router.py::tree` | 同上 |
| AI-DEC-030 预算拆分守恒/超支拒绝 | `decompose/service.py::validate_items` | `test_decompose_knowledge.py` |
| SC-001~003 合约生成/双签/托管 | `contract/service.py` | `test_task_flow.py`, `test_e2e_closed_loop.py` |
| SC-005/009 验收放款/抽佣分账 | `contract/service.py::release` + `wallet/service.py` | 同上（含资金守恒审计） |
| SC-006 违约规则引擎 | `contract/service.py::cancel` | `test_task_flow.py` |
| SC-008 纠纷冻结与裁决执行 | `contract/service.py::freeze/execute_verdict` | `test_im_dispute_support.py` |
| SC-020~022 钱包三态/提现/流水 | `wallet/` | `test_wallet.py` |
| KB-001/002 闭环经验卡（事件驱动、脱敏） | `knowledge/service.py::_on_task_completed` | `test_decompose_knowledge.py` |
| KB-005 FAQ 种子 | `knowledge/service.py::SEED_FAQS` | `test_im_dispute_support.py` |
| KB-020/021 模板检索/估价分布 | `knowledge/service.py` | `test_decompose_knowledge.py` |
| GEO-004 位置脱敏（成交后可见精确地址） | `task/router.py::dump_task` | `test_task_flow.py` |
| GEO-010/011/015 附近任务/距离筛选/距离参与打分 | `task/router.py::list_tasks`, `matching/service.py` | `test_task_flow.py` |
| GEO-020 到场打卡（误差校验） | `task/router.py::checkin` | `test_task_flow.py` |
| IM-001/002 单聊/任务会话自动创建 | `im/` | `test_im_dispute_support.py` |
| IM-005 陌生人频控 | `im/service.py::check_stranger_limit` | 同上 |
| IM-006 防跳单风控标记 | `im/service.py::RISK_PATTERNS` | 同上 |
| DSP-001~004 发起/冻结/证据链/和解 | `dispute/router.py` | 同上 |
| DSP-006/007 仲裁裁决自动执行+信用惩罚 | `dispute/router.py::issue_verdict` | 同上 |
| NTF-001/004 事件驱动站内信 | `notification/` | 同上 |
| CS-002/003/006 FAQ 问答/账户上下文/转人工 | `support/router.py` | 同上 |
| 主闭环 E2E（01 spec 第 3 节全链路） | 全模块 | `test_e2e_closed_loop.py` |
| Web 端核心页面（13 spec WEB-001/002/003/007） | `web/src/pages/*` | `web/src/App.test.tsx` |
| 共享 SDK（13 spec 两端共享 API） | `packages/core/src/client.ts` | `packages/core/src/client.test.ts` |
| App 骨架（13 spec APP-001/003/005 精简） | `app/App.tsx` | 骨架（未接入测试，见差距） |

## 有意简化（MVP 降级实现，spec 目标不变）

| 项 | 现状 | 演进 |
|---|---|---|
| 短信验证码 | 固定码 123456 | 接短信服务商 |
| eKYC | 提交即通过 | 接身份核验+人脸 |
| 支付托管 | 平台内账本模拟 | 持牌机构担保交易/分账（12.A 红线） |
| LLM 分解 | 模板驱动 `TemplateLLM` | 经 `LLMGateway` 接真实模型，JSON Schema 校验已就位 |
| 客服问答 | FAQ 关键词检索 | RAG（向量检索 + LLM 生成） |
| 内容机审 | 违禁词表 | 第三方内容安全 |
| IM | REST 轮询 | WebSocket/云 IM（`MessageProvider` 抽象） |
| 定时任务 | 暴露为可调用 job 接口 | 调度器（cron/celery） |

## 未实现（均依赖外部供应商/云服务，代码侧接口已就位）

- 短视频上传转码与沉浸流（CNT-002/014）— 转码/CDN/内容安全云服务
- 个性化推荐流排序模型（CNT-011 完整版）— 需线上行为数据积累
- 存证链上锚定（SC-011 阶段三）— 哈希链已实现，差公链/联盟链写入
- 音视频通话（IM-007）— RTC 云服务
- 企业认证与发票（ACC-021/PAY-008）— 工商核验与税务接口
- App 深化：地图撒点、扫码打卡、离线推送通道（后端 API 均已就绪）
- 真实供应商接入：短信/eKYC/持牌支付托管/LLM/内容安全（抽象层已就位，接入不动业务代码）
