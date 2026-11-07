# 227 工单里追加图片

> 状态：本批实现（V254）。编号 ESCA-057。
> 来源：166 号 spec「没做的」与台账 ESCA-057「工单里追加图片」；BACKLOG V254（第八轮排期 18 分）。
> 只增不减：不附图时提单与补充的请求体、行为都与以前一样；「只说谢谢不重开」（V246）照旧，只是带了截图的不算只说谢谢。
> 写明的行为变化：`tickets.images`、`ticket_replies.images`（迁移 c1d220260049）；工单相关响应多 `images`。

## 0. 要解决的问题

「提现页面报错」「订单金额显示不对」——用户只能用文字描述截图里的东西，客服第一句回复常常是「麻烦截个图」，而工单里根本没有地方放图。

## 1. 业界怎么做

客服工单系统普遍支持在工单与每条回复里附图片 / 附件，并限制数量与大小；附件只在工单的往来里可见。（本批没有另找外部来源。）

## 2. 数据

两张表各加一列 JSON `images`：存**图片名**（不是 url），读的时候拼成 `/api/v1/files/{name}`。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过；新用例在 Postgres 上也跑过。

## 3. 接口

| 接口 | 变化 |
|---|---|
| `POST /support/tickets` | 可选 `images`（上传接口返回的 url） |
| `POST /support/tickets/{id}/replies` | 可选 `images`；带了图就不算「只说谢谢」 |
| `GET /support/tickets` | 工单与每条往来多 `images` |
| `GET /admin/tickets/{id}` | 工单与每条往来多 `images` |

规则：一条最多 4 张（`ticket_too_many_images`）；只能附**自己上传过、非证件类**的图（`ticket_image_not_yours`：别人的、外链、不存在的、标为敏感材料的都拒绝）；同一张图只存一次；被拒的那次什么都不留。上传本身已过内容审核（UMOD），被拒的图根本不落库。

SDK：`MyTicket.images`、`TicketReplyItem.images`、`AdminTicketDetail.images`、`AdminTicketThreadItem.images`（都是可选，老服务端没有）；`createTicket(..., images?)`、`replyMyTicket(..., images?)`（不带图时请求体不变）。

## 4. 两端

- **Web**「我的工单」：提单表单与每张工单的补充旁都有选图（最多 4 张，提示「截之前请遮住卡号、证件号」）；工单与往来里显示缩略图，点开看原图。后台「看完整往来」里同样显示。
- **App**「找客服」：提单与补充都有「附截图」（相册选图，2MB 以内）；工单里写「附 N 张截图」（App 上不铺开大图）。

## 5. 隐私、授权与边界

- 图片走上传接口原有的能力 URL（名字来自 CSPRNG），url 只出现在提单人自己的工单与客服后台里。
- 证件类敏感材料（`sensitive`）不能附进工单——那类图有自己更严的读取规则，不能借工单把它带出来。
- 注销时没转纠纷的工单连同截图引用一起清掉（ESCA-055 原规则扩展）；数据导出包含图片名。

## 6. 闸门与红验

`server/tests/test_ticket_images.py` 3 条；`web/src/TicketImages.test.tsx` 2 条；`app/supportTickets.test.tsx` 加 1 条；响应形状闸门覆盖新字段；补救入口表登记 `ticket_image_not_yours`。

18 处变异（`scratchpad/mut254.py`）全部首轮变红：数量上限差一、不查归属、不查敏感、重复存、带图仍算谢谢、回复 / 提单不存图、列表 / 后台不给图、注销不清、导出不带、SDK 不带图、两端不显示 / 不发送。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| ESCA-062 | 客服回复时附图（现在只有提单人能附） | 台账「欠」 |
| ESCA-063 | App 上点开看大图（现在只写「附 N 张截图」） | 台账「欠」 |
