# 157 客服主管指派工单与首次响应时限

> 状态：本批实现（V183）。编号 ESCA-053、ESCA-054。
> 来源：150 号「没做的」ESCA-053「首次响应 SLA 与解决 SLA 分开计时」、ESCA-054「主管把工单指派给某位客服」；BACKLOG V183。
> 只增不减：认领、回复并结单、超时逐级升级（150 号）都不变；`Ticket.reply` 仍是最近一次客服回复；列表与「我的工单」多字段。
> 写明的行为变化：结单时的回复也记进工单往来（`ticket_replies`），并记为首次响应（如果之前没回过）。

## 0. 要解决的问题

- 客服只能「认领」和「回复并结单」：一张要查两天的单，提单人两天里一句话都收不到。
- 平台只承诺了「多久解决」（24 小时），没有承诺「多久有人回第一句话」——而用户最在意的往往是后者。
- 主管看到积压，只能挨个去叫人认领，不能直接指派。

## 1. 业界怎么做

- **首次响应时间（First Response Time）与解决时间分开**：Zendesk SLA 策略把 first reply time、next reply time、resolution time 分开设目标（<https://support.zendesk.com/hc/en-us/articles/4408829459866>）。
- **指派（assignment）**：Freshdesk、Zendesk 都支持主管或规则把工单指派给具体客服（<https://support.freshdesk.com/support/solutions/articles/37589>）。

## 2. 数据（迁移 `c1d220260031`，SQLite 与 Postgres 都验过）

| 表 | 字段 |
|---|---|
| `tickets`（加列） | `first_response_at`、`first_response_alerted_at` |
| `ticket_replies`（新） | 工单、作者、是否客服、内容、时间 |

配置：`SUPPORT_FIRST_RESPONSE_HOURS`（默认 4）。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| ESCA-053-1 | `POST /admin/tickets/{id}/reply`（客服）：先回一句、不结单；记进往来、通知提单人；第一次回复记为首次响应（之后不再改） |
| ESCA-053-2 | 结单（`resolve`）的回复也记进往来，并在之前没回过时记为首次响应 |
| ESCA-053-3 | 超时升级 job 增加首次响应检查：还开着、没人回过、已等首次响应时限 → 叫醒接手人（没人接手叫醒客服），每张单只叫一次；与解决时限的分级各算各的 |
| ESCA-053-4 | 后台列表与「我的工单」多 `first_responded`、`first_response_hours`、`first_response_overdue`；后台多 `replies_count`；「我的工单」多 `replies`（内容与时间，不含是哪位管理员） |
| ESCA-054-1 | `POST /admin/tickets/{id}/assign`（只有超级管理员 = 主管）：只能指派给有客服角色的管理员（`assignee_not_support`）；进审计（写明此前接手人）、通知被指派的人；之后超时提醒只叫醒被指派的人 |

## 4. 两端

- **Web 管理后台「待处理工单」**：每行写明「已回复 N 次 / 还没回过（首次响应时限 4 小时）」，超时的标红；「先回一句」按钮；主管多一个「指派给…」下拉（只列有客服角色的人）。
- **Web「客服」与 App「客服与工单」**：处理进度里多「客服已回复」；往来多于一条时逐条列出。

## 5. 隐私、授权与边界

- 提单人看到的是回复内容与时间，不是哪位管理员。
- 只有超级管理员能指派；被指派的人必须有客服角色。

## 6. 闸门与红验

9 处变异全部变红（`scratchpad/mut183.py`）：

| 闸门 | 红验 |
|---|---|
| 首次响应只记第一次 | 每次都改 → `test_reply_without_closing…` 红 |
| 回过话的不算首次响应超时 | 去掉 → `test_first_response_overdue_alerts_once…` 红 |
| 首次响应超时只提醒一次 | 去掉 → 同上红 |
| 时限按配置 | 改成六分之一 → 同上红 |
| 结单也记往来 | 去掉 → `test_resolving_directly_also_records_first_response` 红 |
| 只有主管能指派 | 放宽到客服 → `test_supervisor_assigns…` 红 |
| 只能指派给客服 | 去掉角色判断 → 同上红 |
| 指派进审计 | 去掉 → 同上红 |
| 不给提单人看管理员身份 | 多给作者编号 → `test_reply_without_closing…` 红 |
| 两端 | `web/src/TicketAssign.test.tsx`、`app/supportTickets.test.tsx`（新增往来一条） |

## 7. 没做的

- **ESCA-055 工单进数据导出与注销处置**：用户的工单与往来还没进 `/users/me/export` 和注销处置表（这一条在 V178 之前就欠着，这次一并记下）。
- **ESCA-056 提单人在工单里追加回复**：现在只有客服能回；用户要补充材料只能新开一单。
