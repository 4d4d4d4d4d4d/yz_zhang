# 16 · Spec → 实现 → 测试 追溯矩阵

> 状态：MVP + V1 主体完成（2026-07-03）。后端 63 tests + 前端 16 tests 全绿。
> 范围：15-roadmap.md 的 MVP 全集 + V1 大部分；剩余项见文末。

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

## 未实现（剩余 V1/V2 项）

- 短视频上传转码与沉浸流（CNT-002/014）— V2（转码/审核成本高）
- 个性化推荐流排序（CNT-011 完整版：行为特征模型）— V2
- SC-011 上链存证（当前为 SHA256 哈希雏形）— V2
- LAW-002/003 文书生成、律师入驻市场 — V2
- 管理后台独立前端（API 已就绪，缺 UI）— V1 收尾
- 竞价比选页（MATCH-007 后端 bid 已支持，缺专属 UI）— V1 收尾
- 音视频通话（IM-007）、周期任务（TASK-006）、保证金（CRED-005）— V2
- App 完整版（地图/打卡/推送/圈层）— V1 收尾
