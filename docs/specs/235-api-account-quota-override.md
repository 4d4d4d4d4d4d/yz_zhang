# 235 开放 API 账号配额按客户单独调整

> 状态：本批实现（V262）。编号 API-056。
> 来源：台账 API-056「账号配额可按客户单独调高」（158 号 spec 立账号总配额时留下的）；BACKLOG V262（第十轮排期 27 分）。
> 只增不减：没单独调过的账号照旧用 `PLATFORM_API_ACCOUNT_DAILY_QUOTA`；每把 Key 的每日配额与每分钟限流不变。
> 写明的行为变化：新表 `api_account_quotas`（迁移 c1d220260053）；后台新接口三条；用量接口多两项；后台多「开放 API 配额」一块（运营）。

## 0. 要解决的问题

158 号的账号每日总配额是一个全局配置。签了接入合同、量比默认大的客户，或要压测一周的客户，只能把所有人一起调高——等于把平台的总暴露面一起放大。

## 1. 业界怎么做

开放平台通常有默认配额，并允许按客户（账号 / 项目）申请提额；提额有记录、可以设有效期。（本批没有另找外部来源。）

## 2. 规则

- 运营（`ops` 角色）给某个账号单独设每日总配额（所有 Key 合计，按北京时间的天）：可以调高也可以调低；理由至少 4 个字；可设 1~366 天，到期自动回到默认。
- 改回默认要写理由。每次调整与改回都进审计、通知对方。
- 每把 Key 的每日配额上限（`API_KEY_DAILY_QUOTA`）不变：要用满调高后的账号配额，可以把量分到几把 Key 上（158 号：账号合计才是真正的上限）。

## 3. 数据

`api_account_quotas`：`user_id`（唯一）、`daily_quota`、`reason`、`set_by`、`set_at`、`expires_at`（可空）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `GET /admin/api-accounts/quotas` | 单独调过的账号：调到多少、默认多少、理由、到期、是否还生效、今天用了多少 |
| `PUT /admin/api-accounts/{user_id}/quota` `{daily_quota, reason, days?}` | 没有这个用户 404 |
| `DELETE /admin/api-accounts/{user_id}/quota?reason=` | 没调过 `api_account_quota_not_set` |
| `GET /developer/api-keys/{id}/usage` | 多 `account_quota_custom`、`account_quota_expires_at` |

后台角色表、入口表、分区表（`apiQuotas`，运营）已登记。SDK：`ApiAccountQuotaRow`、`apiAccountQuotas` / `setApiAccountQuota` / `resetApiAccountQuota`、`ApiKeyUsageView` 两个可选字段、共享文案 `accountQuotaNote`。

## 5. 两端

- **Web 后台「开放 API 配额」**（运营）：填用户编号、每日配额、有效天数、理由调整；列表写明调到多少、默认多少、今天用量、到期或「一直有效」、理由；「改回默认」要写理由。
- **用户一侧**（Web 开发者页、App Key 用量）：调过的写「平台为你单独调过账号配额（到 某日，之后恢复默认）」。

## 6. 隐私、授权与边界

只有运营能调；调整只影响这一个账号。

## 7. 闸门与红验

`server/tests/test_api_account_quota_override.py` 2 条；`packages/core/src/apiQuota.test.ts` 1 条；`web/src/ApiQuotas.test.tsx` 3 条；`app/apiKeyUsage.test.tsx` 加 1 条；响应形状闸门覆盖新类型。

15 处变异（`scratchpad/mut262.py`）：14 处首轮变红；「列表也给客服看」首轮存活（全量里角色表闸门会红，单测没覆盖），补「客服看不了列表」后变红。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| API-057 | 接入方在开发者页自己申请提额（填用途与预计量），运营在后台批 | 台账「欠」 |
