
# 357 响应形状棘轮再降一批：78 → 44

> 状态：本批实现（V384）。编号 CLI-083b。
> 来源：台账 CLI-083b「响应形状仍有 78 个调用点未验证」；BACKLOG V384。客户端按 SDK 声明读响应，声明与真实返回分叉时，要么字段永远显示不出来，要么读到 undefined 白屏。
> 只增不减：SDK 只加字段、把读不出的写法改成等价的具名接口，不删任何字段与方法；服务端不改。

## 0. 要解决的问题

100 号 spec 的扫除闸门（`test_response_shape_sweep.py`）能静态读出一半接口的返回键；读不出的（返回 `dump_xxx(...)`、变量、`{**...}` 展开）要靠真实响应断言，否则只记个数、用棘轮钉住「只许降」。V339 停在 78 个。

这 78 个里有每天都会走到的接口：我的账户、钱包、协议与同意、私聊与会话、圈子、好友、报名、邀约、评价、团队与合作体、后台看板。

## 1. 做法

`server/tests/test_shape_sweep_v384.py` 对这些接口跑真实请求，用 `_assert_shape` / `_assert_inline_shape` 三个方向比：声明了没给、给了没声明、类型对不上。

## 2. 扫出来的问题

**SDK 漏声明、服务端一直在给（客户端看不见）**

| 接口 | 漏掉的字段 | 后果 |
|---|---|---|
| `circleMembers` | `role` | 圈子成员列表分不出谁是圈主、管理员 |
| `withdraw` | `payout_ref`（打款单号） | 提现到账后用户找银行对账时拿不出单号 |
| `listReviews` | `revealed`（双盲互评是否已揭晓） | 界面没法说「对方的评价要等你也评完或窗口到期才公开」 |

**SDK 声明的写法让闸门读不出任何字段（等于没检查）**

| 声明 | 原写法 | 改成 |
|---|---|---|
| `PersonalSpace`、`OwnSpace` | 写在一行里的接口 | 一行一个字段 |
| `BanImpactView.in_flight_contracts` | 多行内联 `Array<{…}>` | 具名接口 `BanImpactContract` |
| `conversations` | `Array<Conversation & {…}>` | 具名接口 `ConversationListItem`（附 `ConversationLastMessage`） |
| `myVentures` | `Array<VentureView & { role }>` | 具名接口 `MyVentureRow` |
| `myTeams` | `Array<TeamView & {…}>` | 具名接口 `MyTeamRow` |

改写前后 TypeScript 类型等价，Web 与 App 类型检查照过。

**测试写法与闸门对不上**：扫除闸门用正则认 `_assert_shape(第一个参数, "名字")`，第一个参数里有逗号（如 `client.get(url, headers=h).json()`）就认不出。本批的断言统一先赋给变量再比。这个偏差只会让计数偏高（偏保守），不会让没检查的算成检查过。

**V383 自己的两个**：`createRecipientLink`、`revokeRecipientLink` 返回用了 `{**link_row(...)}`，让计数从 78 涨到 80，补了真实响应断言（193d6a1）。

## 3. 结果

- 未验证调用点：78 → **44**；棘轮 `MAX_UNVERIFIED` 78 → 44。
- 新覆盖 34 个调用点：账户 10（me、updateMe、myReferrals、newcomerProgress、myTax、myAgreements、acceptAgreements、grantConsent、revokeConsent、sendSmsCode）、钱包 2、个人空间 3、社交 6（openDirect、sendMessage、createCircle、getCircle、circles、circleMembers）、列表 7（friends、myInvitations、myApplications、contractSignatures、conversations、listReviews、workedWith）、团队与合作体 3（createTeam、myVentures、myTeams）、后台 5（platformFinance、adminSecurity、banImpact、northStar、marketHealth）。

## 4. 两端

不涉及界面改动（SDK 类型改动两端类型检查照过）。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_shape_sweep_v384.py`（8 条）、`test_response_shape_sweep.py`（棘轮 44） | `scratchpad/mut384.py` 9 处：去掉三个补上的字段各红；把 `OwnSpace` 的字段删一个、`BanImpactContract` 改错一个键、`MyVentureRow` 去掉 `role`、`ConversationListItem` 去掉 `last_message` 各红；删掉一条真实响应断言，棘轮红（两处）。<br>首轮 3 处存活：封禁影响的测试里没有在途合约，嵌套字段比不到（补一份在途合约并断言列表非空后变红）；另两处是变异写法不对——闸门按文本数断言，改函数名不改计数，改成删断言行后变红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| CLI-083b | 还有 44 个调用点未验证 | 欠（下一批继续降） |
| CLI-083c | 扫除闸门按文本数断言：写在没被执行的函数里的断言也会被算作已检查 | 欠：改成只认 `test_` 函数里的调用（要先确认没有测试把断言放在辅助函数里） |
