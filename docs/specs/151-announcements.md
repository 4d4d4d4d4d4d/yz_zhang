# 151 全站公告的预览、定时与撤回

> 状态：本批实现（V179）。编号 NTF-064。
> 来源：台账 NTF-064「公告不能撤回 / 定时 / 预览——发出去收不回来」；BACKLOG V179。
> 只增不减：`POST /admin/announcements` 不填时间时照旧马上发，响应里原有的 `delivered` 不变（多了 `id`、`status`、`scheduled_at`）；后台「发布」按钮照旧一步可发。
> 写明的行为变化：每条公告都留一条记录并进审计（此前发了什么、发给谁、谁发的都查不到）；撤回会改写用户通知中心里那条通知的标题与正文。

## 0. 要解决的问题

- 公告按下就发：发给多少人只能发完才知道；发错了收不回来，只能再发一条更正——两条互相矛盾的通知并排躺在每个人的通知中心里。
- 没有定时：维护通知、节假日安排只能等到那个时间有人守着点。
- 没有记录：谁、什么时候、发给谁、送达多少人，事后都查不到，也不进审计。

## 1. 业界怎么做（带来源链接）

- **发前预览与受众人数**：邮件与站内信营销工具在发送前给出收件人数和预览（Mailchimp「Preview and test」：<https://mailchimp.com/help/preview-and-test-your-email-campaign/>）。
- **定时发送与取消**：Slack 的定时消息在发出前可改可删（<https://slack.com/help/articles/1500012915082>）；营销平台的定时活动在发出前可以取消。
- **撤回 / 更正**：站内消息可以撤回（如微信的消息撤回）；但系统推送一旦送达手机收不回来——Apple 与 Android 的推送都没有「召回」，只能再推一条。所以撤回只改平台内的通知，并在界面上说清楚。

## 2. 数据（迁移 `c1d220260029`，SQLite 与 Postgres 都验过）

| 表 | 字段 |
|---|---|
| `announcements`（新） | 标题、正文、仅已实名、状态（scheduled / sent / cancelled / revoked）、定时时间、发起人、创建 / 发出时间、送达人数、取消或撤回的人、时间与理由 |
| `notifications`（加列） | `announcement_id`：来自哪条公告（撤回时据此找到已送达的通知） |

## 3. 规则与接口

| 编号 | 内容 |
|---|---|
| NTF-064-1 | `POST /admin/announcements/preview`：受众人数（公告这一类用户关不掉，受众就是会收到的人）、用户看到的样子、要留意的地方（标题超过 20 字锁屏会截断、正文为空、像资金或合规类却发给全体）。不发、不落库 |
| NTF-064-2 | `POST /admin/announcements` 可带 `scheduled_at`：要晚于现在至少 1 分钟（`schedule_in_past`）、最多提前 30 天（`schedule_too_far`）；不带就马上发。每条留记录、进审计 |
| NTF-064-3 | `POST /admin/jobs/send-scheduled-announcements`（调度表每 5 分钟，`scheduled_announcements`）：到点的发出，每条只发一次 |
| NTF-064-4 | `POST /admin/announcements/{id}/cancel`：还没发出的定时公告可取消（否则 `announcement_not_scheduled`），进审计 |
| NTF-064-5 | `POST /admin/announcements/{id}/revoke`：已发出的可撤回，理由必填（`revoke_reason_required`，用户会看到）；已送达的通知标题改成「【已撤回】原标题」、正文改成「这条公告已撤回：理由」；同一个人的其他通知不受影响；进审计。不是已发出状态的不能撤回（`announcement_not_sent`） |
| NTF-064-6 | `GET /admin/announcements`：发过的公告，最新的在前，可按状态筛选 |
| — | 全部是运营角色（141 号角色总表已登记） |

## 4. 两端

- **Web 管理后台「全站公告」**：「预览」显示将送给多少人、用户看到的样子与要留意的地方；可填北京时间的定时；「发布」照旧一步可发；下面列出发过的公告（状态、时间、送达人数），定时的可「取消」，已发的可「撤回」（写理由，并说清推送收不回来）。
- **用户侧（Web 与 App 的通知中心）**：不需要改界面——撤回后那条通知本身就显示「【已撤回】」和理由，两端的通知列表都直接显示服务端的标题与正文。
- **App 管理后台**：管理后台只在 Web，不涉及。

## 5. 隐私、授权与边界

- 预览只返回人数，不返回名单。
- 撤回只改公告产生的那些通知（按 `announcement_id`），不碰用户的其他通知。
- 已经推到手机上的系统推送收不回来，界面撤回成功后明确说明，需要的话再发一条更正。

## 6. 闸门与红验

14 处变异全部变红（`scratchpad/mut179.py`）：

| 闸门 | 红验 |
|---|---|
| 仅已实名真的只算实名 | 去掉筛选 → `test_preview_counts_audience…` 红 |
| 标题太长要提醒 | 去掉 → 同上红 |
| 定时的先不发 | 去掉 scheduled 状态 → `test_scheduled_announcement_waits…` 红 |
| 定时在过去 / 超过 30 天被拒 | 去掉 → `test_schedule_must_be_in_the_future…` 红 |
| 只发到点的 | 放宽到明天 → `test_scheduled_announcement_waits…` 红 |
| 到点真的发出 | 去掉发送 → 同上红 |
| 已发的不能取消、未发的不能撤回 | 去掉 → `test_cancel…`、`test_revoke…` 红 |
| 撤回理由必填 | 去掉 → `test_revoke…` 红 |
| 撤回改写正文 | 去掉 → 同上红 |
| 通知记下公告编号 | 不记 → 同上红（撤回改不到） |
| 撤回进审计 | 去掉 → 同上红 |
| 只给运营 | 放宽到财务 → `test_only_ops_can_manage…` 红 |
| Web 预览 / 定时 / 取消 / 撤回 | `web/src/Announcements.test.tsx`；原有「发完回显送达人数」（`AdminOversight.test.tsx`）照旧通过 |

## 7. 没做的

- **NTF-066 公告按人群定向**：按城市、角色（接单者 / 发单者）、类目发；现在只有全体或仅已实名。
- **NTF-067 公告阅读率**：已读多少人；通知有已读位，但还没有按公告汇总。
