# 228 邀请链接的使用记录

> 状态：本批实现（V255）。编号 TEAM-068。
> 来源：147 号 spec「没做的」与台账 TEAM-068「邀请链接的使用记录（谁通过哪条链接加入）」；BACKLOG V255（第八轮排期 18 分）。
> 只增不减：邀请链接的生成、预览、加入、作废规则不变；生成与作废的响应不变。
> 写明的行为变化：`team_members.invite_id`（迁移 c1d220260050）；邀请链接列表每条多 `joined`；团队成员多 `invite_id`；有人通过链接加入时通知所有者。

## 0. 要解决的问题

一条能用 5 次的链接，后台只显示「已用 3/5」：是谁用的、什么时候进来的，所有者不知道；链接被转发给了不认识的人，也看不出来是哪条链接漏出去的、该作废哪条。

## 1. 业界怎么做

协作工具的邀请链接通常会记录「通过这条链接加入的成员」，并在有人加入时通知管理员，方便发现链接外泄后及时作废。（本批没有另找外部来源。）

## 2. 数据

`team_members.invite_id`（可空，有索引）：通过链接加入时记下链接编号；所有者手动加的为空。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 3. 接口

| 接口 | 变化 |
|---|---|
| `GET /teams/{id}/invite-links`（所有者） | 每条多 `joined`：`{user_id, nickname, joined_at, active}`，按加入时间先后；被移出或离开的 `active=false`，记录不消失 |
| `GET /teams/{id}` | 成员多 `invite_id` |
| `POST /team-invites/{token}/accept` | 加入时通知所有者：谁、通过哪条链接、用了几次、额度多少，不认识可以移出并作废链接 |

SDK：`TeamInviteJoin`、`TeamInviteLink.joined?`、成员 `invite_id?`；共享文案 `inviteJoinedLine`、`memberSourceLabel`。

## 4. 两端

- **Web** 团队页「邀请链接」：每条写编号与「已加入：小甲（日期）、小乙（已离开）」；成员表里写「通过邀请链接 #3 加入」。
- **App** 团队成员里写「通过邀请链接 #3 加入」。App 上不列链接清单（147 号的分工：App 生成并分享，清单与作废在 Web），所以链接维度的使用记录在 Web 看；加入通知两端都收得到。

## 5. 隐私、授权与边界

链接清单原本就只给所有者；使用记录只列团队里的成员（昵称与加入时间），不暴露别的信息。

## 6. 闸门与红验

`server/tests/test_team_invite_usage.py` 1 条；`packages/core/src/teamInviteUsage.test.ts` 2 条；`web/src/TeamInvites.test.tsx` 加 1 条；`app/appGaps.test.tsx` 加 1 条；响应形状闸门覆盖新类型。

12 处变异（`scratchpad/mut255.py`）全部首轮变红：不记来源、离开的不标、顺序反、不通知、列表不给、成员不给来源、文案三处、两端显示三处。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| TEAM-072 | App 上的邀请链接清单与作废 | 台账「欠」 |
