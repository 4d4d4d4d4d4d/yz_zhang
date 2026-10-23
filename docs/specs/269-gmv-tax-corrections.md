
# 269 成交额与代扣税表的更正说明

> 状态：本批实现（V296）。编号 FIN-068。
> 来源：265 号 spec「没做的」——「成交额与代扣税表（258 号）的更正说明」；BACKLOG V296。
> 只增不减：V292 的更正说明不传 `report` 时行为与请求体都不变（就是平台收支表）；成交额与代扣税表没有已批准的更正时，响应与导出与以前一样。

## 0. 要解决的问题

V285 起锁账时成交额与代扣税表也一起锁住。这张表是给记账代理、报税用的，快照错了比平台收支表更要紧，可 V292 的更正说明只挂在平台收支表上。

## 1. 业界怎么做

同 265 号：已结账期间的差错不改原表，经复核的附注说明随报表给出。（本批没有另找外部来源。）

## 2. 规则

- 更正说明多一个「哪张表」：`platform` 平台收支表（默认）/ `gmv_tax` 成交额与代扣税表。四眼、说明长度、只给已锁月份等规则与 265 号相同。
- 写 `gmv_tax` 时，那个月锁账时必须一起锁了这张表（V285 之后锁的）；之前锁的月份这张表仍按最新流水现算 → 400 `correction_gmv_not_locked`，写明直接在当期调整即可。
- 两张表各挂各的：成交额表的期间行多 `corrections`（季度挂它三个月的），导出 CSV 表尾（口径与草稿提示之后）另列一段；平台收支表照旧。

## 3. 数据

`finance_period_corrections.report`（迁移 `c1d220260068`，默认 `platform`，V292 写过的都是平台收支表）。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `POST /admin/platform-finance/corrections` | 多一个可选 `report` |
| `GET /admin/platform-finance/corrections` | 每行多 `report` |
| `GET /admin/platform-finance/gmv-tax` | 有已批准的更正时，对应期间多 `corrections` |
| `GET /admin/platform-finance/gmv-tax/export` | 有已批准的更正时，表尾多一段 |

SDK：`requestFinanceCorrection(period, note, cents, report?)`（不传 report 时请求体不变，已登记在 DYNAMIC_BODY）；类型 `FinanceCorrectionReport`、`FinanceCorrectionRow.report`、`PlatformGmvTaxRow.corrections?`；i18n `correction_gmv_not_locked`。

## 5. 两端

- **Web 后台「按期间 → 更正说明」**：多「更正哪张表」下拉；待批准的写明是哪张表；批准后成交额表跟着重新读，更正挂在那个月上。
- **App**：后台只在 Web，不涉及。

## 6. 隐私、授权与边界

同 265 号：只有财务角色，四眼，不改已出的数。

## 7. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_finance_corrections.py` 加 1 条（两张表各挂各的、数字不变、导出表尾、不传默认平台收支表、V285 之前锁的月份不能写、不认识的表 422） | 6 处服务端变异全部变红 |
| `web/src/FinanceCorrections.test.tsx` 加 1 条 | 3 处 Web 变异全部变红 |

变异脚本：`scratchpad/mut296.py`、`mut296b.py`。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| FIN-069 | 更正说明按金额分级要超级管理员批准（沿用 265 号） | 台账「欠」 |
