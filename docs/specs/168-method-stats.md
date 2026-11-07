# 168 「我的方法」的效果统计

> 状态：本批实现（V195）。编号 AGT-095。
> 来源：164 号 spec 第 7 节「没做的」；BACKLOG V195；VISION V-7「经验作为检索库与 skill tool」。
> 只增不减：方法的增删改、蒸馏、套用到工作台与编排都不变；`NbMethod` 多五个只读字段。

## 0. 要解决的问题

- 164 号让「我的方法」能作编排的第一轮计划，但方法只记了「用过几次」：按它拆过的编排做成了没有、花了多少，看不到，也就不知道该不该接着用、该不该改。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 模板 / Playbook 的使用效果 | 自动化与项目管理工具常对模板给出「运行次数、成功率、平均耗时」，帮人淘汰不好用的模板 |
| 小样本不下结论 | 统计界面在样本太少时只给计数、不给比率（本平台能力画像 126 号 spec 同一条规矩） |

## 2. 数据

不新增表：按 `missions.method_id`（164 号）聚合，状态 `succeeded` 算做成，`failed`、`cancelled` 算没成，花费取 `spent_cents`（真实放款）。

## 3. 接口

| 接口 | 说明 |
|---|---|
| `GET /notebook/methods`（已有） | 每个方法多 `missions_total`、`missions_succeeded`、`missions_failed`、`missions_spent_cents`、`success_rate`（做完的少于 3 个为 null）；整页一次聚合查询，不按方法逐个查 |
| 新建 / 改方法的响应 | 同样带这五个字段（形状一致） |

## 4. 两端

- **Web 知识库「我的方法」**：「编排用过 N 次：做成 a、没成 b，花了 ¥x；成功率 y%」（做完的少写「做完的还少，先不算成功率」；没用过不显示）。
- **App 知识库「我的方法」**：同一句话。

## 5. 隐私、授权与边界

- 只统计本人的方法与本人的编排（方法与编排都只属于本人）。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_method_stats.py`） | 红验 |
|---|---|---|
| 计数、花费、做完 3 个才给成功率、取消算没成 | `test_stats_count_outcomes_and_spend_and_hold_back_the_rate_on_small_samples` | 小样本也给比率 → 红；取消不算没成 → 红；不算花费 → 红；不按方法过滤 → 红 |
| 按方法分开；新方法从零开始；响应形状一致 | `test_stats_are_per_method_and_new_methods_start_empty` | 列表不带统计 → 红 |
| 两端 | `web/src/Notebook.test.tsx`、`app/notebook.test.tsx` | — |

## 7. 没做的

- **AGT-097 方法版本与效果对比**：方法改过步骤后，新旧版本的效果混在一起算；要按版本分开才知道「改了之后有没有变好」（欠）。
- **AGT-096 修复步也参考方法里的备注**：仍然欠（164 号）。
