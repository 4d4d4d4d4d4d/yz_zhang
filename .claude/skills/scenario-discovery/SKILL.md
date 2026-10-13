---
name: scenario-discovery
description: Discover, score and queue new user scenarios for the platform on your own initiative (not only what the user listed) — segment × job-to-be-done × pain frequency/severity × AI feasibility × commercial value ÷ delivery cost, with risk gates — using the vision, platform demand signals (scenario radar) and industry research; output scenario cards and scenario-pack definitions and insert them into docs/BACKLOG.md. Use at the start of each planning round and whenever the backlog runs low.
---

# 发掘场景，并把它变成可部署的场景包

用户原话（VISION 1.8）：「场景千变万化，可以提炼一些方法……快速发掘并部署方法到这个平台上……agent、skill、知识库就是平台重要的资产之一。」

## 1. 找信号（每轮都做）
- **愿景**：`docs/VISION.md` 1.6~1.8 的人群表。
- **平台数据**（场景雷达，只看聚合，不看个人内容）：搜不到结果的词、招募超过 3 天没人报名的类目、法律问答转律师或拒答的问题类别、客服没解决的工单类别、工作台里最常见的任务主题（只用聚合计数）。
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

场景包引擎上线后（BACKLOG 中的「场景包引擎」），新场景只需要一份场景包数据，审核后上线；现有能力不够时，才把缺的工具作为一批代码排进 BACKLOG。

## 5. 入账
- 排进 `docs/BACKLOG.md`，写分数与「为什么排在这里」；在 `docs/VISION.md` 1.7 的人群表补一行。
- 场景卡写在对应批次的 spec 第 0、1 节。
