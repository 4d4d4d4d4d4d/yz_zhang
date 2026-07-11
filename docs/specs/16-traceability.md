# 16 · Spec → 实现 → 测试 追溯矩阵

> 状态：MVP + V1~V19 全批次完成（2026-07-11）。
> 后端 173 tests + 前端 29 tests 全绿。真实 LLM 分解已接入（有 Key 即用，缺省降级）。
> 剩余项均依赖外部供应商/云服务，见文末。

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
