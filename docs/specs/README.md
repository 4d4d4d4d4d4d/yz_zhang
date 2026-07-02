# 任务协作平台 · 功能拆分 Spec 总目录

> 状态：草案 v0.1（仅拆分功能点，暂不进入构建阶段）
> 更新日期：2026-07-02

## 产品一句话定位

一个「AI 驱动的任务协作与本地服务平台」：用户可以发布任务（大到项目、小到一笔交易/一次打扫卫生），
平台通过 AI 将大任务分解为子任务、智能推荐执行人选、以智能合约保障履约与结算，
并通过内容（视频/博客/朋友圈）、社交（聊天/社群/圈层）沉淀信任关系，
用 AI 知识库积累闭环任务经验，最终形成「发布 → 分解 → 匹配 → 执行 → 结算 → 经验沉淀」的正向飞轮。

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
