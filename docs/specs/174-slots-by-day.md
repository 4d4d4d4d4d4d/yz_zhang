# 174 多天名额按天汇总：哪天还缺几个人

> 状态：本批实现（V201）。编号 SCN-116。
> 来源：167 号 spec 第 7 节「没做的」——「SCN-116 名额按天汇总：母任务详情还是一排名额，没有按天分组看『哪天还缺几个人』」；BACKLOG V201；VISION 1.7 小店临时帮手。
> 只增不减：`GET /tasks/{id}/tree` 原有字段不变，只多 `by_day` 与每个子任务的 `work_date`；项目型任务的子任务进度与驾驶舱照旧。
> 写明的行为变化：两端详情页以前**只有项目型**根任务才拉子任务进度；现在多人、多天的母任务也拉（共享 SDK `hasChildTasks`）。发单人能在详情页看到名额、点进去；发布方还会看到合作驾驶舱（与项目型同一块）。

## 0. 要解决的问题

- V194 上线「5 个人干 3 天」后，发单人最先问的是「哪天还缺几个人」。母任务详情只有一排 15 个名额，得自己数。
- 更糟的是：核对时发现两端详情页**只对项目型**任务拉子任务进度，多人、多天的母任务（`task_type` 是 service）一个名额都不显示——名额只在发布成功那一刻的响应里出现过。`people_needed` 早在 TASK-007 就存了，却从没给出去，客户端无从判断。
- Web 的合作驾驶舱在响应不像预期时会把整页带崩（App 的那块早有防护）。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 按班次看招满没有 | 灵活用工平台把每个班次作为一行：有人接了就把头像挂到班次上，没招满的可以取消重发（Instawork 帮助中心：<https://help.instawork.com/en/articles/10113606-what-to-expect-a-guide-to-managing-shifts-with-instawork>、<https://help.instawork.com/en/articles/2475608-can-i-edit-my-gig-after-i-create-it>） |

本批取「一天一行」：日期、名额、招到、还缺、做完、取消；标题旁一句「还有 N 天缺人」。

## 2. 数据

- 不加表、不加迁移。按天汇总是读时聚合（一次查出母任务的全部子任务，已有查询，无 N+1）。
- 任务详情多给 `people_needed`（列早就有）。

## 3. 接口

| 接口 | 变化 |
|---|---|
| `GET /tasks/{id}/tree` | 多 `by_day: [{date, slots, filled, open, done, closed}]`（按日期排，只算带日期的名额；没有就是空表）；每个子任务多 `work_date` |
| `GET /tasks/{id}` 等返回 `Task` 的接口 | 多 `people_needed` |

口径：**招到** = 有人接且没取消（做完的也算招到）；**还缺** = 仍在招募、没人接；**取消**（含到期没人接被下架的、接了又取消的）单独数，不算缺也不算招到；**做完**是招到里已完成的。

SDK：`TaskTreeChild`（原先内联在 `TaskTree` 里，单独命名后形状闸门能逐字段比）、`TaskDaySummary`；`daySummaryLine`、`daysStillShort`、`hasChildTasks`（`decompose.ts`，两端同一份）。

## 4. 两端

- **Web 任务详情**：子任务进度卡里多「按天看名额」：标题「还有 N 天缺人」或「每天的名额都招到人了」，下面一天一行「01-06 · 2 个名额：招到 1，还缺 1」。多人、多天的母任务也拉子任务进度；合作驾驶舱响应不对时不画。
- **App 任务详情**：同一块（`TaskTreeBlock`），多人、多天的母任务也显示子任务进度与驾驶舱。

## 5. 隐私、授权与边界

- `/tree` 的可见范围不变（原本就对登录用户公开进度与子任务标题）；按天汇总只是计数，不含接单人信息。
- 驾驶舱仍只给发布方（`_get_parent` 校验发布者）。

## 6. 闸门与红验

13 处变异全部变红（`scratchpad/mut201.py`）：

| 闸门 | 测试 | 红验 |
|---|---|---|
| 招到 / 还缺 / 做完 / 取消的口径 | `server/tests/test_slots_by_day.py::test_tree_groups_slots_by_day…` | 做完的不算招到 → 红；接了又取消的算招到 → 红；取消的算还缺 → 红；不数做完 → 红 |
| 按日期排而不是按名额 id | `test_days_come_out_in_date_order…` | 按插入顺序 → 红 |
| 单天多人没有按天汇总；详情给 `people_needed` | `test_single_day_multi_person_has_no_day_summary` | 删掉 `people_needed` → 红 |
| 一天一句话、还缺人的那几天、要不要拉子任务进度 | `packages/core/src/slots.test.ts` | 去掉多天 / 多人的判断 → 红；不缺人时仍写「还缺 0」 → 红 |
| Web 详情页拉得到、画得出 | `web/src/SlotsByDay.test.tsx` | 退回只有项目型才拉 → 红；不画按天那块 → 红 |
| App 详情页拉得到、画得出 | `app/slotsByDay.test.tsx` | 退回只有项目型才显示 → 红；不画按天那块 → 红 |
| 响应形状 | `_assert_shape(…, "TaskTree" / "TaskTreeChild" / "TaskDaySummary")` | — |

## 7. 没做的

- **SCN-117 每天的时段**：只有日期没有几点到几点（欠，沿用 167 号）。
- **SCN-118 一个人一次报多天**（欠，沿用 167 号）。
- **SCN-121 缺人的那天一键补招**：现在只看得见哪天缺人；「把这天没人接的名额再推一次 / 加价」要等补招规则（欠）。
