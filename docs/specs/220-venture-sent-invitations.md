# 220 邀请人看「我发出的邀请」

> 状态：本批实现（V248）。编号 COOP-062。
> 来源：142 号 spec「没做的」——「邀请人看『我发出的邀请』及其状态（待接受 / 已拒绝 / 已过期）」；BACKLOG V248（台账「欠」第七轮排期，分数 27）。
> 只增不减：邀请制（COOP-021）、被邀请人的列表 / 接受 / 拒绝（COOP-060）都不变；本批加一个只读接口。

## 0. 要解决的问题

142 号让被邀请的人看得到、接得了、拒得掉邀请。发邀请的那一侧却什么都看不到：对方接没接、拒没拒、7 天过没过期，只能去问。过期了也不知道该再邀一次。

## 1. 业界怎么做

团队协作产品的成员页普遍有「待处理的邀请」一栏，写明状态与发出时间，过期的可以重新发。本平台照做；重新邀请走原有接口（`invite_member` 本来就会把过期 / 拒绝的那条重置成待接受）。（本批没有另找外部来源。）

## 2. 数据

不加表：读 `venture_invitations`。待接受但过了 `expires_at` 的写成「已过期」（库里的状态不改）。

## 3. 接口

| 接口 | 说明 |
|---|---|
| `GET /ventures/{id}/invitations/sent` | 只给合作体成员；只列**本人**在这个合作体发出的邀请（别的成员发的不列，免得成员之间互看邀请了谁）；每条 `invitee_id`、`invitee_nickname`、`status`（`pending` / `accepted` / `declined` / `expired`）、`created_at`、`expires_at`、`accepted_at` |

SDK：`ventureSentInvitations(ventureId)`、`VentureSentInvitation`、`VentureInviteStatus`、`VENTURE_INVITE_STATUS_LABEL`（待接受 / 已加入 / 已拒绝 / 已过期（可以再邀一次））。

## 4. 两端

- **Web** 合作体详情「邀请成员」下面列「我发出的邀请」：昵称、状态、发出时间；发出新邀请后刷新。
- **App** 「邀请成员」块下同样一列。

## 5. 隐私与边界

只给本人看本人发出的；被邀请人的昵称本来就在平台公开资料里，不多给别的信息。

## 6. 闸门与红验

`server/tests/test_venture_sent_invitations.py` 1 条（待接受 / 已拒绝 / 已过期 / 已加入四种状态、只列本人发出的、不是成员看不到）；`web/src/VentureInvites.test.tsx`、`app/ventureInvites.test.tsx` 各扩展 1 条断言。

6 处变异全部变红：列出别人发的、不算过期、不查成员、Web 发出后不刷新、Web 不用状态中文、App 不加载。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| — | 无（撤回待接受的邀请：等有人要再加） | — |
