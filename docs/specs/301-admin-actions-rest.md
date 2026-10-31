
# 301 其余板块里的按钮逐个登记进按钮权限表

> 状态：本批实现（V328）。编号 SEC-061l。
> 来源：295 号 spec「没做的」——「把其余板块里的按钮逐个登记进 `ADMIN_ACTIONS`」；BACKLOG V328。
> 只增不减：谁看得到哪个按钮与以前完全一样；只是判断从页面里手写的 `isSuper` 换成共享 SDK 的登记表，闸门从此核得到。

## 0. 先盘点

把服务端角色表里比所在板块更窄的接口逐个对照后台页面：

| 接口（角色） | 在哪个板块（板块的角色） | 以前怎么收起 | 本批 |
|---|---|---|---|
| `GET /admin/support/agents` 及替人暂停 / 恢复、节假日录入 / 删除 / 导入（super） | 客服工单（support） | 页面里手写 `isSuper` | 登记为 `supportBoard`，页面改用 `canDoAdminAction` |
| `POST /admin/tickets/{id}/assign`（super） | 客服工单（support） | 295 号已登记；加载可指派的人仍用 `isSuper` | 改用 `canDoAdminAction(me, 'assignTicket')` |
| `PUT /admin/admins/{id}/roles`、临时角色（super） | 管理员与角色（所有管理员） | 用服务端返回的「我的角色」判断 | 不动（已由服务端驱动，不是页面手写） |

## 1. 业界怎么做

同 295 号。（本批没有另找外部来源。）

## 2. 规则

- `ADMIN_ACTIONS.supportBoard`：「管理客服排班与状态」，probe `GET /admin/support/agents`，角色超级管理员。
- 后台页面里不再有手写的角色判断（`isSuper` 已删掉，判断改走登记表）。

## 3. 数据 / 接口

不涉及。

## 4. 两端

- **Web 后台**：客服看得到工单板块，看不到「看客服状态」；超级管理员照旧看得到。
- **App**：后台只在 Web，不涉及。

## 5. 隐私、授权与边界

同 295 号：界面收起是方便，拦截在服务端。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_admin_sections.py`（295 号的两条闸门自动覆盖新登记的按钮） | 界面给多放客服 → 红；页面不再收起 → 红 |
| `packages/core/src/adminActions.test.ts` 加 1 条、`web/src/AdminActionsByRole.test.tsx` 加 2 条 | 2 处 Web 变异全部变红 |

变异脚本：`scratchpad/mut328.py`。

## 7. 没做的

无新增欠账。
