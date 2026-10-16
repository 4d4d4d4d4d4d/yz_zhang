# 172 按类别和优先级的工单时限

> 状态：本批实现（V199）。编号 ESCA-052。
> 来源：150 号 spec「没做的」ESCA-052；BACKLOG V199；VISION V-21 客服与工单。
> 只增不减：不选类别的工单时限完全不变（首次响应 4 小时、处理 24 小时、48 小时升级主管），请求体也与以前一样；升级 job、首次响应、指派、追加回复都照旧，只是按每张工单的优先级取时限。

## 0. 要解决的问题

- 所有工单同一个时限：「提现三天没到账」和「怎么改头像」都是 4 小时首次响应、24 小时处理。钱和账号的事等 24 小时，用户会以为平台跑路了。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 按优先级的 SLA 策略 | 主流客服系统（Zendesk SLA policies、Freshdesk SLA）都按优先级 / 类别设不同的首次响应与解决时限 |
| 客服可调整优先级 | 用户选错类别很常见，客服按实际情况改，改动留痕 |

## 2. 数据

`tickets.category`（funds / account / general）与 `tickets.priority`（urgent / normal），迁移 `c1d220260039`；老工单默认 general / normal。

## 3. 规则与接口

| 项目 | 说明 |
|---|---|
| 提单 `POST /support/tickets` `{…, category?}` | 资金（提现、退款、到账）、账号（登录、安全）类自动加急；不选按一般；不认识的类别 400 `ticket_bad_category` |
| 时限 | 加急：首次响应 1 小时、处理 8 小时、16 小时升级主管（`PLATFORM_SUPPORT_URGENT_*` 可配）；一般不变 |
| 列表 | 我的工单与后台工单行都多 `category`、`priority`、`priority_label`，`sla_hours` / `first_response_hours` 是这张单自己的时限；后台「最急的在前」先排加急 |
| 升级 job | 每张单按自己的时限判超时与首次响应超时 |
| 客服调优先级 `POST /admin/tickets/{id}/priority {priority, reason}` | 客服角色；只对开着的单（`ticket_not_open`）；写审计（含理由），时限随之变化 |

## 4. 两端

- **Web 与 App「我的工单」**：提单时选「一般 / 资金 · 加急 / 账号 · 加急」；加急的单标「加急」。
- **Web 后台工单台**：加急标出来；「改成加急 / 改回一般」（写理由）。

## 5. 隐私、授权与边界

- 用户自选加急可能被滥用（什么都选资金）；客服可以改回一般并留痕。是否要统计「自选加急被改回」的比例来提示，另记 ESCA-060。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_ticket_sla_tiers.py`） | 红验 |
|---|---|---|
| 资金 / 账号类加急，时限变短；不选的不变；不认识的类别拒 | `test_funds_and_account_tickets_get_the_urgent_clock` | 加急不缩短时限 → 红；首次响应时限不变 → 红；不按类别定优先级 → 红；不拦类别 → 红 |
| 升级 job 按每张单自己的时限 | `test_escalation_job_uses_the_shorter_clock_for_urgent_tickets` | 升级用统一时限 → 红 |
| 客服改优先级：写理由、审计、时限跟着变；只有客服；已结的不改 | `test_support_can_change_priority_with_a_reason_and_the_clock_follows` | 不审计 → 红；已结也能改 → 红 |
| 「最急的在前」先排加急 | `test_urgent_comes_first_in_the_urgent_sort` | 不按优先级排 → 红 |
| 原有工单测试（24 小时等）全部照旧通过 | `test_ticket_escalation.py`、`test_ticket_assign_reply.py`、`test_ticket_user_reply.py` | — |
| 两端 | `web/src/TicketUserReply.test.tsx`、`app/supportTickets.test.tsx` | — |

## 7. 没做的

- **ESCA-060 自选加急的滥用提示**：统计每个人自选加急被客服改回的比例，过高时提单页提示（欠）。
- **ESCA-061 按类别分派客服**：资金类自动派给熟悉提现的客服（欠，要先有客服技能标签）。
