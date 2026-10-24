# 246 公告按多个类目定向

> 状态：本批实现（V273）。编号 NTF-070。
> 来源：238 号 spec「没做的」——「公告按多个类目定向（一次选几个类目取并集）」；BACKLOG V273。
> 只增不减：只选一个类目（或不选）时，请求体、预览、发送、列表与 V265 完全一样；`categories` 字段只在选了不止一个类目时出现。
> 写明的行为变化：`announcements.categories`（迁移 c1d220260061）；请求可带 `categories`（最多 10 个）。

## 0. 要解决的问题

238 号一次只能选一个类目。「上门类接单规则调整」要同时发给跑腿、家政、维修几类的人，只能发三条公告——同一个人做两类活就会收到两条一样的。

## 1. 业界怎么做

推送分群通常允许多个标签取并集（命中任一即发），且每人只发一次。（本批没有另找外部来源。）

## 2. 规则

- 主类目（`category`）之外可以「也发给」别的类目（`categories`），两者取并集、去重保序；每个类目都要是平台上有的。
- 人群照旧叠加：发单的 = 近 180 天在这几类里任一类发过单；接单的 = 报过名；全体 = 两者之一。
- 同一个人命中几个类目也只收到一次（按用户去重的查询本来就如此）。
- 只选了一个类目时不带 `categories`（与 V265 一样）；选了多个时预览、列表多 `categories`，审计写明全部类目。
- 定时公告到点发出时按创建时记下的全部类目圈人。

## 3. 数据

`announcements.categories`（JSON，可空）：选了不止一个类目时的全部类目（含主类目）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 4. 接口

| 接口 | 变化 |
|---|---|
| `POST /admin/announcements/preview`、`POST /admin/announcements` | 可选 `categories: string[]`（最多 10 个） |
| 预览与列表响应 | 选了多个类目时多 `categories` |

SDK：`AnnouncementPreview.categories?`、`AnnouncementRow.categories?`；`broadcastAnnouncement` / `previewAnnouncement` 的 `target.categories`（给了才带，`DYNAMIC_BODY` 已写明这两处的条件字段）。

## 5. 两端

- **Web 后台「发布全站公告」**：选了类目后多「也发给：」几个勾选；预览与发过的公告写明全部类目。
- **App**：后台只在 Web，不涉及。

## 6. 隐私、授权与边界

与 238 号相同：只有运营可发，运营只看到人数。

## 7. 闸门与红验

`server/tests/test_announcement_category.py` 加 1 条（只选一个不带 categories、多个取并集且去重、每个类目都校验、最多 10 个、送达按并集、列表与审计写明全部类目）；`web/src/AnnouncementCategory.test.tsx` 加 1 条。

11 处变异（`scratchpad/mut273.py`）：10 处首轮变红；「预览不带也发给的类目」首轮存活，补「勾了再预览」后变红。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| NTF-071 | 按类目定向的公告单独统计阅读率（哪一类的人点开得多） | 台账「欠」 |
