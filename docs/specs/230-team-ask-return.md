# 230 所有者提醒退回团队拨款

> 状态：本批实现（V257）。编号 TEAM-071。
> 来源：226 号 spec「没做的」——「所有者『催退』：对某笔拨款发一条提醒给发起人（现在只在移出成员时自动提一次）」；BACKLOG V257（第九轮排期 18 分）。
> 只增不减：226 号的退回规则不变（平台不判断用掉多少、不扣钱）；支出列表原有字段不变。
> 写明的行为变化：`team_spend_requests.return_asked_at`（迁移 c1d220260051）；新接口 `POST /teams/{id}/spends/{rid}/ask-return`；支出列表多 `return_asked_at`。

## 0. 要解决的问题

V253 让成员能退回没用完的拨款，但只有成员离开团队时平台才自动提一次。活动结束了、钱还在成员那里，所有者只能私下去问；平台上没有一个「提醒他」的动作，也没有「我上次什么时候提醒过」的记录。

## 1. 业界怎么做

企业费用管理里，预支款到期未核销时由财务发「催还提醒」，并记录提醒时间、控制频率，避免反复打扰。（本批没有另找外部来源。）

## 2. 规则

- 所有者或管理员可以提醒；普通成员、发起人自己不行（403）。
- 只对还有可退的拨款提醒（`nothing_to_return`：没执行，或已经全部退回）。
- 每笔 **24 小时内最多一次**（`return_asked_recently`）。
- 发起人已经离开团队也能提醒；提醒只是一条通知：写明拨了多少、最多还能退多少、去钱包页「团队拨款」退——不扣钱、不替他判断。

## 3. 数据

`team_spend_requests.return_asked_at`（可空）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `POST /teams/{team_id}/spends/{request_id}/ask-return` | 返回 `{id, returnable_cents, return_asked_at}` |
| `GET /teams/{id}/spends` | 每行多 `return_asked_at` |

新错误码进 `i18n.ts`。SDK：`TeamReturnAsked`、`SpendRequestView.return_asked_at?`、`askTeamSpendReturn()`。

## 5. 两端

- **Web** 团队页支出列表、**App** 团队详情支出列表：所有者 / 管理员在还有可退的拨款旁看到「提醒退回」，提醒过的写「（上次 时间）」；点了提示「已提醒 #发起人 退回没用完的拨款」。普通成员看不到。

## 6. 隐私、授权与边界

只是通知；不动任何人的钱。频率限制防止反复打扰。

## 7. 闸门与红验

`server/tests/test_team_spend_return.py` 加 1 条；`web/src/TeamAskReturn.test.tsx` 2 条；`app/team-approval.test.tsx` 加 2 条；响应形状闸门覆盖新字段。

13 处变异（`scratchpad/mut257.py`）：12 处首轮变红；「一天」改成「一小时」首轮存活，补「23 小时前提醒过仍拒绝」后变红。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| — | 无 | — |
