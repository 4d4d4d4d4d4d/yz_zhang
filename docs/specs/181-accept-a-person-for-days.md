# 181 发单人一次选同一个人的多天

> 状态：本批实现（V208）。编号 SCN-126。
> 来源：177 号 spec 第 7 节「没做的」——「SCN-126 发单人一次选同一个人的多天（现在逐个名额选）」；BACKLOG V208。
> 只增不减：单个名额上的「接受报名」接口与规则不变（规则抽成 `_accept_one`，两条路共用一份）；每个名额各一份合约，签署、托管、验收、放款都按名额。
> 写明的行为变化：多天名额上选了一人后，同一个名额上其他人的报名**挪到同一天下一个还在招、自己没报过的名额**，而不是像以前那样全部拒掉；那天没有空名额时照旧拒。

## 0. 要解决的问题

- 帮手一次报了三天（177 号），发单人要在三个名额上各选一次；名额是平铺的，发单人也看不出「这三份报名是同一个人」。
- 177 号让一次报多天的人都先落在那天第一个名额上。发单人在第一个名额选了 A，B 的报名被一并拒掉——B 本可以顶那天的第二个名额，等于白报。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 按人确认多个班次 | 灵活用工平台上，商家可以一次确认同一个人接的多个班次（Instawork 帮助中心 <https://help.instawork.com/en/articles/10113606-what-to-expect-a-guide-to-managing-shifts-with-instawork>） |

## 2. 数据

不加表、不加迁移：报名换个名额就是改 `applications.task_id`（仍是 pending）。

## 3. 接口

| 接口 | 说明 |
|---|---|
| `GET /tasks/{id}/applicants` | 只给发单人：多天母任务上，还在等选的报名按人分组 `[{applicant_id, nickname, days: [{date, task_id, application_id}]}]`，报的天数多的在前 |
| `POST /tasks/{id}/accept-person` `{applicant_id}` | 只给发单人：把这个人在各天的报名按日期逐个用 `_accept_one` 选上，各生成一份合约；选不上的那天（在途单到上限、名额已不在招……）逐日写进 `skipped` 并带原因，其余照选；一天都选不上 409 `nothing_to_accept` |
| `POST /applications/{id}/accept`（原有） | 规则不变；多天名额上多一步「同一天还有空名额就把别人的报名挪过去」 |

SDK：`dayApplicants`、`acceptPerson`、`DayApplicant`、`AcceptPersonResult`；1 个错误码进 i18n；对象级授权表登记两条。

## 4. 两端

- **Web 任务详情**：发单人在「按天看名额」下多一块「按人选」：「小王 · 01-06、01-07　[选 TA 的这 2 天]」，结果写明选上了哪几天（每天一份合约，去各名额签署、托管）、哪几天为什么没选上。
- **App 任务详情**：同一块（`TaskTreeBlock`）。

## 5. 边界

- 选人只是生成合约，不动钱：签署、托管仍逐份由发单人确认（「钱、签署……人确认」）。
- 不是发单人、没登录都看不到谁报了哪几天。

## 6. 闸门与红验

10 处变异全部变红（`scratchpad/mut208.py`；首轮 4 处存活：挪名额时没核对「停招」与「自己已报」、按人排序、App 非发单人的隐藏，补了用例后全红）：

| 闸门 | 测试 | 红验 |
|---|---|---|
| 按人分组、天数多的在前、一次选上各一份合约；同名额的其他人挪到同一天下一个名额 | `server/tests/test_accept_person.py::test_poster_sees_who_applied…` | 不挪 → 红；不排序 → 红 |
| 那天没空名额时照旧拒 | `test_without_a_free_slot_that_day…` | — |
| 挪时跳过停招的、自己已报的名额 | `test_moved_application_skips_slots…` | 挪到第一个兄弟名额 → 红；不看是否在招 → 红 |
| 选不上的逐日说清；全选不上 409 | `test_days_that_cannot_be_accepted_are_explained` | 不捕获单日失败 → 红；不报 409 → 红 |
| 只给发单人 | `test_only_the_poster` | 去掉校验 → 红 |
| Web / App | `web/src/ApplyDays.test.tsx`、`app/applyDays.test.tsx` | 非发单人也显示 → 红；不说没选上的原因 → 红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| SCN-130 | 一次签署同一个人的多份合约（现在逐份签、逐份托管） | 意：签署与托管是钱和法律关口，逐份确认是有意的；可在 UI 上把这几份排在一起（欠，低优先） |
