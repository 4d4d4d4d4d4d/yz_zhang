# 222 断网或页面跳走时不清登录态

> 状态：本批实现（V249）。编号 REG-002。
> 来源：91136b8 的全量回归在真浏览器联调里红了（「个人空间」的输入框等不到——页面被弹回登录页）；二分到 V236 只是改变了时序，根因是 Web 的 `refreshMe` 对任何失败都清掉登录态。
> 只增不减：服务端拒绝登录（401、被踢下线、封号、注销）时照旧清掉并回登录页。
> 写明的行为变化：取当前用户时遇到断网、请求被取消、服务端 5xx、与登录无关的 403，不再清 token，保留登录态。

## 0. 要解决的问题

Web 的 `refreshMe` 在 `client.me()` 抛错时一律 `setToken(null)`。页面跳转时浏览器会取消还在路上的 `/users/me` 请求，这个取消也是一次「抛错」——于是一跳页就被登出。用户那一侧的表现就是「好好的突然回到登录页」；弱网、服务端短暂 5xx 也一样。App 根组件同样是 `.catch(() => setToken(null))`，手机信号一抖就登出。

## 1. 业界怎么做

常见做法是只在服务端明确表示凭据无效（401，或标明「会话已失效」的 403）时清掉本地凭据；网络错误与服务端错误保留登录态、提示重试。（本批没有另找外部来源。）

## 2. 数据

无。

## 3. 接口

不改服务端。共享 SDK 新增 `isAuthRejection(e)`（`packages/core/src/session.ts`）：只有 SDK 从服务端响应构造的 `ApiError`，且是 401，或 403 并且错误码是 `unauthenticated` / `session_revoked` / `account_banned` / `account_deleted`，才算「服务端不认这个登录」。

## 4. 两端

- **Web** `store.tsx` 的 `refreshMe`：只在 `isAuthRejection` 时清 token 与当前用户。
- **App** `App.tsx` 根组件：同样只在 `isAuthRejection` 时清 token。

## 5. 隐私、授权与边界

不放宽任何授权：服务端每个请求照旧校验 token；被踢下线、封号、注销的照旧立刻回登录页。保留的只是本地那份 token，下一次请求服务端仍然会拒。

## 6. 闸门与红验

`packages/core/src/session.test.ts` 2 条；`web/src/SessionKeep.test.tsx` 2 条（网络错误保留 token；403 unauthenticated 清掉）；`app/sessionKeep.test.tsx` 1 条（App 根组件没法在测试里注入已登录状态，守住 `catch` 用了共享判定）。全量回归里的真浏览器联调是这条的端到端验证。

| 闸门 | 红验（`scratchpad/mut249.py`） |
|---|---|
| 401 要清 | 去掉 401 → 红 |
| 403 只认登录类错误码 | 任何 403 都清 → 红 |
| 只认 SDK 的错误 | 去掉 `instanceof ApiError` → 首轮存活，补「带 status 的普通对象不算」后变红 |
| Web 用了判定 | 改回一律清 → 红 |
| App 用了判定 | 改回一律清 → 红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| — | 无 | — |
