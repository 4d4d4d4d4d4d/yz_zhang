
# 282 响应头声明表与客户端读取的头自动对账

> 状态：本批实现（V309）。编号 CORS-002。
> 来源：160 号 spec「没做的」——「声明表与客户端读取的头自动对账：加一个闸门扫客户端代码里读的响应头，与 `EXPOSED_HEADERS` 对齐」；BACKLOG V309。
> 只增不减：`EXPOSED_HEADERS` 与 CORS 配置不变；只多一条测试。

## 0. 要解决的问题

浏览器跨域时，只有服务端在 `Access-Control-Expose-Headers` 里声明过的响应头才读得到。160 号把要读的头登记在 `app/main.py` 的 `EXPOSED_HEADERS`，靠的是「新加的头要登记」这句话；忘了登记，后端测试照样全绿（测试客户端不受跨域限制），只有真浏览器里分页总数、剩余次数读出来是 null。

## 1. 规则

- 扫 `packages/core/src`、`web/src`、`app` 里非测试的 `.ts / .tsx`：`headers.get('X')`、`headers?.get?.('X')` 读到的、带连字符的头名。
- 每一个都要在 `EXPOSED_HEADERS` 里（大小写不敏感），浏览器本来就能读的那几个（`Content-Type` 等 CORS 安全名单）除外。
- 扫描器必须认得出 SDK 读 `X-Total-Count` 的那一处（防止扫描规则失效后这条闸门什么都没查却照样绿）。

## 2. 数据 / 接口 / 两端

不涉及。

## 3. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_exposed_headers_reconcile.py` | 从 `EXPOSED_HEADERS` 去掉 `X-Total-Count` → 变红；在 Web 源码里加一处读 `X-New-Thing` → 变红并指出文件；都改回后变绿 |

## 4. 没做的

无新增欠账。
