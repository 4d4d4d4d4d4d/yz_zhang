# 171 管理员角色的临时授予

> 状态：本批实现（V198）。编号 SEC-061e。
> 来源：141 号 spec 第 7 节「没做的」；BACKLOG V198；VISION V-11 安全。
> 只增不减：整组设置角色（`PUT /admin/admins/{id}/roles`）照旧，并且明确：在那里设的都是长期角色（会清掉临时到期记录）；「至少留一位超级管理员」「没分配过角色按超级管理员对待」都不变。

## 0. 要解决的问题

- 值班、休假顶岗时只能永久加角色：顶岗结束忘了收回，权限就一直在那儿——权限蔓延是审计最常查出来的问题之一。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 即时 / 限时提权（just-in-time access） | 云厂商的 IAM 与特权访问管理（PAM）普遍支持「有期限的角色授予」：写明理由、到点自动失效、全程审计 |
| 不能限时授予「能授权的权限」 | 授权本身的权限要长期、明确地给，避免临时提权链 |

## 2. 数据

`users.admin_role_until`（JSON，`{角色: UTC 时间}`；不在里面的角色是长期的），迁移 `c1d220260038`；注销处置表登记为清空。

## 3. 规则与接口

| 项目 | 说明 |
|---|---|
| `POST /admin/admins/{id}/temporary-roles` `{role, hours, reason}` | 只有超级管理员；1~720 小时；不能临时给「超级管理员」（`admin_temp_super_forbidden`）；只能加在至少有一个长期角色的管理员身上（`admin_temp_needs_permanent`）；已经长期有的不再临时给（`admin_role_already_permanent`）；写审计（含理由），通知本人 |
| `POST /admin/admins/{id}/temporary-roles/{role}/revoke` | 只有超级管理员；提前收回；长期角色不在这里收（`admin_role_not_temporary`） |
| 生效 | `roles_of` 在每次判断权限时看到期时间：到点就不算。**分配过角色但全部到期的是「没有角色」，绝不落成「未分级 = 超级管理员」** |
| 显示 | `GET /admin/admins` 每位多 `temporary`（未到期的临时角色与到期时间）；`/users/me` 的 `admin_roles` 本来就是生效的角色，后台板块（165 号）跟着收起 |

## 4. 两端

- **Web 管理后台「管理员与角色」**：每位管理员下面列临时角色与到期时间、「提前收回」；有长期角色的显示「临时授予」（问角色、小时数、理由）。
- **App**：没有管理后台，不涉及。

## 5. 隐私、授权与边界

- 动权限的接口都只给超级管理员，并且进入「不对所有管理员开放」的红线清单（`test_money_and_verdicts_are_not_open_to_everyone`）。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_admin_temp_roles.py`） | 红验 |
|---|---|---|
| 临时角色生效、到点失效、`/users/me` 与名单跟着变；审计含理由；通知本人 | `test_temporary_role_works_until_it_expires_then_access_is_gone` | 不看到期 → 红；不写审计 → 红 |
| 全部到期的人没有角色，绝不变超级管理员 | `test_all_roles_expired_means_no_roles_never_super` | 去掉兜底 → 红 |
| 只有超级管理员能给；不能临时给超级管理员；要有长期角色；已长期有的不重复；时长上限 | `test_rules_super_only_no_temp_super_needs_permanent_role_and_hours_cap` | 每条规则去掉 → 红 |
| 提前收回；整组设置的都是长期角色 | `test_revoke_early_and_set_roles_makes_everything_permanent` | 收回不删角色 → 红；整组设置不清到期记录 → 红 |
| 角色表、红线清单、后台入口、注销处置表 | `test_admin_roles.py`、`test_admin_surface_coverage.py`、`test_account_deletion.py` | — |
| Web | `web/src/AdminRoles.test.tsx` | — |

## 7. 没做的

- **SEC-061i 临时提权的申请与审批流**：现在由超级管理员直接给；更严的做法是本人申请、另一位超级管理员批（与四眼同一思路）（欠）。
