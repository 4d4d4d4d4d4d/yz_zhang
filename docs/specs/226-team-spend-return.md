# 226 团队拨款没用完的退回团队

> 状态：本批实现（V253）。编号 TEAM-070。
> 来源：170 号 spec「没做的」——「已划给成员但没用完的钱退回团队：要先定团队支出的报销与结算口径」；BACKLOG V253（第八轮排期 24 分）。
> 只增不减：支出申请、审批、执行、交接的原有行为不变；移出成员的响应与通知只多内容。
> 写明的行为变化：`team_spend_requests` 加 `returned_cents`（迁移 c1d220260048）；新账本科目 `team_return_in` / `team_return_out`；新接口两条。

## 0. 要解决的问题

团队支出执行时，钱从团队钱包划进成员的个人钱包，让他去发任务、托管。活动结束、任务取消退款、实际花得比申请的少——剩下的钱就留在他个人钱包里，以前没有任何路回到团队；人离开团队时也没人提这件事。

## 1. 口径（本批先定下的规则）

1. 钱划进个人钱包后与他自己的钱混在一起，平台分不出「哪一块是团队的」。所以**平台不替他判断用掉了多少，也不从他钱包里扣**：由发起人按实际没用完的退。
2. 一笔拨款最多退到拨款额（`return_exceeds_spend` 写明还能退多少）；只能退已执行的（`spend_not_executed`）；只能发起人自己退（403）；可用余额不够时说清钱可能在托管或冻结里、等结算或退款到账再退（`return_insufficient_balance`）。
3. 资金操作，强制带 `Idempotency-Key`（104 号）：同一个键重试回放，不会退两次；同一个键换金额是冲突。
4. 每次退都留流水：个人「退回团队」、团队「成员退回」；所有者收到通知，支出列表里写「已退回 ¥x」。
5. 已经离开团队的人也能退（钱是在团队时拨的）；离开时的通知写明「团队拨给你、还没退回的共 ¥x」和去哪里退。

## 2. 业界怎么做

企业费用管理里的「备用金 / 预支款」：先预支给员工，事后按实际花费核销，余额退回公司，未核销的余额在员工离职时结清。本平台没有发票核销环节（报销凭证不在平台上），所以只做「余额退回」这一半，核销留给团队自己的财务。（本批没有另找外部来源。）

## 3. 数据

`team_spend_requests.returned_cents`（默认 0）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。账本科目登记进 `LEDGER_KINDS` 与 `TRANSFER_KINDS`，中文名进 `ledger.ts`。团队支出记录属于团队账目，留存口径与团队流水相同（不随个人注销删除，原口径不变）。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `GET /teams/returnable-spends` | 团队拨给我、还能退回的支出（含已经离开的团队）：团队名、用途、拨款额、已退、还能退 |
| `POST /teams/{team_id}/spends/{request_id}/return` `{amount_cents}` | 退回；强制 `Idempotency-Key`；返回已退、还能退、我的可用余额 |
| `GET /teams/{id}/spends` | 每行多 `returned_cents`、`returnable_cents` |
| `DELETE /teams/{id}/members/{uid}` | 响应多 `unreturned_cents`；离开的人收到的通知写明没退回的金额 |

新错误码进 `i18n.ts`（两条消息带金额，进 `SERVER_WORDED_CODES`）。SDK：`ReturnableTeamSpend`、`TeamSpendReturned`、`SpendRequestView` 两个字段、`TeamMemberRemoved.unreturned_cents`、`returnableTeamSpends()`、`returnTeamSpend()`；共享文案 `teamReturnLine`、`teamReturnedNotice`、`TEAM_RETURN_HINT`。

## 5. 两端

- **钱包页「团队拨款」**（Web 与 App）：没有能退的不显示；每笔一行「某某科技 · 支出 #5（活动物料）：拨给你 ¥80.00，已退 ¥30.00，最多还能退 ¥50.00」，金额默认填最多能退的，可以改；「退回团队」用 `OperationKey.run`（断网重试同一个键）；退完写「已退回 ¥30.00，这笔还能退 ¥50.00」或「这笔拨款已全部退清」，并刷新钱包。放在钱包页而不是团队页，是因为离开团队的人进不了团队页。
- **团队页支出列表**（Web 与 App）：已执行的写「已退回 ¥x」。

## 6. 隐私、授权与边界

只有发起人能退自己那笔；所有者看得到退了多少，看不到他个人钱包的其他情况。平台不强制收回，也不判断「用掉了多少」——那是团队与成员之间的事。

## 7. 闸门与红验

`server/tests/test_team_spend_return.py` 3 条；`packages/core/src/teamReturns.test.ts` 2 条；`web/src/TeamReturns.test.tsx` 3 条；`app/teamReturns.test.tsx` 1 条；响应形状闸门覆盖四个类型。

20 处变异（`scratchpad/mut253.py`）：18 处首轮变红；「没执行的也算可退」「指纹不含金额」首轮存活，补「未执行的可退为 0」「同一个键换金额冲突」后变红。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| TEAM-071 | 所有者「催退」：对某笔拨款发一条提醒给发起人（现在只在移出成员时自动提一次） | 台账「欠」 |
