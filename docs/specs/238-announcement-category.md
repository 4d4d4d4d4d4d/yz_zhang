# 238 公告按类目定向

> 状态：本批实现（V265）。编号 NTF-068。
> 来源：159 号 spec「没做的」——「按类目定向（只发给做跑腿的人）」；BACKLOG V265。
> 只增不减：不选类目时，预览、发送、送达与以前完全一样（请求体也一样，不带 `category`）。
> 写明的行为变化：`announcements.category`（迁移 c1d220260056）；响应多 `category` 字段（空串 = 不限）。

## 0. 要解决的问题

159 号能按城市、人群定向，但「跑腿类接单规则调整」仍然会发给所有接单的人，包括只做设计的人。发给不相干的人，既打扰他们，也会让「公告」这类关不掉的通知越来越没人看（阅读率在 159 号已经能看到）。

## 1. 业界怎么做

推送与站内信的分群：在城市、身份之外按用户近期行为（最近在哪个类目活跃）圈人，是常规的分群维度；圈完先看人数再发。（本批没有另找外部来源。）

## 2. 规则

- 类目从平台类目表里选（Web 下拉），不在表里的类目拒绝（`announcement_bad_category`），避免写错字把人数圈成 0 还发出去。
- 类目与人群叠加：
  - 发单的人：近 180 天在这个类目发过单；
  - 接单的人：近 180 天在这个类目报过名（按报名时间算）；
  - 全体：两者之一。
- 城市、仅已实名照旧叠加在上面。
- 圈出来 0 人时，预览的提醒多一句「或者这个类目近 180 天没人发单 / 报名」。
- 定时公告到点发出时按创建时记下的类目圈人。

## 3. 数据

`announcements.category`（默认空串）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 4. 接口

| 接口 | 变化 |
|---|---|
| `POST /admin/announcements/preview` | 可选 `category`；返回多 `category` |
| `POST /admin/announcements` | 可选 `category`；审计里写明类目 |
| `GET /admin/announcements` | 每行多 `category` |

SDK：`AnnouncementPreview.category`、`AnnouncementRow.category`；`broadcastAnnouncement` / `previewAnnouncement` 的 `target` 多可选 `category`，给了才带（进 `DYNAMIC_BODY` 写明）。错误码 `announcement_bad_category` 进 `i18n.ts`。

## 5. 两端

- **Web 后台**「发布全站公告」多「只发给类目」下拉（不限类目 / 各类目）；预览写明「· 类目「X」」，发过的公告列表写明类目。
- **App**：后台只在 Web，不涉及。

## 6. 隐私、授权与边界

只有运营角色能发公告（与 159 号一样）；圈人只用平台内的发单 / 报名记录，不对外暴露名单，运营只看到人数。

## 7. 闸门与红验

`server/tests/test_announcement_category.py` 2 条（类目叠加人群的人数、400 天前的报名不算、送达按类目、列表与审计带类目、未知类目拒绝、不选不限）；`web/src/AnnouncementCategory.test.tsx` 1 条（不选不带 `category`、选了带上、预览与历史写明类目）。

16 处变异（`scratchpad/mut265.py`）：14 处首轮变红；「送达不按类目」首轮存活，补「设计类公告上海跑腿发单人收不到」后变红；「类目分支不提前返回」存活，属等价变异（类目条件已比不带类目的人群条件更窄，再叠一次结果不变），不补。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| NTF-070 | 公告按多个类目定向（一次选几个类目取并集） | 台账「欠」 |
