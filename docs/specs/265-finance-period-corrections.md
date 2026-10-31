
# 265 锁账月份的更正说明（四眼）

> 状态：本批实现（V292）。编号 FIN-064。
> 来源：223 号 spec「没做的」——「锁账后发现快照本身有错时的更正流程（例如四眼批准后追加一条『更正说明』随报表导出），本批只允许在当期记调整」；BACKLOG V292。
> 只增不减：锁账规则不变（锁过的不能解锁，已出的数一分不变）；没有已批准的更正时，报表响应与导出与以前完全一样。

## 0. 要解决的问题

锁账之后，那个月的报表就是锁账时的快照。可快照本身也可能错（例如一笔补贴记成了其他调整）。以前只能在当期记一笔调整，看那个月报表的人（记账代理、审计）不知道它错过、错在哪、谁认可了这个更正。

## 1. 业界怎么做

会计上已结账期间的差错一般不改原账，而是在当期调整，并在报表附注里说明前期差错与更正；附注要经复核。（本批没有另找外部来源。）

## 2. 规则

- 只能给**已锁**的月份写更正说明；没锁的直接在当期记调整（400 `correction_period_not_closed`，写明该怎么办）。
- 说明至少 5 个字，写清哪里错、为什么；可以带一个差额（分，可正可负），只是说明，**不改报表的数**。
- 四眼：一位财务写，另一位财务批准（写的人自己批 → 400 `correction_same_approver`）；驳回别人写的要写理由，写的人可以自己撤回；处理过的再处理 → 409 `correction_already_decided`。
- 批准后：那个月的报表行多一个 `corrections` 列表（季度挂它三个月里的）；导出 CSV 的列不变，表尾另起一段列出这些期间里已批准的更正（月份、差额、说明、写的人、批准人、批准时间）。
- 写、批准、驳回都进审计。

## 3. 数据

新表 `finance_period_corrections`（迁移 `c1d220260066`）：月份、说明、差额、写的人、状态、处理人、理由、时间。是后台财务记录，不属于任何用户，不进用户的注销处置与数据导出。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `POST /admin/platform-finance/corrections` | 财务；`{period, note, amount_delta_cents}` |
| `GET /admin/platform-finance/corrections?status=` | 财务；默认等待批准的 |
| `POST /admin/platform-finance/corrections/{id}/approve` | 财务；不能是写的人 |
| `POST /admin/platform-finance/corrections/{id}/reject` | 财务；`{reason}` |
| `GET /admin/platform-finance/periods` | 有已批准的更正时，对应期间多 `corrections` |
| `GET /admin/platform-finance/periods/export` | 有已批准的更正时，表尾多一段 |

SDK：`requestFinanceCorrection` / `financeCorrections` / `approveFinanceCorrection` / `rejectFinanceCorrection`；类型 `FinanceCorrectionRow`、`FinanceCorrectionNote`，`PlatformFinancePeriod.corrections?`。登记：后台角色表、后台覆盖表、i18n（4 个错误码）、功能面清单。

## 5. 两端

- **Web 后台「平台财务 → 按期间」**：锁过账之后出现「更正说明」：选月份、填差额（元）与说明提交；下面列出等待批准的，可批准 / 驳回；批准后重新读报表，说明挂在那个月的行上。
- **App**：后台只在 Web，不涉及。

## 6. 隐私、授权与边界

只有财务角色；与平台结算同一套四眼思路（148 号）。更正说明不动钱、不改报表的数。

## 7. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_finance_corrections.py`（2 条：写 → 本人不能批 → 另一位批准 → 报表与季度与导出表尾、数字不变、审计；没锁的月份、说明太短、格式、驳回要理由、撤回、404、角色） | 9 处服务端变异：8 处首轮变红，1 处（季度只认年份）补用例后变红 |
| `web/src/FinanceCorrections.test.tsx`（2 条） | 4 处 Web 变异全部变红 |

旧测试 `test_finance_lock.py` 的导出表头断言（「…本期含补记以前期间（元）,自检」）不动，所以更正放在表尾而不是新加一列。变异脚本：`scratchpad/mut292.py`、`mut292b.py`。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| FIN-068 | 成交额与代扣税表（258 号）的更正说明 | 台账「欠」 |
| FIN-069 | 更正说明按金额分级要超级管理员批准（同 155 号的结算） | 台账「欠」 |
