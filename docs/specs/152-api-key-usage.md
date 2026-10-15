# 152 API Key 用量与每日配额

> 状态：本批实现（V180）。编号 API-052（顺带 API-053 的一半：响应头带剩余配额）。
> 来源：145 号「没做的」API-052「集成方看不到自己用了多少」；台账 API-052；BACKLOG V180。
> 只增不减：每分钟限流（API-050）、429 + Retry-After、开发者设置原有的上限设置与轮换都不变；Key 列表多了两个字段。
> 写明的行为变化：开放 API 的每个请求多一道每日配额（平台默认每把 Key 每天 2 万次，北京时间按天）；每个请求在鉴权时多记一笔用量并当场提交。

## 0. 要解决的问题

- V173 有了每分钟限流，但集成方**看不到自己用了多少**——为什么被 429、一天大概打多少次，只能自己记。
- 每分钟 120 次的限流之内，一个跑飞的循环一天照样能打十几万次；平台没有「一天最多多少」这道闸。
- 被挡回去的请求没有任何记录：集成方不知道自己有多少请求根本没进来。

## 1. 业界怎么做（带来源链接）

- **每日配额 + 用量面板**：Google Cloud 每个 API 有按天的配额与用量图（<https://cloud.google.com/docs/quotas/view-manage>）；高德开放平台按 Key 的日配额与用量统计（<https://lbs.amap.com/api/webservice/guide/tools/flowlevel>）。
- **响应头告知剩余**：GitHub 用 `X-RateLimit-Limit / Remaining / Reset`（<https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>）。
- **配额超限回 429 并告诉何时恢复**：RFC 6585 的 429 + `Retry-After`。
- **按自然日重置并写明时区**：国内平台普遍按北京时间零点重置。

## 2. 数据（迁移 `c1d220260030`，SQLite 与 Postgres 都验过）

| 表 | 字段 |
|---|---|
| `api_keys`（加列） | `daily_quota`：这把 Key 自己的每日配额，0 = 用平台默认 |
| `api_key_usage`（新） | Key、日期（北京时间 YYYY-MM-DD，与 Key 一起唯一）、`count`（进到接口的）、`rejected`（被每分钟限流或每日配额挡回去的） |

配置：`API_KEY_DAILY_QUOTA`（默认 20000）。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| API-052-1 | 开放 API 鉴权时先过每分钟限流（被挡记一次 `rejected`），再记一次用量：`UPDATE … count = count + 1` 之后读回；超了就撤回这一次、记一次 `rejected`、回 429 `api_key_quota_exceeded`，`Retry-After` 是到北京时间下一个零点的秒数 |
| API-052-2 | 每个通过的请求带 `X-Quota-Limit`、`X-Quota-Remaining` 响应头 |
| API-052-3 | 用量与被挡记录是独立记账，当场提交（登记在 CONC-067 的 CHECKPOINTS）：接口后面失败也算用过一次，被挡回去的那次也留下 |
| API-052-4 | `PUT /developer/api-keys/{id}/quota`：只能设得比平台默认低（`api_key_quota_above_cap`），0 = 恢复默认；平台默认后来调得比它还低时按平台的算 |
| API-052-5 | `GET /developer/api-keys/{id}/usage?days=14`（最多 90 天）：今天已用 / 配额 / 剩余、下一次恢复时间、时区，以及每天进来多少、挡回多少（没有记录的天补 0，最近的在前）；只有 Key 的主人能看 |
| API-052-6 | 轮换不改配额，也不清零当天用量（否则轮换一次就绕过了每日配额） |

## 4. 两端

- **Web「开发者」**：每把生效中的 Key 下面显示「今天（北京时间）已用 X / Y 次（平台默认配额 / 你设的配额），还剩 Z 次，几点恢复」、可设更低配额，以及最近 14 天每天进来与挡回的表（带一条横条，挡回的天标成橙色）。
- **App「我的 → 开发者」**：每把 Key 下同样的一行今天用量、最近 7 天进来与挡回、设更低配额。

## 5. 隐私、授权与边界

- 用量只按 Key 和天汇总，不记请求内容、不记调用方 IP。
- 只有 Key 的主人能看用量、改配额（别人 404，不暴露 Key 是否存在）。
- 配额是「每把 Key」的；同一个人建多把 Key 可以叠加——按账号的总配额见第 7 节。

## 6. 闸门与红验

12 处变异全部变红（`scratchpad/mut180.py`）：

| 闸门 | 红验 |
|---|---|
| 按北京时间分天 | 改成 UTC 的日期 → `test_beijing_day_and_reset_time` 红 |
| 恢复时间是下一个零点 | 改成后天零点 → 同上红 |
| 平台默认后来更低时按平台的 | 去掉 min → `test_platform_cap_lowered_later_still_wins` 红 |
| 超额撤回这一次、记挡回 | 去掉撤回或挡回记录 → `test_quota_exhausted…` 红 |
| 超额回 429 | 去掉 → 同上红 |
| 被每分钟限流挡回也记 | 去掉 → `test_rate_limited_requests_are_recorded…` 红 |
| 只能设得更低 | 去掉 → `test_owner_can_lower_but_not_raise…` 红 |
| 只给主人看用量 | 去掉主人判断 → 同上红 |
| 轮换保留配额与当天用量 | 去掉任一 → `test_rotation_keeps_quota…` 红 |
| 没记录的天补 0 | 补成 1 → `test_old_days_are_reported…` 红 |
| 两端 | `web/src/ApiKeyUsage.test.tsx`、`app/apiKeyUsage.test.tsx`（载荷不对时不拖垮页面） |
| 原有行为 | `test_api_key_rate.py`、`test_open_api_webhooks.py` 照旧通过 |

## 7. 没做的

- **API-054 按账号的总配额**：一个人建多把 Key 可以叠加每日配额；需要时按账号再加一道。 → **已做**（V184，158 号 spec）。
- **API-055 用量记录的保留期**：`api_key_usage` 每把 Key 每天一行，增长很慢，暂未清理；到量时按 90 天清理（用量页最多也只看 90 天）。
- **API-053 的另一半**：每分钟限流的剩余次数（`X-RateLimit-Remaining`）还没给，只给了每日配额的剩余。 → **已做**（V180/V184，152/158 号 spec）。
