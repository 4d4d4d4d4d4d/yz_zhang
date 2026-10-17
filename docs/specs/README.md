# 任务协作平台 · 功能拆分 Spec 总目录

> 更新：2026-10-07。规格包含已实现、部分实现和设计目标；请对照 [实现核对表](../IMPLEMENTATION-MATRIX.md)，不要将历史“完成”表述等同于商业放行。

## 产品一句话定位

以独立个体为中心、由 AI 支持的开放协作网络。每个人经营自己的数字空间，通过关系与可信约定组成合作，并把获授权的成果和经验转化为下一次合作的能力。

当前产品与 UI 基准：[88 · 独立个体网络、公开空间与合作入口](88-individual-network-and-spaces.md)。完整愿景、前后端分工、未实现能力与商业模式假设均在该篇及实现核对表中。

## 端与系统划分

| 端/系统 | 说明 | Spec |
|---|---|---|
| Web 前端 | 桌面浏览器端，全功能 | [13-clients.md](./13-clients.md) |
| App（iOS/Android） | 移动端，主打 LBS 任务 + 社交 + 内容消费 | [13-clients.md](./13-clients.md) |
| 后端服务 | 微服务/模块化单体，见架构篇 | [14-backend-architecture.md](./14-backend-architecture.md) |
| 管理后台 | 运营、审核、风控、客服工作台 | [12-platform-foundation.md](./12-platform-foundation.md) |

## 模块 Spec 索引

