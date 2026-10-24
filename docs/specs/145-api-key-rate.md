
# 145 开放 API 按 API Key 独立限流

> 状态：本批实现（V173）。编号 API-050（含 API-050a~d）。
> 来源：台账 API-050「没有按 API Key 的独立限流，走既有 IP + 账号限流」；BACKLOG V173「一个第三方集成跑飞会挤占同 IP 的所有人」。
> 只增不减：Key 的签发、轮换、吊销、scope 校验不变；站内（非开放 API）的写限流不变。
> 写明的行为变化：开放 API 超限回 **429**（此前站内限流回 400 `rate_limited`），带 `Retry-After`；开放 API 的写请求从站内共享的 IP 写额度里分出来，单独一个池。

## 0. 要解决的问题

- 开放 API 没有按 Key 的上限：一个集成写了死循环，它自己不受单独约束，耗光的是**同一出口 IP 后面所有人**（同一公司的真人用户）的写额度。
- 超限时回 400，集成方的 HTTP 客户端认不出这是「该退避」，常见的重试库只对 429 / 503 自动退避。
- 用户没法给测试环境的 Key 设一个更紧的上限。

## 1. 业界怎么做（带来源链接）

- **429 Too Many Requests + Retry-After**：RFC 6585 第 4 节（<https://www.rfc-editor.org/rfc/rfc6585#section-4>）；`Retry-After` 见 RFC 9110 第 10.2.3 节。
- **按凭证限流并在响应头告诉调用方额度**：GitHub REST API 按令牌计额度并返回 `x-ratelimit-limit` 等响应头（<https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>）；Stripe 按账户限流并要求集成方对 429 做指数退避（<https://docs.stripe.com/rate-limits>）。

## 2. 数据（迁移 `c1d220260024`，SQLite 与 Postgres 都验过）

| 表 | 新列 |
|---|---|
| `api_keys` | `rate_per_minute`（默认 0 = 平台默认） |

配置：`PLATFORM_API_KEY_RATE_PER_MINUTE`（默认 120，平台给每把 Key 的天花板）。

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| API-050a | 每把 Key 一个独立的每分钟计数（复用现有限流后端：Redis 共享、故障时回落内存）；超限 429 `api_key_rate_limited`，带 `Retry-After` 与 `X-RateLimit-Limit`；正常响应也带 `X-RateLimit-Limit` |
| API-050b | `PUT /developer/api-keys/{id}/rate-limit`：给自己的 Key 设更低的上限，0 = 恢复默认；高于平台天花板 `api_key_rate_above_cap`；只能改自己的 Key（别人的 404）；轮换时额度跟着新 Key |
| API-050c | 开放 API（`/api/v1/open/`）的写请求进单独的 IP 池，不再消耗站内真人共享的写额度；它自己的池仍有上限 |
| API-050d | `errors.too_many_requests`：429 的统一出口；i18n 闸门认得它 |

## 4. 两端

- **Web 开发者设置**与 **App「我的 → 开发者」**：每把 Key 显示「每分钟最多 N 次（平台默认 / 你设的），超了会收到 429 并告诉你几秒后重试」，可以设更低的上限。App 顺带补上了此前只有网页才有的「轮换」（旧 Key 立刻失效，新 Key 只显示这一次）。

## 5. 隐私、授权与边界

- 限流计数只按 Key 编号，不记任何请求内容。
- 需要更高额度走人工（联系平台），不开放自助提额：额度关乎平台稳定，也关乎滥用。

## 6. 闸门与红验

9 处变异全部变红（`scratchpad/mut173.py`）：

| 闸门 | 红验 |
|---|---|
| 按 Key 限流 | 去掉 → `test_each_key_has_its_own_minute_budget…` 红 |
| 按 Key 而不是按用户 | 改成按用户 → 同上红（同一用户的另一把 Key 不受影响） |
| 自己设的更低上限生效 | 恒用平台默认 → `test_owner_can_lower…` 红 |
| 不能高于天花板 | 去掉 → 同上红 |
| 轮换保留额度 | 去掉 → 同上红 |
| 开放 API 写请求单独一池 | 合回共享池 → `test_open_api_writes_do_not_eat…` 红 |
| 429 带 Retry-After | 去掉 → `test_each_key…` 红 |
| 两端显示来源、保存的是填的数 | `ApiKeyRate.test.tsx`、`app/apiKeyRate.test.tsx` |
| 原有行为 | `test_open_api_webhooks.py` 全部照旧通过 |

## 7. 没做的

- **API-052 每日配额与用量页**：现在只有每分钟的上限；按日 / 按月的配额与「这把 Key 今天用了多少」要先有用量统计表。 → **已做**（V180，152 号 spec）。
- **API-053 `X-RateLimit-Remaining`**：Redis 固定窗口能给出剩余数，内存滑动窗口要另算；先给上限，剩余数排进待办。 → **已做**（V180/V184，152/158 号 spec）。
