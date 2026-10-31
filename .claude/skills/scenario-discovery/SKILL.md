---
name: scenario-discovery
description: Discover, score and queue new user scenarios for the platform on your own initiative (not only what the user listed) — segment × job-to-be-done × pain frequency/severity × AI feasibility × commercial value ÷ delivery cost, with risk gates — using the vision, platform demand signals (scenario radar) and industry research; output scenario cards and scenario-pack definitions and insert them into docs/BACKLOG.md. Use at the start of each planning round and whenever the backlog runs low.
---

# 发掘场景，并把它变成可部署的场景包

用户原话（VISION 1.8）：「场景千变万化，可以提炼一些方法……快速发掘并部署方法到这个平台上……agent、skill、知识库就是平台重要的资产之一。」

## 1. 找信号（每轮都做）
- **愿景**：`docs/VISION.md` 1.6~1.8 的人群表。
- **平台数据**（场景雷达，管理后台「服务包 → 场景雷达」，`GET /admin/packs/radar`；只看聚合，每条至少 3 个不同的人，不看个人内容）：
  搜了没有供给的词、招募超过 3 天没人报名的类目、已上线的包答不上 / 没人觉得有用 / 知识过期。
  V167（153 号 spec）起雷达还会给出：法律问答答不上的主题（`legal_gap`）、客服没接住的工单主题（`support_gap`）；主题表在 `server/app/modules/packs/topics.py`，落到「其他」的多了就补主题词。
- **业界**：WebSearch 查同类平台与研究，带链接写进场景卡。

## 2. 写场景卡（每个候选一张）
人群 / 要办的事（job to be done）/ 现在怎么办（替代方案）/ 痛点：频率（天、周、月、年）与严重度（1~5）/ AI 能做到几成，哪些步骤必须由人做 / 商业价值（抽佣、订阅、增值服务）/ 交付成本（要写多少代码，还是只要写数据）/ 风险关口（资金、资质、医疗、法律意见、隐私）。

## 3. 打分排序
`分数 = 覆盖人数(1~5) × 频率(1~5) × 痛感(1~5) × AI 可完成度(0~1) × 商业价值(1~5) ÷ 交付成本(1~5)`
- 碰到资金、签署、申报、医疗、法律意见的，**必须有人工关口**，否则不上线。
- 需要外部持牌机构的，标「外」，只做平台内能做的那一半。

## 4. 变成场景包（优先写数据，少写代码）
一个场景包包含：
- **助手专家**：人设、方法步骤、可调用的平台工具白名单、人工关口、免责说明。
- **方法**：触发条件、步骤、完成标准、不适用的情形。
- **知识条目**：来源、有效期、适用地区。
- **任务模板和例行任务模板**。
- **指标**：启用数、完成率、转化到平台任务的数量。

引擎已上线（V148，123 号 spec）。**新场景的交付物就是一个文件**：
1. 写 `server/app/modules/packs/seeds/<key>.json`（文件名＝key）。格式见 `server/app/modules/packs/schema.py` 的 `PackDef`，
   参照现有的 `collab-basics.json`。字段：`key / title / segment / summary / pains / score / evidence / assistants / methods / knowledge / routines / task_templates`。
2. 本地校验：`cd server && python -m pytest tests/test_packs.py -k repo_seed`（格式 + 平台红线：工具白名单、人工关口、知识出处、政策有效期）。
3. 合入后，运营在管理后台「服务包」点「导入仓库里的种子包」→ 成为**草稿** → 提交审核 → **另一位管理员**上线（四眼，文件不能绕过）。
4. 上线后看后台的指标（在用、答不上、有用率）与「场景雷达」，答不上多的就补知识，过期的就更新——又回到第 1 步。

助手能用的工具只有 `schema.TOOLS` 里那几个（都是只读或只出草稿）。现有工具不够时，才把缺的工具作为一批代码排进 BACKLOG（例如 OPC 的记账底稿、接单者的顺路匹配）。

## 5. 入账
- 排进 `docs/BACKLOG.md`，写分数与「为什么排在这里」；在 `docs/VISION.md` 1.7 的人群表补一行。
- 场景卡写在对应批次的 spec 第 0、1 节。
