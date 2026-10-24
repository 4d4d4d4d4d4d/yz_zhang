# 236 团队审批通知的轮流指派

> 状态：本批实现（V263）。编号 TEAM-064。
> 来源：台账 TEAM-064「审批通知群发给全体 owner/admin，没有轮值或指派」（75 号 spec 做了催办，轮值仍缺）；BACKLOG V263（第十轮排期 18 分）。
> 只增不减：默认（`all`）与以前完全一样：通知、催办都发给所有所有者与管理员；谁能审批不变。
> 写明的行为变化：`teams.approval_mode`、`team_spend_requests.assignee_id`（迁移 c1d220260054）；新接口 `PATCH /teams/{id}/approval-mode`。

## 0. 要解决的问题

每笔超额申请同时通知所有所有者与管理员。谁都收到 = 谁都不负责：常见的结果是都以为别人会批，员工的活卡在那里，直到催办或超时关闭。

## 1. 业界怎么做

审批流常见「指定审批人」或「轮流分配」，并设升级规则：分到的人一段时间没处理，就扩大到整个审批组。（本批没有另找外部来源。）

## 2. 规则

- 所有者可以把审批通知改成「轮流指派一人」（`rotate`）；默认「发给所有管理员」（`all`）。
- 轮流：在当前在职的所有者 / 管理员里（不含发起人自己），按用户编号依次轮，到底了从头开始。
- 通知只发给轮到的人（写明「轮到你审批；其他管理员也能批」）。
- 催办：第一轮只叫轮到的人；还没批，第二轮叫所有审批人，并写明「轮到某某审批还没处理，请其他管理员帮忙看一下」；轮到的人已经离开团队，第一轮就叫所有人。
- 任何审批人都能批（不是锁给轮到的人）；超时关闭规则不变。

## 3. 数据

`teams.approval_mode`（默认 `all`）、`team_spend_requests.assignee_id`（可空）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `PATCH /teams/{id}/approval-mode` `{mode: all\|rotate}` | 只有所有者 |
| `GET /teams/{id}` | 多 `approval_mode` |
| `GET /teams/{id}/spends` | 每行多 `assignee_id` |

SDK：`TeamDetail.approval_mode?`、`SpendRequestView.assignee_id?`、`setTeamApprovalMode()`。

## 5. 两端

- **Web 团队页**：所有者看到「审批通知：发给所有管理员 / 轮流指派一人」下拉；待审批的申请写「轮到 某某 审批」。
- **App 团队详情**：所有者一个按钮在两种方式间切换；待审批的申请同样写「轮到 某某 审批」。

## 6. 隐私、授权与边界

只改通知对象，不改权限。

## 7. 闸门与红验

`server/tests/test_team_approval_rotation.py` 4 条；`web/src/TeamAskReturn.test.tsx` 加 1 条；`app/team-approval.test.tsx` 加 1 条；原 `test_team_approval_notice.py` 照旧通过（默认不变）。

14 处变异（`scratchpad/mut263.py`）：13 处首轮变红；「轮到的人离开了还只叫他」首轮存活，补对应用例后变红。顺带修了一处 Web 的真问题：下拉框的值在 `await` 之后才读，受控组件已被重渲染回旧值，提示写反——改成先取值。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| TEAM-073 | 所有者手动把某笔申请改派给指定的人 | 台账「欠」 |
