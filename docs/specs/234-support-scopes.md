# 234 按类别分派客服

> 状态：本批实现（V261）。编号 ESCA-061。
> 来源：台账 ESCA-061「按类别分派客服」（172 号 spec 定了工单类别之后留下的）；BACKLOG V261（第九轮排期 9 分）。
> 只增不减：有接手人的工单只叫接手人（ESCA-051 不变）；没人声明负责类别时提醒对象与以前完全一样；队列默认不筛。
> 写明的行为变化：新表 `support_agent_scopes`（迁移 c1d220260052）；新接口 `GET/PUT /admin/support/my-categories`；队列多 `my_categories` 筛选。

## 0. 要解决的问题

没人接手的工单超时，提醒发给所有客服。「钱没到账」的工单叫醒了只会处理登录问题的人，懂资金的那位淹没在一堆提醒里；客服打开队列也只能一张张翻。

## 1. 业界怎么做

客服系统按「技能组 / 分组」分派：客服归属一个或几个组，工单按类别进组，提醒与队列都按组过滤；没有组覆盖时回落到全部。（本批没有另找外部来源。）

## 2. 规则

- 客服自己声明负责哪几类（资金 / 账号 / 一般，至少一类）；**没声明的视为什么都管**。
- 没人接手的工单超时（首次响应与一级升级）：优先提醒负责这一类的客服（含没声明的）；一个都没有就照旧叫全部——不能没人管。
- 有接手人的照旧只叫接手人。
- 队列「只看我负责的类别」：声明过才出现，勾上才筛。

## 3. 数据

`support_agent_scopes`：`user_id`（唯一）、`categories`、`updated_at`。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。声明进审计（`support_scope`）。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `GET /admin/support/my-categories` | `{categories, declared, labels}`；没声明时 `categories` 是全部、`declared=false` |
| `PUT /admin/support/my-categories` `{categories}` | 未知类别 `ticket_bad_category`；空 `support_categories_empty` |
| `GET /admin/tickets?my_categories=true` | 只列我负责的类别（没声明不筛） |

客服角色可用（后台角色表与后台入口表已登记）。SDK：`SupportScope`、`mySupportCategories()`、`setMySupportCategories()`、`adminTickets` 选项多 `my_categories`。

## 5. 两端

- **Web 后台工单台**：「我负责：□资金 □账号 □一般 保存」（没选过写「还没选，视为都管」）；声明过才出现「只看我负责的类别」。老服务端没有这个接口时不显示这一块。
- **App**：后台只在 Web，不涉及。

## 6. 隐私、授权与边界

只影响提醒的对象与队列筛选，不改变谁能处理工单（任何客服仍可以接手任何工单）。

## 7. 闸门与红验

`server/tests/test_support_scopes.py` 3 条；`web/src/SupportScope.test.tsx` 2 条；响应形状闸门覆盖 `SupportScope`。

12 处变异（`scratchpad/mut261.py`）全部首轮变红：没声明的当成不管、没人负责时不回落、不按类别挑、类别校验与非空校验、筛选不看声明、保存不改、角色放宽、Web 四处。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| ESCA-064 | 新工单进来时按类别自动指派给负责的客服（轮流 / 按负载），现在只影响提醒与筛选 | 台账「欠」 |
