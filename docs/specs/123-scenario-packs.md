
# 123 场景包引擎与平台资产：助手专家、方法、知识、模板的定义、四眼上线、启用、指标与场景雷达

> 状态：本批实现（V148）。编号 PACK-100~111。
> 来源：用户 2026-10-13：「我只是举例，不局限于这些场景和功能……场景千变万化，可以提炼一些方法或者 skill 或者工作流，
> 对于这些场景也可以总结一套方法快速发掘并部署方法到这个平台上，这样也能快速部署新的功能。
> 本身这些 agent、skill、知识库就是平台重要的资产之一。」VISION 1.8；BACKLOG V148。
> 只增不减：知识库、工作台、法律问答的既有接口与行为都不变；场景包只是**往用户自己的知识库与工作台里复制**数据。
> 顺带：122 号的覆盖门槛从「60%」调成「一半且不少于 2 个」（自然问句答不上），见 122 号第 3 节。

## 0. 要解决的问题

用户点名的 OPC 财税合规、接单者就近顺路只是例子。真正要的是**一套方法**：
持续发掘场景（skill `scenario-discovery`）→ 把服务一个场景所需的平台资产打成一包 → 审核后上线 → 用户一键启用 → 看指标 → 复核或下线。
新场景主要靠**写数据**上线，而不是每次写新页面。

## 1. 业界怎么做

- **Agent Skills（Anthropic）**：一个 skill 是一个文件夹，`SKILL.md`（名称、描述 + 指令）加脚本与资源；
  元数据常驻、正文按需加载；因为能带代码，只用可信、审过的 skill。
  [Anthropic Engineering](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)。
  对应到这里：**场景包＝面向用户的 skill**——定义是数据（JSON），带助手人设、方法步骤、知识、模板；
  **不带可执行代码**，助手只能调用白名单里的平台工具；上线前四眼审核。
