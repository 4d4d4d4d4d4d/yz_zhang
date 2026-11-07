# 241 接入方自己申请提额

> 状态：本批实现（V268）。编号 API-057。
> 来源：235 号 spec「没做的」——「接入方在开发者页自己申请提额（填用途与预计量），运营在后台批」；BACKLOG V268（第十一轮排期 12 分）。
> 只增不减：运营主动调配额（235 号）的接口与行为不变（写配额、审计、通知抽成一个共用的函数，批准申请也走它）；没申请过的用户导出与以前一样。
> 写明的行为变化：新表 `api_quota_requests`（迁移 c1d220260059）；新增 3 个开发者接口、3 个后台接口。

## 0. 要解决的问题

235 号让运营能给单个接入方调高账号每日总配额，但接入方没有入口：只能找客服、发邮件说明，运营再手工去调，来回几轮、没有记录。配额用完时接口直接 429，接入方的业务就停了。

## 1. 业界怎么做

云服务与开放平台普遍有「配额提升申请」：在控制台填想要的量、用途，平台审核后批准（可能批得比申请的少）或驳回，结果在同一页可见。（本批没有另找外部来源。）

## 2. 规则

- 接入方（至少有一把 API Key）在开发者页填：想要每天多少次（要比现在生效的高）、多少天（不填 = 长期）、用途（至少 10 个字）。
- 同一时间只能有一个待批的申请；待批的可以撤回。
- 运营（ops）在后台「开放 API 配额」看到待批申请：申请人、想要的量与天数、用途，附现在的配额与最近 7 天用量最多的一天。
  - **批准**：可以按申请的，也可以改量或天数；写进账号配额（与运营主动调同一处，同样进审计、通知对方），鉴权立刻按新配额算。
  - **驳回**：要写理由（至少 4 个字，对方会看到）；不动配额；进审计、通知对方。
- 已经有结果（批了、驳回、撤回）的申请不能再改。
- 两端开发者页与后台用同一句话描述一条申请（共享 SDK `quotaRequestLine`）。

## 3. 数据

`api_quota_requests`：申请人、想要的量与天数、用途、状态（pending / approved / rejected / withdrawn）、决定人与时间、备注或理由、实际批的量与天数。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。导出：本人有申请时多 `api_quota_requests`。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `POST /developer/quota-requests` | `{daily_quota, days?, purpose}` |
| `GET /developer/quota-requests` | 我的申请，最新的在前，最多 20 条 |
| `DELETE /developer/quota-requests/{id}` | 撤回待批的；别人的 404 |
| `GET /admin/api-quota-requests?status=pending` | ops；附 `current_quota`、`peak_7d` |
| `POST /admin/api-quota-requests/{id}/approve` | ops；`{note?, daily_quota?, days?}` |
| `POST /admin/api-quota-requests/{id}/reject` | ops；`{note}` 至少 4 个字 |

错误码（进 `i18n.ts`）：`api_quota_request_no_key`、`api_quota_request_not_higher`、`api_quota_request_pending`、`api_quota_request_decided`、`api_quota_reject_reason_required`。SDK：`requestApiQuota`、`myApiQuotaRequests`、`withdrawApiQuotaRequest`、`adminApiQuotaRequests`、`approveApiQuotaRequest`、`rejectApiQuotaRequest`、`ApiQuotaRequest`、`AdminApiQuotaRequest`、`quotaRequestLine`。登记：后台角色表、后台端点覆盖表、`DYNAMIC_BODY`（可选字段给了才带）、功能面清单。

## 5. 两端

- **Web 开发者页**：有 Key 时多「申请提高账号配额」一块：表单（待批时隐藏）、我的申请列表、撤回。
- **Web 后台「开放 API 配额」**：多「待批的提额申请」：批准（可改量）、驳回（要理由）。
- **App 开发者页**：有 Key 时多「申请提高账号配额」按钮，点开才加载（不多打请求）：表单、列表、撤回。

## 6. 隐私、授权与边界

申请只本人可见、可撤；后台只有 ops（及超级管理员）可看可批。用途是接入方自己写给平台的说明，不对外展示。钱无关；配额变化照旧进审计。

## 7. 闸门与红验

`server/tests/test_api_quota_requests.py` 2 条（没 Key、不比现在高、重复待批被拒；后台列表附现配额与 7 天峰值；批准可改量、天数沿用申请的、立刻生效、写配额与审计与通知；批过不能再批；导出；驳回要理由、不动配额；别人撤不了；撤回后不能批；角色）；`packages/core/src/apiQuotaRequest.test.ts` 3 条；`web/src/ApiQuotaRequests.test.tsx` 2 条；`app/quotaRequests.test.tsx` 1 条。

23 处变异（`scratchpad/mut268.py`）：22 处首轮变红；「批的天数不同也当按申请的」首轮存活，补一例后变红。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| API-058 | 新的提额申请提醒运营（现在要运营打开后台才看到），与申请超过若干天没处理的提醒 | 台账「欠」 |