| 编号 | 模块 | 文档 | 优先级 |
|---|---|---|---|
| 01 | 产品总览：角色、术语、核心流程 | [01-overview.md](./01-overview.md) | P0 |
| 02 | 账户、认证与信用体系 | [02-user-account.md](./02-user-account.md) | P0 |
| 03 | 任务核心：发布 / 推荐人选 / 执行 / 完成 | [03-task-core.md](./03-task-core.md) | P0 |
| 04 | AI 任务分解与编排 | [04-ai-task-decomposition.md](./04-ai-task-decomposition.md) | P0 |
| 05 | 智能合约与资金结算 | [05-smart-contract.md](./05-smart-contract.md) | P0 |
| 06 | AI 知识库（闭环任务经验积累） | [06-ai-knowledge-base.md](./06-ai-knowledge-base.md) | P1 |
| 07 | 地域能力（LBS 与本地小任务） | [07-geo-lbs.md](./07-geo-lbs.md) | P0 |
| 08 | 内容：知识分享 / 视频 / 博客 / 朋友圈 | [08-content.md](./08-content.md) | P1 |
| 09 | 社交：聊天 / 社群 / 兴趣与能力圈层 | [09-social.md](./09-social.md) | P1 |
| 10 | 智能客服 | [10-ai-customer-service.md](./10-ai-customer-service.md) | P1 |
| 11 | 法律与纠纷解决 | [11-legal-dispute.md](./11-legal-dispute.md) | P1 |
| 12 | 平台基础：支付钱包 / 通知 / 搜索 / 审核风控 / 管理后台 | [12-platform-foundation.md](./12-platform-foundation.md) | P0 |
| 13 | 客户端功能点（Web / App） | [13-clients.md](./13-clients.md) | P0 |
| 14 | 后端架构与数据模型概要 | [14-backend-architecture.md](./14-backend-architecture.md) | P0 |
| 15 | 阶段规划（MVP → V1 → V2） | [15-roadmap.md](./15-roadmap.md) | — |
| 16 | Spec → 实现 → 测试 追溯矩阵 | [16-traceability.md](./16-traceability.md) | — |
| 17 | 编排循环 Agent Harness（发任务即调工具） | [17-orchestrator.md](./17-orchestrator.md) | P1 |
| 18 | 并发与生产化硬化 | [18-concurrency.md](./18-concurrency.md) | P0 |
| 19 | 外部供应商接入抽象层 | [19-vendor-integration.md](./19-vendor-integration.md) | P0 |
| 20 | 部署、可观测与运维 | [20-deployment.md](./20-deployment.md) | P0 |
| 21 | 移动端与 PWA | [21-mobile-pwa.md](./21-mobile-pwa.md) | P0 |
| 22 | 增长、运营与市场 | [22-growth-ops.md](./22-growth-ops.md) | P0 |
| 23 | 分布式部署与抗攻击 | [23-network-security.md](./23-network-security.md) | P0 |
| 24 | AI 编排增强：模型驱动的验收与迭代 | [24-ai-orchestration.md](./24-ai-orchestration.md) | P0 |
| 25 | 资金合规与分账（含**上线红线**） | [25-financial-compliance.md](./25-financial-compliance.md) | P0 |
| 26 | 智能合约的法律效力与纠纷解决 | [26-legal-enforceability.md](./26-legal-enforceability.md) | P0 |
| 27 | 沙箱桩实现（让预留接口跑得通） | [27-sandbox-stubs.md](./27-sandbox-stubs.md) | P0 |
| 28 | 事件投递：失败隔离、可重试、跨副本 | [28-event-delivery.md](./28-event-delivery.md) | P0 |
| 29 | 个税代扣代缴与发票 | [29-tax-withholding.md](./29-tax-withholding.md) | P0 |
| 30 | 反洗钱与可疑交易 | [30-aml.md](./30-aml.md) | P0 |
| 31 | 安全事件落库、跨副本封禁与人机验证 | [31-security-events.md](./31-security-events.md) | P0 |
| 32 | 定时任务编排的完整性 | [32-job-orchestration.md](./32-job-orchestration.md) | P0 |
| 33 | 处置动作的单一实现 | [33-moderation-actions.md](./33-moderation-actions.md) | P0 |
| 34 | 人机验证的端到端闭环 | [34-captcha-e2e.md](./34-captcha-e2e.md) | P0 |
| 35 | 账号注销的资金与个人信息闭环 | [35-account-deletion.md](./35-account-deletion.md) | P0 |
| 36 | 纠纷的当事人闭环 | [36-dispute-client-loop.md](./36-dispute-client-loop.md) | P0 |
| 37 | 上传文件的 URL 是能力，不是指纹 | [37-upload-capability-urls.md](./37-upload-capability-urls.md) | P0 |
| 38 | 被诉方真的收得到、也真的开得了口 | [38-dispute-respondent-reach.md](./38-dispute-respondent-reach.md) | P0 |
| 39 | 上传图片的内容审核与处置 | [39-upload-moderation.md](./39-upload-moderation.md) | P0 |
| 40 | 那些从来没验证过的东西（演练/告警/压测/依赖） | [40-ops-drills.md](./40-ops-drills.md) | P0 |
| 41 | 一键部署与全链路验收（Postgres 生产路径） | [41-production-path.md](./41-production-path.md) | P0 |
| 42 | 兑现两句写了很久的注释：推送通道与向量检索 | [42-push-and-semantic.md](./42-push-and-semantic.md) | P1 |
| 43 | 好友、群聊与第三方登录 | [43-social-and-oauth.md](./43-social-and-oauth.md) | P1 |
| 44 | 博客编辑器与视频沉浸流 | [44-blog-and-video.md](./44-blog-and-video.md) | P1 |
| 45 | App 发现流的视差滚动 | [45-app-parallax.md](./45-app-parallax.md) | P1 |
| 46 | App 侧视频沉浸流 | [46-app-video-feed.md](./46-app-video-feed.md) | P1 |
| 47 | 共享类型与文案的漂移，和一个从没装上过的 App | [47-shared-contract-drift.md](./47-shared-contract-drift.md) | P0 |
| 48 | 平台自有 Agent 的执行层 | [48-agent-execution.md](./48-agent-execution.md) | P0 |
| 49 | 人类核验闭环与争议升级阶梯 | [49-verification-and-escalation.md](./49-verification-and-escalation.md) | P0 |
| 50 | 早期合作体：贡献即份额 | [50-early-cooperation.md](./50-early-cooperation.md) | P0 |
| 51 | 受限类目资质：从「自己填」到「核过才算」 | [51-certification-verification.md](./51-certification-verification.md) | P0 |
| 52 | 合同缺的两条，和一档能做的浮动对价 | [52-ip-confidentiality-outcome-pricing.md](./52-ip-confidentiality-outcome-pricing.md) | P0 |
| 53 | 团队账户：预算、权限与审批 | [53-team-accounts.md](./53-team-accounts.md) | P1 |
| 54 | 开放 API 与 Webhook | [54-open-api-webhooks.md](./54-open-api-webhooks.md) | P2 |
| 55 | 国际化：先把机制做对 | [55-i18n.md](./55-i18n.md) | P2 |
| 56 | Agent 交付闭环与产出审核 | [56-agent-delivery-closure.md](./56-agent-delivery-closure.md) | P0 |
| 57 | 端上接得到：客户端契约覆盖闸门 | [57-client-reachability.md](./57-client-reachability.md) | P0 |
| 58 | 时间是一条契约（时区） | [58-timezone.md](./58-timezone.md) | P0 |
| 59 | 有后果的界面：合作体 / 团队 / 开发者 | [59-coop-team-developer-ui.md](./59-coop-team-developer-ui.md) | P0 |
| 60 | 形状也要对上（请求体与响应体闸门） | [60-shape-alignment.md](./60-shape-alignment.md) | P0 |
| 61 | 让 AI 真的参与，并且越做越好 | [61-orchestrator-agents-and-lessons.md](./61-orchestrator-agents-and-lessons.md) | P0 |
| 62 | 额度必须是累计的（团队月度预算池） | [62-team-monthly-budget.md](./62-team-monthly-budget.md) | P0 |
| 63 | App：发不出任务的按钮与四条必查项 | [63-app-store-readiness.md](./63-app-store-readiness.md) | P0 |
| 64 | 声明了却不给，给了却不声明 | [64-declared-but-not-returned.md](./64-declared-but-not-returned.md) | P0 |
| 65 | 错过就无法挽回的通知，不能被一个开关关掉 | [65-deadline-notices.md](./65-deadline-notices.md) | P0 |
| 66 | 钱能进不能出：所有端都点不动的提现按钮 | [66-money-can-get-in-but-not-out.md](./66-money-can-get-in-but-not-out.md) | P0 |
| 67 | 没有人被告知：审批两端沉默与 App 三条线 | [67-nobody-was-told.md](./67-nobody-was-told.md) | P0 |
| 68 | 建好了，可是没有一个人能按下去（求助/改密码/会话） | [68-nobody-can-press-it.md](./68-nobody-can-press-it.md) | P0 |
| 69 | 扫描闸门证明不了的那一半（App 单元测试） | [69-app-unit-tests.md](./69-app-unit-tests.md) | P0 |
| 70 | 算得很清楚的钱，没有人能动（变更单/分期/打卡） | [70-money-nobody-can-move.md](./70-money-nobody-can-move.md) | P0 |
| 71 | 进了人审，就再也出不来（提现复核台与运营侧闸门） | [71-into-review-never-out.md](./71-into-review-never-out.md) | P0 |
| 72 | **状态台账**：做了什么/没做什么/哪些「没做」其实已做 | [72-status-ledger.md](./72-status-ledger.md) | — |
| 73 | 盲封与查不到的那笔钱（运营侧监督四条） | [73-admin-oversight.md](./73-admin-oversight.md) | P0 |
| 74 | 一个人不能把不可逆的钱决定做完（四眼原则） | [74-four-eyes.md](./74-four-eyes.md) | P0 |
| 75 | 没有人会被提醒第二次（催办 / 临期 / 预警 / 超时兜底） | [75-nobody-is-reminded-twice.md](./75-nobody-is-reminded-twice.md) | P0 |
| 76 | 没有人能核过它（运营侧人审队列的出口与覆盖闸门） | [76-nobody-can-approve-it.md](./76-nobody-can-approve-it.md) | P0 |
| 77 | 进不去，也交不上（登录找回 / 资质提交 / 工单 / 发票 / 通知开关） | [77-cannot-get-in-cannot-hand-in.md](./77-cannot-get-in-cannot-hand-in.md) | P0 |
| 78 | 没有人盯的队列（SLA / 积压催办 / 队列分页） | [78-a-queue-nobody-watches.md](./78-a-queue-nobody-watches.md) | P0 |
| 79 | 视差与科技感（web 运动层 / 禁区表 / 减弱动效） | [79-parallax-and-tech-feel.md](./79-parallax-and-tech-feel.md) | P1 |
| 80 | 里面那一层也要对上（嵌套类型 / 变量请求体） | [80-nested-shapes-and-variable-bodies.md](./80-nested-shapes-and-variable-bodies.md) | P0 |
| 81 | 有人在跑的 lint（规则选择 / 豁免必须真有规则 / CI 缓存） | [81-lint-that-someone-runs.md](./81-lint-that-someone-runs.md) | P1 |
| 82 | 前端真的连得上后端吗（真浏览器联调 / 覆盖记账 / 失败判据） | [82-does-the-front-end-reach-the-back-end.md](./82-does-the-front-end-reach-the-back-end.md) | P0 |
| 83 | 经验数据的清洗与累积（不采集 / 整段抹掉 / 写读双防线 / 去重） | [83-experience-data-hygiene.md](./83-experience-data-hygiene.md) | P0 |
| 84 | 没有人跑的脚本与它印在文档里的数字（覆盖记账 / 契约性失败判死） | [84-scripts-nobody-runs.md](./84-scripts-nobody-runs.md) | P1 |
| 85 | 手抄的数字没有人核对（计数闸门 / 历史记录不改） | [85-numbers-nobody-checks.md](./85-numbers-nobody-checks.md) | P2 |
| 86 | 第一次打开钱包可能 500（懒建账户的竞态） | [86-first-wallet-read-can-500.md](./86-first-wallet-read-can-500.md) | P0 |
| 87 | 服务端叫他交资质而 App 上交不了（祈使句错误码派生闸门） | [87-server-says-do-x-but-app-cannot.md](./87-server-says-do-x-but-app-cannot.md) | P0 |
| 88 | 独立个体网络、公开空间与合作入口（当前产品与 UI 基准） | [88-individual-network-and-spaces.md](./88-individual-network-and-spaces.md) | P0 |
| 89 | 个人空间进入原生 App，与只看见双引号的闸门 | [89-spaces-on-the-app-and-single-quote-blindness.md](./89-spaces-on-the-app-and-single-quote-blindness.md) | P0 |
| 90 | 关注是个 toggle，而没有接口能告诉客户端当前状态 | [90-follow-was-a-toggle-nobody-could-read.md](./90-follow-was-a-toggle-nobody-could-read.md) | P0 |
| 91 | 单聊并发会建出两条会话（规范化唯一键 / 非破坏性迁移） | [91-direct-chat-forked-under-concurrency.md](./91-direct-chat-forked-under-concurrency.md) | P0 |
| 92 | 代扣明细与 PIPL 权利在 App 上够不到（法定权利可达性） | [92-tax-and-pipl-rights-unreachable-on-app.md](./92-tax-and-pipl-rights-unreachable-on-app.md) | P0 |
| 93 | 分期合约在一次点击里被放光（意图钉死 / 放款前的决定点） | [93-staged-payment-released-in-one-tap.md](./93-staged-payment-released-in-one-tap.md) | P0 |
| 94 | 经验按子类生长，而不是按样本堆积（聚类 / 子类自生长 / 分歧不被平均） | [94-experience-grows-by-clusters-not-samples.md](./94-experience-grows-by-clusters-not-samples.md) | P1 |
| 95 | 经验要变成能被调用的工具（检索库 / skill tool / 复用计量） | [95-experience-as-a-callable-tool.md](./95-experience-as-a-callable-tool.md) | P1 |
| 96 | 拆到能干活为止，并说清每一步谁能闭环（树状拆解 / 执行主体判定） | [96-decompose-into-a-tree-that-can-be-worked.md](./96-decompose-into-a-tree-that-can-be-worked.md) | P1 |
| 97 | 平台知道，而没有人问得到（法律问答三种结局 / 经验读回 / 内联响应形状） | [97-the-platform-knows-but-nobody-can-ask.md](./97-the-platform-knows-but-nobody-can-ask.md) | P0 |
| 98 | 部署并发：连接预算、重复付款与容量证明（CONC-060~ / FIN-070） | [98-concurrency-and-capacity-for-real-traffic.md](./98-concurrency-and-capacity-for-real-traffic.md) | P0 |
| 99 | 安全：谁能碰谁的东西（对象级授权 / 授权矩阵 / 外部视角） | [99-security-for-real-money.md](./99-security-for-real-money.md) | P0 |
| 100 | 响应形状：整条扫除，而不是挑几个抽查（26 → 178/281） | [100-response-shapes-swept-not-sampled.md](./100-response-shapes-swept-not-sampled.md) | P0 |
| 101 | 搜索：接到界面上之前，先管住它会公开的东西（k-匿名热词 / 搜人看隐私） | [101-search-before-it-goes-public.md](./101-search-before-it-goes-public.md) | P0 |
| 102 | 关注列表、内容流里的关注状态，与那一页的查询次数（关注关系按隐私过滤 / 内容流 N+1） | [102-follow-lists-and-feed-follow-state.md](./102-follow-lists-and-feed-follow-state.md) | P1 |
| 103 | 另外那些没人核对的数字：前端测试计数与结构计数（CI 里与测试框架输出比 / 表、迁移、job 回归里直接比） | [103-the-other-numbers-nobody-checks.md](./103-the-other-numbers-nobody-checks.md) | P2 |
| 104 | 幂等键：从「支持」到真的护住钱（先占键再动钱 / 过期 / 两端真的发键） | [104-idempotency-that-actually-protects.md](./104-idempotency-that-actually-protects.md) | P0 |
| 191 | 第五轮场景发掘：异地租房代看房 | [191-scenario-round5.md](./191-scenario-round5.md) | P0 |
| 190 | 对象响应完整运行时校验：复核后不做 | [190-runtime-validation-review.md](./190-runtime-validation-review.md) | P0 |
| 189 | App 主框架每一屏的畸形响应探针 | [189-app-all-screens-probe.md](./189-app-all-screens-probe.md) | P0 |
| 188 | 台账编号唯一 | [188-ledger-id-unique.md](./188-ledger-id-unique.md) | P0 |
| 187 | 后台页面出错标出已提醒的页与阈值 | [187-render-alert-marks.md](./187-render-alert-marks.md) | P0 |
| 186 | 有一页坏的人多了，提醒运营 | [186-render-error-alerts.md](./186-render-error-alerts.md) | P0 |
| 185 | 页面内块级防护：畸形响应只坏一块 | [185-block-level-resilience.md](./185-block-level-resilience.md) | P0 |
| 184 | 页面渲染出错的上报 | [184-render-error-reports.md](./184-render-error-reports.md) | P0 |
| 183 | 每一页都不白屏：错误边界与全路由闸门 | [183-no-white-screen.md](./183-no-white-screen.md) | P0 |
| 182 | 详情页每一块都扛得住畸形响应 | [182-detail-page-resilience.md](./182-detail-page-resilience.md) | P0 |
| 181 | 发单人一次选同一个人的多天 | [181-accept-a-person-for-days.md](./181-accept-a-person-for-days.md) | P0 |
| 180 | 按时段撮合 | [180-shift-matching.md](./180-shift-matching.md) | P0 |
| 179 | 验收前提醒上门回报的差距 | [179-visit-shortfall-before-accept.md](./179-visit-shortfall-before-accept.md) | P0 |
| 178 | 多天名额的每天时段 | [178-daily-shift.md](./178-daily-shift.md) | P0 |
| 177 | 一个人一次报多天 | [177-apply-several-days.md](./177-apply-several-days.md) | P0 |
| 176 | 一单多次上门的逐次回报 | [176-visit-reports.md](./176-visit-reports.md) | P0 |
| 175 | 替别人发单：发单人与服务对象分开 | [175-post-on-behalf.md](./175-post-on-behalf.md) | P0 |
| 174 | 多天名额按天汇总：哪天还缺几个人 | [174-slots-by-day.md](./174-slots-by-day.md) | P0 |
| 173 | 第四轮场景发掘：宠物上门照看与给爸妈办事 | [173-scenario-round4.md](./173-scenario-round4.md) | P0 |
| 172 | 按类别和优先级的工单时限 | [172-ticket-sla-tiers.md](./172-ticket-sla-tiers.md) | P1 |
| 171 | 管理员角色的临时授予 | [171-admin-temp-roles.md](./171-admin-temp-roles.md) | P1 |
| 170 | 团队成员离开时的交接 | [170-team-handover.md](./170-team-handover.md) | P1 |
| 169 | 法律条目有效期与到期复核 | [169-legal-faq-review.md](./169-legal-faq-review.md) | P1 |
| 168 | 我的方法的效果统计 | [168-method-stats.md](./168-method-stats.md) | P2 |
| 167 | 一单多人多天的临时帮手 | [167-multiday-slots.md](./167-multiday-slots.md) | P1 |
| 166 | 提单人在工单里追加回复 | [166-ticket-user-reply.md](./166-ticket-user-reply.md) | P1 |
| 165 | 后台按角色显示板块 | [165-admin-sections-by-role.md](./165-admin-sections-by-role.md) | P1 |
| 164 | 我的方法套到新编排 | [164-mission-from-method.md](./164-mission-from-method.md) | P1 |
| 163 | 法律知识库的运营草稿流 | [163-legal-faq-drafts.md](./163-legal-faq-drafts.md) | P1 |
| 162 | 雷达主题一键起草知识条目 | [162-radar-knowledge-draft.md](./162-radar-knowledge-draft.md) | P1 |
| 161 | 多模态智能体操作其他 App（无 agent 接口时） | [161-cross-app-agent.md](./161-cross-app-agent.md) | P0 |
| 160 | 功能检视：CORS 暴露响应头与工单进导出和注销处置 | [160-review-fixes.md](./160-review-fixes.md) | P0 |
| 159 | 全站公告按城市与人群定向、阅读率 | [159-announcement-targeting.md](./159-announcement-targeting.md) | P0 |
| 158 | 开放 API 按账号的总配额与每分钟剩余次数 | [158-api-account-quota.md](./158-api-account-quota.md) | P0 |
| 157 | 客服主管指派工单与首次响应时限 | [157-ticket-assign-first-response.md](./157-ticket-assign-first-response.md) | P0 |
| 156 | 审计链头外部锚定 | [156-audit-anchor.md](./156-audit-anchor.md) | P0 |
| 155 | 四眼按金额分级与第二人级别 | [155-tiered-four-eyes.md](./155-tiered-four-eyes.md) | P0 |
| 154 | 从编排复盘一步蒸馏成我的方法 | [154-mission-distill.md](./154-mission-distill.md) | P0 |
| 153 | 第三轮场景发掘：雷达新信号与三个场景包 | [153-scenario-round3.md](./153-scenario-round3.md) | P0 |
| 152 | API Key 用量与每日配额 | [152-api-key-usage.md](./152-api-key-usage.md) | P0 |
| 151 | 全站公告的预览、定时与撤回 | [151-announcements.md](./151-announcements.md) | P0 |
| 150 | 客服工单超时自动升级与 App 我的工单 | [150-ticket-escalation.md](./150-ticket-escalation.md) | P0 |
| 149 | 审计日志防篡改：哈希链与自检 | [149-audit-chain.md](./149-audit-chain.md) | P0 |
| 148 | 大额平台结算的四眼：两位不同的财务先后确认 | [148-settle-four-eyes.md](./148-settle-four-eyes.md) | P0 |
| 147 | 团队邀请链接 | [147-team-invites.md](./147-team-invites.md) | P0 |
| 146 | 只放已交付的那几期：分期合约的批量放款；App 补上分期列表 | [146-batch-release.md](./146-batch-release.md) | P0 |
| 145 | 开放 API 按 API Key 独立限流 | [145-api-key-rate.md](./145-api-key-rate.md) | P0 |
| 144 | 平台财务按期间报表；合约导出与证据包写明时区 | [144-finance-periods.md](./144-finance-periods.md) | P0 |
| 143 | 后台审计日志与提现复核台：筛选、总数、导出；导出时间写明时区 | [143-admin-lists.md](./143-admin-lists.md) | P0 |
| 142 | 合作体邀请的另一半：我收到的邀请、拒绝、邀请成员与分配记录上两端 | [142-venture-invitations.md](./142-venture-invitations.md) | P0 |
| 141 | 管理员分级：按职责在事前拦 | [141-admin-roles.md](./141-admin-roles.md) | P0 |
| 140 | 发单时就提示创作类需求的九项 | [140-brief-on-publish.md](./140-brief-on-publish.md) | P0 |
| 139 | 指标说真话：审核积压指标恒为 0，与后端一定是错的静态检查 | [139-truthful-metrics.md](./139-truthful-metrics.md) | P0 |
| 138 | 场景包知识检索：标签整词、连接词与技能概念展开 | [138-pack-retrieval.md](./138-pack-retrieval.md) | P0 |
| 137 | 场景发掘第二轮：自由创作者与小店临时帮手 | [137-scenario-round-2.md](./137-scenario-round-2.md) | P0 |
| 136 | App 补齐：开票、证据包导出、团队成员管理 | [136-app-gaps.md](./136-app-gaps.md) | P0 |
| 135 | 技能的语义匹配：技能概念表（撮合、认技能、个人空间、知识库检索） | [135-skill-concepts.md](./135-skill-concepts.md) | P0 |
| 134 | 编排复盘一键存进个人知识库 | [134-mission-summary-to-notebook.md](./134-mission-summary-to-notebook.md) | P0 |
| 133 | 编排复盘：花了多少、几轮、整改过哪些、评审分、草稿采用、下一步 | [133-mission-summary.md](./133-mission-summary.md) | P0 |
| 132 | 母任务结项报告上两端：实付按合约放款、是否全部完成 | [132-final-report-both-ends.md](./132-final-report-both-ends.md) | P0 |
| 131 | AI 编排两端界面；编排按授权调用经验工具；助手只读检索经验；每月助手成本上限 | [131-orchestrator-tools-and-costs.md](./131-orchestrator-tools-and-costs.md) | P0 |
| 130 | 助手专家的可靠性：运行合同、重试退避、降级交付、就绪检查、只送达一次、运行日志与健康度、角色契约 | [130-assistant-reliability.md](./130-assistant-reliability.md) | P0 |
| 129 | 端侧模型下载、断点续传、分块校验与启用；浏览器端模型评估 | [129-on-device-model-download.md](./129-on-device-model-download.md) | P0 |
| 128 | 端侧隐私沙箱：本机助手、量化小模型、原文不上云、同步前脱敏 | [128-on-device-privacy-sandbox.md](./128-on-device-privacy-sandbox.md) | P0 |
| 127 | 影响力与专家等级：不可转让、质押担保、罚没、衰减、Merkle 快照锚定 | [127-influence-and-expert-tiers.md](./127-influence-and-expert-tiers.md) | P0 |
| 126 | 任务画像与能力画像：说明完整度与补全建议、价格位置、风险、推断技能；被证明过的能力 | [126-task-and-capability-profiles.md](./126-task-and-capability-profiles.md) | P0 |
| 125 | 接单者服务包：现在有空推单、顺路单（新增绕行）、报价参考 | [125-gig-nearby.md](./125-gig-nearby.md) | P0 |
| 124 | 一人公司服务包：记账底稿、申报日历、合同体检与财税 / 合同 / 政策三位助手专家 | [124-opc-finance-compliance.md](./124-opc-finance-compliance.md) | P0 |
| 123 | 场景包引擎与平台资产：助手专家、方法、知识、模板的定义、四眼上线、启用、指标与场景雷达 | [123-scenario-packs.md](./123-scenario-packs.md) | P0 |
| 122 | 个人知识库：收件箱、笔记与链接、标签与检索、助手引用、纪要抽待办、个人方法蒸馏 | [122-personal-knowledge-base.md](./122-personal-knowledge-base.md) | P0 |
| 121 | WorkBuddy 蓝皮书逐章对照：门户的助手与知识库还缺什么（V146 复核与排期） | [121-workbuddy-bluebook-gap.md](./121-workbuddy-bluebook-gap.md) | P0 |
| 120 | 合作驾驶舱：树、关键路径、预算账、预警（SPACE-024 / AI-DEC-021 / APP-007） | [120-collaboration-cockpit.md](./120-collaboration-cockpit.md) | P1 |
| 119 | 报价卡接上两端；变更单可以改期、改范围（IM-009 / SC-007b） | [119-quote-cards-and-change-orders-with-deadline-scope.md](./119-quote-cards-and-change-orders-with-deadline-scope.md) | P1 |
| 118 | 可用时段、少量接单与回复时长进入撮合（SPACE-023） | [118-availability-and-reply-time-in-matching.md](./118-availability-and-reply-time-in-matching.md) | P1 |
| 117 | 真实演示里的粗糙之处（二）：履约上门户、发布不替人选、推荐看相关性 | [117-demo-findings-portal-record-publish-defaults-matching-fit.md](./117-demo-findings-portal-record-publish-defaults-matching-fit.md) | P1 |
| 116 | 个人工作台：我的任务、进度与助手（PWB-001~012，参照 WorkBuddy） | [116-personal-workbench.md](./116-personal-workbench.md) | P0 |
| 115 | 列表接口的查询次数不随数据量增长（CONC-066） | [115-list-endpoints-dont-scale-with-data.md](./115-list-endpoints-dont-scale-with-data.md) | P0 |
| 114 | 谁能碰作品、私聊与证件：内容类两账号行为验与授权总表（可见性单一判据、管理员受限访问写理由并审计） | [114-who-can-touch-content-and-private-data.md](./114-who-can-touch-content-and-private-data.md) | P0 |
| 113 | 调外部服务时不挂着数据库事务（守卫、三种改法、出款两阶段、提交后投递） | [113-no-vendor-call-inside-a-transaction.md](./113-no-vendor-call-inside-a-transaction.md) | P0 |
| 112 | 日志不是第二份个人信息库（一个出口、不写 SQL 参数、凭据脱敏、堆栈补回、真进程闸门） | [112-logs-are-not-a-second-pii-store.md](./112-logs-are-not-a-second-pii-store.md) | P0 |
| 111 | 再审视：做完了什么、没做完什么、业界怎么做、剩下的怎么设计（2026-10-13 复核与排期） | [111-audit-industry-and-remaining-design.md](./111-audit-industry-and-remaining-design.md) | P0 |
| 110 | 手机上找合作者（AI 推荐人选与 AI 助理进 App；六条愿景全部两端已接） | [110-find-collaborators-on-the-phone.md](./110-find-collaborators-on-the-phone.md) | P1 |
| 109 | 经验变成能被调用的单元与工具：实现（蒸馏门槛、分解在用、结果回流、只出草稿的工具、撤回穿透、两端与运营台） | [109-experience-units-and-tools.md](./109-experience-units-and-tools.md) | P0 |
| 108 | 经验按子类生长：实现（归并 job、标定阈值、待定区、共识与分歧、两端与运营台） | [108-experience-subclasses.md](./108-experience-subclasses.md) | P0 |
| 107 | 手机上的逐层拆解（App 入口、详情页继续拆与子任务进度） | [107-decompose-on-the-phone.md](./107-decompose-on-the-phone.md) | P1 |
| 106 | 拆到能干活为止的树：实现（逐层、执行主体与依据、资质否决、只在 Postgres 上才有的 500） | [106-a-tree-you-can-work.md](./106-a-tree-you-can-work.md) | P0 |
| 105 | 写操作必须在响应发出之前提交（FastAPI yield 依赖的作用域 / 确定性探针） | [105-commit-before-the-response.md](./105-commit-before-the-response.md) | P0 |

## 功能点编号与优先级约定

- 功能点编号：`<模块前缀>-<三位序号>`，如 `TASK-001`、`AI-DEC-003`。
- 优先级：
  - **P0**：MVP 必须，缺失则核心闭环跑不通。
  - **P1**：V1 重要，显著提升体验/留存，但闭环可先用人工/简化方案兜底。
  - **P2**：V2 及以后，增值/规模化能力。
- 每个功能点包含：描述、优先级、关键验收点（AC）、依赖。

## 全局非功能性要求（摘要）

- 多端一致：Web 与 App 共享同一套后端 API 与账号体系。
- 数据合规：实名信息、位置信息、支付信息加密存储；遵循当地隐私法规（如 PIPL/GDPR）。
- 可用性：核心链路（发布/接单/支付）目标 99.9%。
- 国际化：文案 i18n 预留，首期中文。
