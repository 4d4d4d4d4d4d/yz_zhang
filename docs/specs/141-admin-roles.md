
# 141 管理员分级：按职责在事前拦

> 状态：本批实现（V169）。编号 SEC-061b（含 SEC-061b-1~6）。
> 来源：台账 SEC-061b「管理员只有一个 `is_admin` 位：没有客服 / 仲裁 / 合规之分」；VISION V-11「管理员分级（SEC-061b）未做」；BACKLOG V169。
> 只增不减：所有管理员接口仍在、错误码 `admin_required` 照旧；**没分配过角色的管理员按超级管理员对待**，此前的全部管理员与运维脚本不受影响。
> 写明的行为变化：分配了角色的管理员只能做自己角色内的事，越权得到 403 `admin_role_required`（说清需要什么角色、你是什么角色）。

## 0. 要解决的问题

此前客服能批提现、运营能裁纠纷、任何管理员都能撤销别人的资质、读任何人的私聊与证件（V139 起要写理由并审计，但那是**事后**可查）。
商用上线前，后台必须按职责划分权限：一个账号被盗或一个人犯错，影响面要限在他的职责之内。

## 1. 业界怎么做（带来源链接）

- **最小权限与职责分离**：NIST SP 800-53 AC-5（Separation of Duties）、AC-6（Least Privilege），<https://csrc.nist.gov/projects/cprt/catalog#/cprt/framework/version/SP_800_53_5_1_1/home?element=AC-6>。
- **基于角色的访问控制（RBAC）**：OWASP Authorization Cheat Sheet 建议在服务端按角色/权限做检查、默认拒绝、集中实现，<https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html>。
- **兼容迁移**：存量管理员先按全权对待并在后台醒目标出「未分级」，由超级管理员逐个分配——避免上线当天把运营全部锁在门外。

## 2. 数据（迁移 `c1d220260023`，SQLite 与 Postgres 都验过）

| 表 | 新列 |
|---|---|
| `users` | `admin_roles`（JSON，默认 `[]`）：空 = 未分级，按超级管理员对待 |

注销处置：`admin_roles` 随 `is_admin` 一起清掉（E）。

## 3. 角色与接口

| 角色 | 职责 |
|---|---|
| `super` 超级管理员 | 全部权限，并且只有它能给管理员分配角色 |
| `support` 客服 | 工单、举报、查用户与封禁影响 |
| `arbiter` 仲裁 | 纠纷裁决与申诉复核；为举证读私聊与敏感材料（写理由、进审计） |
| `compliance` 合规 | 资质与团队企业核验、上传审核、反洗钱、封禁与解封、安全看板、审计日志；读私聊与敏感材料（写理由、进审计） |
| `finance` 财务 | 提现审批、平台财务与结算、结算核对、代扣台账、补贴池注资、手动触发对账 |
| `ops` 运营 | 类目、城市、撮合参数、公告、增长活动与优惠券、知识库、场景包、端侧模型、技能概念、平台 AI 助理、漏斗、死信 |
| 任何管理员 | 只读总览：指标、审核队列概览、供应商状态、北极星指标、角色说明 |

| 编号 | 内容 |
|---|---|
| SEC-061b-1 | `require_role(...)`：先是管理员（`admin_required`），再看角色（`admin_role_required`）；86 个管理员接口逐个声明，总表在 `tests/test_admin_roles.py::ROUTE_ROLES` |
| SEC-061b-2 | `GET /admin/roles`：角色说明与我的角色（任何管理员） |
| SEC-061b-3 | `GET /admin/admins`：管理员与角色、未分级人数（超级管理员） |
| SEC-061b-4 | `PUT /admin/admins/{id}/roles`：分配角色（超级管理员）；对象必须是管理员（`admin_target_not_admin`）、角色必须认识（`admin_role_unknown`）、至少留一位超级管理员（`admin_last_super`）；每次进审计（前 → 后） |
| SEC-061b-5 | 读他人私聊、读他人敏感材料：在「写理由 + 审计」之外，还要求「仲裁」或「合规」角色 |
| SEC-061b-6 | `/users/me` 多 `admin_roles`（生效角色） |

管理员身份本身（`is_admin`）仍由运维开通，后台只分配角色——开通管理员是比分配角色更高的权限，不放进网页。

## 4. 两端

- **Web 管理后台**：最上面一块「管理员与角色」——每位管理员看到自己的角色与各角色的职责；超级管理员看到全部管理员、未分级的醒目提示、勾选角色并保存。
- **App**：管理后台只在 Web（REACHED_BY），不涉及。

## 5. 隐私、授权与边界

- 拦在服务端；后台按角色决定显示什么只是为了不让人白点。
- 授权总表（`docs/AUTHZ-MATRIX.md`）3.2b 写明角色的定义与两项受限读取的角色要求。

## 6. 闸门与红验

12 处变异全部变红（`scratchpad/mut169.py`）：

| 闸门 | 红验 |
|---|---|
| 每个管理员接口都声明角色且与总表一致 | 把「批提现」改成财务或客服都行 → `test_every_admin_endpoint_declares…` 红 |
| 角色真的拦 | 去掉检查 → `test_roles_actually_block` 红 |
| 超级管理员包含一切 | 去掉 → `test_unclassified_admins_keep_full_access…` 红 |
| 未分级按超级管理员 | 去掉 → 同上红 |
| 至少留一位超级管理员 | 去掉 → `test_only_super_assigns_roles…` 红 |
| 分配进审计 | 去掉 → 同上红 |
| 私聊、敏感材料要仲裁或合规 | 各去一处 → `test_private_chats_and_identity_images…` 红 |
| 手动对账要财务 | 去掉 → `test_manual_reconcile_is_finance` 红 |
| 注销清角色 | 去掉 → `test_erasing_an_admin_clears_roles` 红 |
| `/users/me` 的生效角色 | 恒为空 → `test_unclassified…` 红 |
| Web 只有超级管理员去拉名单 | 恒拉 → `AdminRoles.test.tsx` 红 |
| 红线 | 动钱、裁决、资质决定、分配角色都不对「任何管理员 / 客服 / 运营」开放（`test_money_and_verdicts…`） |
| 原有行为 | 全部既有管理员测试照旧通过（测试里的管理员都是未分级） |

## 7. 没做的

- **SEC-061c 高风险动作的二次确认 / 四眼按角色**：提现审批、平台结算现在是一个有财务角色的人就能做；四眼原则（PAY-042b）要求「另一位财务」复核，排进待办。
- **SEC-061d 后台界面按角色隐藏板块**：现在所有板块都显示，没权限的点了会看到说清楚的 403；按角色隐藏要逐个板块改，价值低于服务端拦截，后做。
- **SEC-061e 角色的临时授予（带到期时间）**：例如临时请客服协助仲裁；要先定审批口径。