- **Outcome-Driven Innovation / JTBD 机会打分（Ulwick）**：机会分 = 重要性 + max(重要性 − 满意度, 0)，
  用来找「重要但没被满足」的结果。[Wikipedia](https://en.wikipedia.org/wiki/Outcome-Driven_Innovation)、
  [Intercom](https://www.intercom.com/blog/where-do-you-suck-where-does-it-matter)。
  对应到这里：场景雷达找的就是「重要（很多人搜、很多人发）但没被满足（没供给、没人接、答不上）」的信号；
  打分沿用 VISION 1.8 的「覆盖 × 频率 × 痛感 × AI 可完成度 × 商业价值 ÷ 交付成本」，雷达给出覆盖与频率的建议档位。
- **WorkBuddy 蓝皮书第 6、24 章**：专家＝人设 + 方法论 + 工具链；多 Agent 的角色契约写清输入、输出、禁止动作与必须由人确认的点。
  对应到这里：`AssistantDef` 的字段就是这份契约。

## 2. 数据

| 表 | 说明 |
|---|---|
| `scenario_packs` | `key + version` 唯一；`status` draft → review → published →（新版上线后）superseded，任何时候可 retired（写理由）；`definition` 是校验过的完整定义；`score`；`created_by / reviewed_by` |
| `pack_enrollments` | 每人每个 key 一行：启用的版本、状态（active / removed）、`installed`＝装进去的副本 id（按资产 key） |
| `pack_events` | enable / disable / ask / unanswered / helpful / unhelpful。**没有放文字的列**：提问原文不落库 |

迁移 `c1d220260015`，SQLite 与 Postgres 都验过 `upgrade head && alembic check`。

**定义格式**（`app/modules/packs/schema.py` 的 `PackDef`）：`key / title / segment / summary / pains / score / evidence /
assistants / methods / knowledge / routines / task_templates`。仓库里的种子在 `app/modules/packs/seeds/<key>.json`，
本批带一个：`collab-basics`（平台协作入门：托管、验收、纠纷、服务费；接单前确认清单、交付与验收清单；每周回顾；协作顾问）。

## 3. 规则（PACK-101，平台红线写成代码）

- 助手专家必须写**禁止动作**与**人工关口**（money / sign / file / publish / share_personal）；
  高风险人群（`opc`）的每个助手都必须把**钱、签署、申报**设为人工关口。
- 工具只能从白名单选：`pack.knowledge`、`notebook.search`（只读本人）、`legal.faq`、`workbench.method`——只读或只出草稿，**没有一个碰钱**。
- 知识条目必须有**出处**；政策类必须有**有效期**。助手引用的方法 / 知识必须在包里；引用知识就必须有 `pack.knowledge`。
- 资产 key 在包内唯一；包里至少有一样资产。格式错误（多收字段等）逐条报出来，不抛异常。

## 4. 接口

| 编号 | 接口 | 说明 |
|---|---|---|
| PACK-102 | `POST /admin/packs/validate`、`POST /admin/packs`、`PUT /admin/packs/{id}`、`GET /admin/packs` | 校验、建草稿（同 key 自动下一个版本号；有没上线的版本时 409）、改草稿（不能改 key）、列表（含指标） |
| PACK-103 | `POST /admin/packs/{id}/submit / approve / reject / retire` | **四眼**：写它的人不能自己批（409 `pack_four_eyes`）；上线时同 key 旧版本转 superseded；下线写理由；建、上线、下线进审计 |
| PACK-104 | `GET /packs`、`GET /packs/{key}`、`POST /packs/{key}/enable`、`POST /packs/{key}/disable` | 启用＝把方法 / 知识 / 例行任务**复制**进我的知识库与工作台（之后是用户自己的）；再调＝升级，只补新增的资产 key，从不覆盖；停用一律关掉例行任务，`remove_copies` 只删没改过的副本；上限沿用知识库与工作台 |
| PACK-105 | `POST /packs/{key}/assistants/{akey}/ask` | 摘录式回答：只用白名单工具；每条带出处与有效期，过期标出；高风险问题拒答指向 110；答不上时给「发一单请专业的人」（`fallback_category`）；每次回答都写人工关口说明 |
| PACK-106 | `POST /packs/{key}/feedback`；指标 | 在用、累计启用、近 30 天提问 / 答不上 / 有用 / 没用及比率 |
| PACK-107 | `GET /admin/packs/radar` | 场景雷达（见下） |
| PACK-108 | `POST /admin/packs/import-seeds` | 仓库种子导成**草稿**（内容与最新版本相同、或已有没上线版本的跳过）——文件也不能绕过四眼 |
| PACK-109 | 注销 | 启用记录与事件随注销删除；装进去的副本随知识库 / 工作台一起删除 |

**场景雷达（PACK-107）只读聚合信号**，任何来自用户行为的信号都要**至少 3 个不同的人**（k-匿名），不读笔记、私聊、提问原文：
1. 搜了没有供给：近 30 天 ≥3 人搜过、招募中的公开任务一条都匹配不上的词；
2. 有需求没人接：同一类目近 60 天招募超过 3 天没人报名、来自 ≥3 个发布方；
3. 已上线的包没接住：答不上 ≥30% 或有用率 <50%（样本 ≥5），或知识过了有效期。

## 5. 两端

- **Web**：导航多一项「服务包」（`/packs`，用户看到的名字；工程里叫场景包）。列表写清人群、解决的痛点、资产数与在用人数；
  详情页启用（可选不开定时提醒）/ 升级 / 停用（可选删掉没改过的副本）、每位助手专家的人设 / 不会做 / 必须本人确认、提问（带出处、过期标红、答不了给发单入口）、
  做法清单、知识出处与有效期、发单模板（**只预填**发布页，含验收标准）、有用 / 没用。
  管理后台多「服务包（场景包）」一节：列表与指标、编辑草稿（JSON）、校验逐条列问题、提交 / 上线（写它的人按钮禁用）/ 退回 / 下线（写理由）、导入种子、场景雷达。
- **App**：「我的」多「服务包」子页：列表、详情、启用 / 升级 / 停用、问助手专家（答不了跳发单）、反馈。管理在 Web。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| 四眼 | 去掉 `created_by == admin.id` 判断 → `test_four_eyes…` 红 |
| 已上线不可改 | 去掉草稿判断 → 同上红 |
| 高风险人群三道关口 | 去掉规则 → `test_rules_are_platform_red_lines` 红 |
| 工具白名单 | 去掉白名单比对 → 同上红 |
| 没给 notebook.search 就不读我的笔记 | 改成总是读 → `test_assistant_without_notebook_tool…` 红 |
| k-匿名 | `K_ANON = 2` → `test_radar_uses_only_k_anonymous_aggregates` 红 |
| 有供给的词不算缺口 | 去掉供给判断 → 同上红 |
| 升级只补新增 | 改成全量装 → `test_enable_installs…` 红 |
| 改过的副本不删 | 改成总是删 → 同上红 |
| 停用关掉例行任务 | 去掉 → `test_disable_without_removing…` 红 |
| 过期标出 | 改成永不过期 → `test_expired_knowledge…` 红 |
| 注销删除 | 去掉处置 → `test_account_erase_removes…` 红 |
| 仓库种子必须合格 | `test_every_repo_seed_is_valid`（skill `scenario-discovery` 的产出过这一关） |
| 响应形状 | `test_responses_match_sdk_types`：每个 Pack* 接口逐字段比 |
| 真浏览器 | `scripts/e2e_web.py`：打开服务包 → 启用 → 问协作顾问（出处 + 人工关口）→ 知识出现在知识库 |

## 7. 没做的

- **PACK-110 生成式回答与工具真执行**：现在助手是摘录式；接模型要先有运行合同、成本与日志（V153）。
- **PACK-111 场景包市场的第三方贡献**：现在只有平台运营能写包；外部作者投稿、分成与审核流程以后再做。
- 雷达还没接的信号：法律问答转律师的类别、客服未解决工单的类别（要先给这两处加聚合计数）。
- 包内定制代码：刻意不支持（安全）；缺工具就作为一批代码排进 BACKLOG（V149 记账底稿、V150 顺路匹配）。
- App 上的发单模板入口：App 的发布页目前只接类目参数。
