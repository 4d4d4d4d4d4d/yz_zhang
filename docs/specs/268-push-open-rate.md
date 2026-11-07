
# 268 推送点击率

> 状态：本批实现（V295）。编号 NTF-073（NTF-069 的推送点击率部分）。
> 来源：261 号 spec「没做的」——「推送点击率：从推送点进来的打开单独计数（App 打开通知时带上来源）」；BACKLOG V295。
> 只增不减：标已读接口不带 `via` 时行为与以前一样；推送附带的数据只在公告推送里多一个 `announcement_id`；`markRead(id)` 不传来源时请求不变。

## 0. 要解决的问题

V288 的阅读曲线能看出「一小时内有多少人点开」，但分不出是推送把人叫回来的，还是用户自己打开 App 在通知中心看到的。要判断推送值不值得发（推送按量计费、发多了用户会关），得先有这个数。

## 1. 业界怎么做

推送平台普遍把「推送打开率（点推送进入应用的人数 / 送达人数）」和「站内消息阅读率」分开统计，打开时由客户端带上来源回报。（本批没有另找外部来源。）

## 2. 规则

- 通知第一次点开时记下从哪里：`push`（点推送进来）/ `center`（在通知中心点开）；不说的（老客户端、本版之前的）为空。只记第一次。
- 公告的推送在附带数据里带上 `announcement_id`（发推送时通知 id 还没有）；App 点推送进来时报 `POST /notifications/push-opened {announcement_id}`，服务端把**自己那条**通知记成从推送点开；已经点开过的不改（`recorded=false`）；没收到这条公告的 404。
- 阅读曲线（261 号）多 `read_via_push`：点开过的人里从推送点进来的人数。

## 3. 数据

`notifications.read_via`（迁移 `c1d220260067`，默认空串）。随通知的既有处置走。

## 4. 接口

| 接口 | 说明 |
|---|---|
| `POST /notifications/{id}/read?via=push\|center` | `via` 可选（不传与以前一样） |
| `POST /notifications/push-opened` | 登录用户；`{announcement_id}` → `{notification_id, recorded}` |
| `GET /admin/announcements/{id}/read-curve` | 多 `read_via_push` |

SDK：`markRead(id, via?)`、`pushOpened(announcementId)`；`AnnouncementReadCurve.read_via_push`。

## 5. 两端

- **App**：`app/pushOpen.ts` 的 `reportPushOpened(client, data)`：推送数据里有正整数 `announcement_id` 才报，报失败不影响打开。接到 expo-notifications 的点击回调需要真机推送通道——与 `getPushToken` 同为「外」（NTF-075），SDK 方法已登记在待接表里。
- **Web 后台公告「看曲线」**：多一行「其中从推送点进来 N 人（只算报了来源的手机 App）」。

## 6. 隐私、授权与边界

只能报自己的通知；后台只看聚合数。

## 7. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_announcement_read_curve.py` 加 1 条（推送数据带公告 id、别的通知不多字段、push-opened 只记第一次、通知中心点开过的不算推送、via 校验、曲线计数、没收到的 404） | 7 处服务端变异：6 处首轮变红，1 处（所有通知都带 announcement_id）补用例后变红 |
| `app/pushOpen.test.ts`（2 条） | 2 处变异全部变红 |
| `web/src/AnnouncementReadCurve.test.tsx` 加断言 | 1 处变异补断言后变红 |

变异脚本：`scratchpad/mut295.py`、`mut295b.py`。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| NTF-075 | App 接 expo-notifications 的点击回调调用 `reportPushOpened`（要真机与推送通道） | 台账「外」 |
| NTF-076 | 送达到设备的数（推送供应商回执）与「推送打开率」的分母 | 台账「欠」 |
