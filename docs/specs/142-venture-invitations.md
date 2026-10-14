
# 142 合作体邀请的另一半：我收到的邀请、拒绝、邀请成员与分配记录上两端

> 状态：本批实现（V170）。编号 COOP-060（含 COOP-060a~d）。
> 来源：台账 COOP-060「合作体邀请 / 加入 / 分配记录没上端：V75 建的那条线用户侧缺一半」；VISION V-3 高级协作；BACKLOG V170。
> 只增不减：邀请制、风险揭示书由本人签、邀请 7 天有效、只分已实现收益——这些规则一条不改；新增的是「列出我收到的邀请」与「拒绝」两个接口和两端界面。

## 0. 要解决的问题

COOP-021 定了邀请制（没有公开加入端点），邀请时会给被邀请人发一条通知。但是：

- **没有任何接口能列出「我收到的邀请」**——通知把人叫来了，点进去无处可接受（与 V91 APP-066 是同一类问题）；
- 不想加入也没法拒绝，邀请人那边一直挂着「待接受」；
- 邀请成员（`inviteToVenture`）、加入（`joinVenture`）、分配记录（`ventureDistributions`）三个 SDK 方法两端都没人调用。

## 1. 业界怎么做（带来源链接）

- 协作平台的邀请都是「站内可见的待处理邀请 + 接受 / 拒绝」两个动作，并且有有效期（例如 GitHub 的仓库邀请，<https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-access-to-your-personal-repositories/inviting-collaborators-to-a-personal-repository>：被邀请人在站内接受或拒绝，邀请 7 天过期）。
- 知情同意必须由本人作出：接受前整篇展示风险揭示书（59 号 spec 的做法），不能由邀请人代签。

## 2. 数据

无新表。`venture_invitations.status` 多一个取值 `declined`（原有 `pending / accepted`）。

## 3. 接口

| 编号 | 内容 |
|---|---|
| COOP-060a | `GET /ventures/invitations`：发给我的、待处理的、没过期的、合作体没关闭的邀请：合作体名称与目标、邀请人昵称、有效期、当前风险揭示书版本 |
| COOP-060b | `POST /ventures/{id}/invitations/decline`：只能拒绝发给自己的待处理邀请（`invitation_not_found`）；拒绝后不能再凭这张邀请加入（`invitation_required`），邀请人可以重新邀请 |
| COOP-060c | 两端接上邀请成员（按用户编号）与加入（服务端给的风险揭示书版本） |
| COOP-060d | 两端接上分配记录：每次分配的总额、备注、当时的份额快照 |

## 4. 两端

- **Web `/ventures`**：「我收到的邀请」一块（有邀请才显示）：读风险揭示书后加入（勾上「已阅读」才能签署）/ 拒绝；合作体详情里多「分配记录」与「邀请成员」。
- **App「我的 → 合作体」**：同样的「我收到的邀请」、详情里的分配记录与邀请成员（`app/ventureInvites.tsx`）。

## 5. 隐私、授权与边界

- 邀请列表只给被邀请人本人；分配记录只给成员（沿用 `_require_member`）。
- 加入照旧要求实名（`require_verified`）与当前版本的风险揭示书（`join_block`）。

## 6. 闸门与红验

7 处变异全部变红（`scratchpad/mut170.py`）：

| 闸门 | 红验 |
|---|---|
| 只列发给我的、待处理的 | 去掉被邀请人过滤 → `test_invitee_lists…` 红 |
| 过期的不列 | 去掉有效期过滤 → `test_expired_invitations_are_not_listed` 红 |
| 只能拒绝自己的待处理邀请 | 去掉被邀请人条件 → `test_decline_only_my_pending…` 红 |
| 拒绝后不能凭这张邀请加入 | 拒绝改成不改状态 → 同上红 |
| 两端签的是服务端给的版本、勾了已阅读才能签 | Web `VentureInvites.test.tsx`、App `app/ventureInvites.test.tsx` |
| SDK 分诊 | `inviteToVenture` / `joinVenture` / `ventureDistributions` 移出分诊表 |
| 响应形状 | `VentureInvitationView` |

## 7. 没做的

- **COOP-061 邀请时按昵称或手机号找人**：现在按用户编号邀请（与团队加人一致）；按手机号找人涉及号码枚举，要先定隐私口径（只匹配已同意被找到的人）。
- **COOP-062 邀请人看「我发出的邀请」及其状态（待接受 / 已拒绝 / 已过期）**。
