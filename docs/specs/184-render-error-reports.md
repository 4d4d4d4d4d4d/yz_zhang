# 184 页面渲染出错的上报

> 状态：本批实现（V212）。编号 APP-094。
> 来源：183 号 spec 第 5 节「没做的」——「APP-094 渲染错误上报到服务端（只报页面名与错误类型），运营能看到哪页常坏」；BACKLOG V212。
> 只增不减：错误边界（183 号）的替代界面不变；埋点表 `analytics_events` 原样复用，原有漏斗与热词不受影响。

## 0. 要解决的问题

183 号让一页出错不再整页白屏，但出错只有用户自己看见：运营不知道哪一页在坏、坏了多少人，只能等客服工单。

## 1. 业界怎么做

前端错误监控（如 Sentry 的 React 错误边界集成）在边界里捕获错误并上报，按页面与错误类型聚合（<https://docs.sentry.io/platforms/javascript/guides/react/features/error-boundary/>）。本批只做最小的那一半：不带堆栈与内容，只要「哪一页、哪类错、几个人」。

## 2. 数据

复用 `analytics_events`：`name = render_failed:<web|app>:<错误类型>`，`ref_type = 页面名`，`user_id` 只用于数不同的人。不加表、不加迁移。注销时埋点去掉与人的关联（153 号起已有）同样适用。

## 3. 接口

| 接口 | 说明 |
|---|---|
| `POST /client-errors` `{platform, page, kind}` | 登录与否都收（登录页也可能坏）；多收字段一律 422（不收错误内容）；页面名里的数字一律换成 `:id`，不像页面名的归成 `other`，不像错误类型的归成 `Error`；同一人同一页同类错误一分钟内只记一次；没登录的全站每分钟最多 100 条 |
| `GET /admin/client-errors?days=7` | 运营（ops）：平台 × 页面 × 错误类型的次数、不同的人数、最近一次，次数多的在前 |

SDK：`reportRenderError`、`adminClientErrors`、`ClientErrorRow`；后台板块 `clientErrors`（只给运营）。

## 4. 两端

- **Web**：`RouteBoundary` 接住错误后报一条，页面名用 `pageKey`（数字换 `:id`、团队邀请口令换 `:token`）；上报失败或报错都不影响说明卡。
- **App**：`ScreenBoundary` 同样，屏名是 `task` / `overlay-<种类>` / `tab-<页签>`（不带任务 id）。
- **Web 管理后台**：「页面出错（近 7 天）」表：端、页面、错误类型、次数、人数、最近一次。

## 5. 隐私与边界

- 不收错误信息、堆栈、页面数据；页面名在客户端与服务端各归一一次（服务端兜底：测试里 `/people/13800000001` 存成 `/people/:id`）。
- 没登录的上报可以被人编造：只设全站每分钟上限，并在后台看「人数」而不是只看次数。

## 6. 闸门与红验

11 处变异全部变红（`scratchpad/mut212.py`；首轮「人数去重」存活，补了同一人一分钟后再坏一次的用例后变红）：

| 闸门 | 测试 | 红验 |
|---|---|---|
| 聚合、人数去重、一分钟去重、没登录也收 | `server/tests/test_client_errors.py::test_reports_are_aggregated…` | 不去重 → 红；人数不去重 → 红 |
| 只留平台、页面、错误类型 | `test_nothing_but_platform_page_and_kind_is_kept` | 数字不换 → 红；页面不校验 → 红；错误类型不校验 → 红 |
| 没登录每分钟上限 | `test_anonymous_reports_are_capped_per_minute` | 去掉上限 → 红 |
| 只给运营、按天数窗口 | `test_only_ops_sees_the_summary…` | 不看时间窗 → 红 |
| Web 上报与后台 | `web/src/RouteBoundary.test.tsx`、`web/src/AdminClientErrors.test.tsx` | 不归一路径 → 红；不上报 → 红；板块给错角色 → 红 |
| App 上报 | `app/screenBoundary.test.tsx` | 上报出错把说明卡也带坏 → 红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| APP-097 | 某一页一天内坏的人数超过阈值时提醒运营（接入已有告警；原记作 APP-095，撞号后改） | 已做（V214，186 号） |
