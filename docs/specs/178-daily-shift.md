# 178 多天名额的每天时段

> 状态：本批实现（V205）。编号 SCN-117。
> 来源：167 号 spec 第 7 节「没做的」——「SCN-117 每天的时段：只有日期没有几点到几点；时段写在说明里」；BACKLOG V205。
> 只增不减：不写时段时名额标题、截止时间、行为与原来完全一样；名额截止仍到那天北京时间 23:59:59（不因时段改动，免得进行中的活在开工时就被判逾期）。

## 0. 要解决的问题

- 「5 个人干 3 天」只写了哪几天，没写几点到几点。帮手在广场上看到的名额标题是「第 1 天（10-18）」，要点进去读说明才知道是上午还是全天，报名后才发现时间对不上。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 班次 = 日期 + 时段 | 灵活用工平台的每个班次都有开始与结束时间，帮手按时段挑（<https://help.instawork.com/en/articles/10113606-what-to-expect-a-guide-to-managing-shifts-with-instawork>） |

本批取：一单一个每天时段（北京时间 HH:MM～HH:MM，不跨夜），名额带着，标题写明。

## 2. 数据

`tasks.shift_start`、`tasks.shift_end`（String(5)，空表示没写）。迁移 `c1d220260042`（SQLite 与 Postgres 都 `upgrade head && check` 过）。

## 3. 接口

| 接口 | 说明 |
|---|---|
| `POST /tasks` | 多 `shift_start`、`shift_end`：两个一起写或都不写（`shift_incomplete`）；24 小时制 HH:MM（`shift_invalid`）；结束晚于开始（`shift_order`，跨夜拆成两天写）；首尾空白去掉再存 |
| 名额 | 带着同样的时段，标题「第 1 天（10-18 09:00–18:30）· 名额 1/2」 |
| 返回 `Task` 的接口 | 多 `shift_start`、`shift_end`（公开：是活的一部分） |

SDK：`Task` 与 `TaskCreateInput` 多两个字段；`shiftLabel`（多天写「每天 09:00–18:30」，单天写「时段 …」）两端共用；3 个错误码进 i18n。

## 4. 两端

- **Web 发布页**：「连续几天」旁多「每天从 … 到 …」（时间选择），写了才带。**Web 详情页**：「🕘 每天 09:00–18:30（北京时间）」。
- **App 发布页**：「每天几点开始」「每天几点结束」。**App 详情页**：同一句。

## 5. 边界

- 一单一个时段；每天不同时段的要分开发（见第 7 节）。
- 时段只是说明与匹配依据，截止与逾期判断不变。

## 6. 闸门与红验

12 处变异全部变红（`scratchpad/mut205.py`；最初去空白那处存活，补了用例并把入参长度放宽到 8 后变红）：

| 闸门 | 测试 | 红验 |
|---|---|---|
| 名额带着时段、标题写明 | `server/tests/test_task_shift.py::test_slots_carry_the_shift…` | 名额不复制 → 红；标题不写 → 红；响应不带 → 红 |
| 不写时与原来一样 | `test_without_a_shift_titles_and_fields_stay_as_before` | — |
| 成对、格式、先后 | `test_shift_rules` | 去掉成对 → 红；格式放宽 → 红；允许相等 → 红 |
| 去首尾空白 | `test_surrounding_spaces_are_trimmed_before_storing` | 不去 → 红 |
| 一句话 | `packages/core/src/slots.test.ts` | 单天也写「每天」→ 红 |
| Web / App | `web/src/MultiDayPublish.test.tsx`、`web/src/ApplyDays.test.tsx`、`app/taskShift.test.tsx` | 不带进请求 → 红；详情不显示 → 红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| SCN-127 | 每天不同时段（周六 9–18、周日 10–16） | 欠 |
| SCN-128 | 按时段撮合（帮手的可用时间与名额时段对上才推） | 欠：可用时段（V143）已有，要接进名额推荐 |
