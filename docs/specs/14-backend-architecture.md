# 14 · 后端架构与数据模型概要

## 1. 总体架构建议

**MVP 阶段：模块化单体（Modular Monolith）+ 独立资金服务**，按领域划分模块、事件驱动解耦，
待规模上来后按模块边界拆微服务。资金/合约模块从第一天起独立部署（安全与审计隔离）。

```
 客户端 (App / Web / 管理后台)
        │ HTTPS
 ┌──────▼───────────────────────────────┐
 │ API 网关 + BFF（鉴权/限流/聚合）        │
 └──────┬───────────────────────────────┘
        │
 ┌──────▼──────────────── 业务域模块 ─────────────────────┐
 │ 账户与信用 │ 任务与匹配 │ 圈层与IM │ 内容 │ 客服与纠纷    │
 └──────┬─────────────────────────────────────────────┘
        │ 领域事件 (Kafka/RocketMQ)
 ┌──────▼──────────┐  ┌───────────────┐  ┌─────────────┐
 │ 合约与资金服务*   │  │ AI 平台层      │  │ 基础设施服务  │
 │ (独立部署/审计)   │  │ LLM网关/RAG/   │  │ 搜索/推送/   │
 │                 │  │ 推荐/审核模型   │  │ 文件/审核    │
 └─────────────────┘  └───────────────┘  └─────────────┘
```

## 2. 服务/模块清单

| 模块 | 职责 | 对应 Spec |
|---|---|---|
| account | 注册登录、资料、认证、信用分 | 02 |
| task | 任务 CRUD、状态机、验收、评价 | 03 |
| matching | 召回+排序、推送触达、报名管理 | 03 |
| orchestrator | 母任务/子任务树、DAG 调度、驾驶舱 | 04 |
| contract | 合约生命周期、规则引擎、裁决执行 | 05 |
| payment | 通道、托管账本、分账、提现、对账 | 05/12 |
| knowledge | 经验采集管道、向量索引、RAG API | 06 |
| geo | Geo 索引、打卡、围栏、地址 | 07 |
| content | 动态/视频/博客、feed、互动 | 08 |
| im | 消息、会话、群、圈层群聊 | 09 |
| circle | 圈层管理、成员、任务板 | 09 |
| support | AI 客服、工单、人工台 | 10 |
| dispute | 纠纷流程、证据链、仲裁台 | 11 |
| notification | 站内信、推送、短信 | 12 |
| search | 索引与查询 | 12 |
| risk | 内容安全、反欺诈、处罚 | 12 |
| admin | 管理后台聚合 API、RBAC | 12 |
| ai-platform | LLM 网关、Prompt 管理、模型评估、Embedding | 04/06/10/11 |

## 3. 关键领域事件（事件驱动骨架）

```
task.published / task.matched / task.milestone_delivered / task.accepted
task.completed / task.cancelled
contract.signed / contract.funded / contract.released / contract.frozen
dispute.opened / dispute.resolved
user.verified / review.submitted
content.published / circle.joined
```
消费示例：`task.completed` → knowledge(经验入库) + credit(信用更新) + notification + matching(特征更新)。

## 4. 核心数据模型（ER 概要）

```
User ─┬─ Profile / SkillTag / Certification / CreditScore / Wallet
      └─ Membership ── Circle

Task ─┬─ parent_task_id (自关联: 子任务树)
      ├─ TaskDependency (DAG 边)
      ├─ Application (报名/报价)
      ├─ Milestone ── Deliverable
      ├─ Contract ─┬─ ContractVersion / EscrowLedger(资金流水)
      │            └─ Dispute ── Evidence / Verdict
      ├─ Conversation ── Message (任务会话)
      └─ Review (双向)

KnowledgeCard (任务闭环摘要: category, price_actual, duration_actual,
               decomposition_tpl, embedding, source_task_id)

Content (type: post|video|blog) ── Comment / Like / Favorite
Circle ── CircleTaskBoard / CircleFeed
```

要点：
- 金额一律整数最小货币单位；账本复式记账、只增不改。
- Task 状态机变更走统一 `TaskTransitionService`，全量审计。
- 位置字段：粗粒度(geohash 商圈级，公开) 与精确坐标(加密，成交后授权可见)分开存储。

## 5. 技术选型建议（可议）

| 层 | 建议 | 备注 |
|---|---|---|
| 后端语言 | Go 或 Java/Kotlin（资金/高并发）+ Python（AI 平台层） | 团队熟悉度优先 |
| API | REST + OpenAPI（对外），gRPC（内部） | BFF 可用 GraphQL 视复杂度 |
| 数据库 | PostgreSQL（主，含 PostGIS）| 一库多 schema 对应模块 |
| 缓存/队列 | Redis；Kafka 或 RocketMQ | |
| 搜索/向量 | Elasticsearch / OpenSearch + pgvector（起步） | 规模化再上专用向量库 |
| 对象存储 | S3 兼容 + CDN | 视频转码用云服务 |
| IM | 云 IM 起步（抽象 Provider 接口） | 见 09 |
| LLM | 统一网关多模型路由；结构化输出校验 | 见 04.E |
| 部署 | K8s + IaC；环境：dev/staging/prod | 资金服务独立命名空间与密钥 |

## 6. API 设计规范（摘要）

- 版本化 `/api/v1/...`；游标分页；统一错误码结构 `{code, message, trace_id}`。
- 鉴权：JWT 短时 + Refresh；敏感操作二次验证（支付密码/生物识别）。
- 幂等：所有写操作支持 `Idempotency-Key`（资金类强制）。
- 权限：资源级鉴权（任务双方、圈层角色、后台 RBAC）。

## 7. 待决策问题（构建前需拍板）

1. 首发地区与合规主体（决定支付通道、eKYC、地图供应商选择）。
2. App 跨端框架：Flutter vs React Native。
3. IM 云服务选型。
4. 后端主语言（团队画像决定）。
5. MVP 是否包含视频（转码与审核成本高，可延后到 V1）。
