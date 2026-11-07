# 155 四眼按金额分级与第二人级别

> 状态：本批实现（V181）。编号 SEC-061f、PAY-042c。
> 来源：148 号「没做的」SEC-061f「四眼按金额分级」、PAY-042c「提现第二人与第一人的角色等级比较」；BACKLOG V181。
> 只增不减：提现与平台结算的两人确认门槛、同一个人不能确认自己（`same_approver`）、确认时再查余额都不变；列表多一个字段。
> 写明的行为变化：达到「超管确认线」（`SUPER_SECOND_APPROVAL_CENTS`，默认 ¥10 万）的提现与平台结算，第二位确认人必须是超级管理员；任何金额下，第二位确认人的级别不能低于第一位。

## 0. 要解决的问题

- V176 之后，大额提现与平台结算都要两位不同的财务先后确认。但一笔 ¥2 万和一笔 ¥200 万一视同仁：两位普通财务就能放出去。
- 超级管理员先批、普通财务「确认」的，等于下级给上级盖章，复核形同虚设。

## 1. 业界怎么做

- **分级授权（tiered approval / delegation of authority）**：按金额设审批权限，金额越大、要求的审批人级别越高，是企业资金内控的基本做法（COSO 内部控制框架，<https://www.coso.org/guidance-on-ic>；银行大额支付的分级授权）。
- **复核人不低于经办人**：maker-checker 中 checker 的权限不得低于 maker，否则复核没有约束力。

## 2. 数据

不加表。配置：`SUPER_SECOND_APPROVAL_CENTS`（默认 10000000 分 = ¥10 万）。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| SEC-061f-1 | 提现第二次确认、平台结算确认时：金额达到超管确认线，确认人必须有超级管理员角色（没分级的管理员按超级管理员对待，见 141 号），否则 403 `second_approver_role`，消息里的金额取自配置；钱不动 |
| PAY-042c-1 | 级别：超级管理员 2，其他角色 1。第二位确认人的级别低于第一位（提现的初次复核人 / 结算的发起人）时 403 `second_approver_rank` |
| SEC-061f-2 | `GET /wallet/withdraw-requests` 与 `GET /admin/platform-finance/settle-requests` 每行多 `needs_super_second`：这一笔要超级管理员作第二人 |
| — | 门槛以下、级别相当的，照旧两位不同的财务即可 |

## 4. 两端

- **Web 管理后台**：提现复核台「等待第二人确认」的那行、平台财务「待确认的结算」的那行，金额达到超管确认线时标出「金额较大：须超级管理员确认」。
- **App**：管理后台只在 Web，不涉及。

## 5. 隐私、授权与边界

- 只改「谁能当第二人」；第一步仍是财务角色（141 号角色总表）。
- 被拒的第二人不会让钱动：提现仍在等第二人、结算仍在等确认。

## 6. 闸门与红验

7 处变异全部变红（`scratchpad/mut181.py`）：

| 闸门 | 红验 |
|---|---|
| 达到线要超管 | 把线放宽十倍 → `test_large_withdraw_needs_a_super_admin_as_second` 红 |
| 第二人级别不低于第一人 | 去掉 → `test_second_cannot_rank_below_first` 红 |
| 超管级别高于其他 | 改成同级 → 同上红 |
| 提现接上检查 | 去掉 → 第一条红 |
| 结算接上检查 | 去掉 → `test_large_platform_settle_needs_a_super_admin_as_second` 红 |
| 列表标记只给大额 | 改成全标或门槛逻辑改坏 → `test_below_the_line…`、结算那条红 |
| Web 提示 | `web/src/TieredFourEyes.test.tsx` |
| 原有行为 | `test_four_eyes.py`、`test_settle_four_eyes.py`、`test_reminders_and_timeouts.py` 照旧通过 |

## 7. 没做的

- **SEC-061g 分级可配置成多档**：现在只有一条超管确认线；需要时做成金额档位表（例如 ¥50 万以上要两位超级管理员）。
- **PAY-042d 缴库的人工确认**：税款缴库是调度 job，没有人工四眼；要不要在缴库前加一步人工确认，需与财务流程一起定。
