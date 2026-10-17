# 158 开放 API 按账号的总配额与每分钟剩余次数

> 状态：本批实现（V184）。编号 API-054、API-053。
> 来源：152 号「没做的」API-054「一个人建多把 Key 可以叠加每日配额」、API-053「每分钟限流的剩余次数还没给」；BACKLOG V184。
> 只增不减：每分钟限流（API-050）、每把 Key 的每日配额（API-052）、用量页都不变；多两个响应头、用量页多三个字段。
> 写明的行为变化：同一账号所有 Key 当天（北京时间）合计超过 `API_ACCOUNT_DAILY_QUOTA`（默认 5 万）后，开放 API 请求回 429 `api_account_quota_exceeded`。

## 0. 要解决的问题

- 152 号的每日配额是「每把 Key」的：建五把 Key 就有五倍配额，配额形同虚设。
- 每分钟限流只在超了之后告诉你；集成方没法提前放慢——GitHub、Stripe 等都在每个响应里给剩余次数。

## 1. 业界怎么做

- **按账号（项目）的总配额**：Google Cloud 的配额按项目而不是按 Key（<https://cloud.google.com/docs/quotas/overview>）。
- **每个响应带剩余次数**：GitHub `X-RateLimit-Remaining`（<https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>）；IETF 草案 RateLimit 头字段（<https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/>）。

## 2. 数据

不加表：账号合计从 `api_key_usage` 按 Key 的主人汇总（含已吊销、已轮换的 Key——吊销一把再建一把不清零）。配置：`API_ACCOUNT_DAILY_QUOTA`（默认 50000）。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| API-053-1 | 每个通过每分钟限流的开放 API 响应带 `X-RateLimit-Remaining`：本分钟还剩几次（Redis 与内存两种限流实现都能数） |
| API-054-1 | 记用量时同时算账号当天合计；超了就撤回这一次、记一次挡回（算在这把 Key 上）、回 429 `api_account_quota_exceeded`，`Retry-After` 到北京时间零点 |
| API-054-2 | 每个通过的响应带 `X-Account-Quota-Remaining` |
| API-054-3 | `GET /developer/api-keys/{id}/usage` 多 `account_today_used`、`account_daily_quota`、`account_today_remaining` |
| — | 只算本账号的 Key；别的账号不受影响 |

## 4. 两端

- **Web「开发者」与 App「开发者」**：每把 Key 的用量那一行后面写明「账号下所有 Key 今天合计 X / Y 次」。

## 5. 隐私与边界

- 只按账号与天汇总，不记请求内容。
- 账号合计是先加后判、不加锁的软上限：同一瞬间的并发请求可能多放过几次；每把 Key 的配额（行锁）仍是精确的。

## 6. 闸门与红验

7 处变异全部变红（`scratchpad/mut184.py`）：

| 闸门 | 红验 |
|---|---|
| 账号合计超了就挡 | 去掉判断或撤回 → `test_more_keys_do_not_add_up…` 红 |
| 只算本账号 | 去掉账号过滤 → `test_other_accounts_are_not_affected` 红 |
| 吊销的 Key 也算 | 只算生效中的 → `test_revoked_keys_still_count…` 红 |
| 回 429 | 去掉 → 第一条红 |
| 剩余次数头 | 写死或计数坏掉 → `test_rate_limit_remaining_header_counts_down` 红 |
| 两端 | `web/src/ApiKeyUsage.test.tsx`、`app/apiKeyUsage.test.tsx` 各加一条 |
| 原有行为 | `test_api_key_rate.py`、`test_api_key_usage.py` 照旧通过 |

## 7. 没做的

- **API-056 账号配额可按客户单独调高**：现在只有平台统一值；商务签约后要能给单个客户调高（后台操作、进审计）。
