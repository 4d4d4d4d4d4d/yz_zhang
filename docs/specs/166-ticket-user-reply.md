# 166 提单人在工单里追加回复

> 状态：本批实现（V193）。编号 ESCA-056。
> 来源：157 号 spec 第 7 节「没做的」ESCA-056；台账「欠」第四轮排序第一（BACKLOG V193）；VISION V-21 客服与工单。
> 只增不减：客服回复、结单、指派、升级与 SLA 都不变；后台工单行多三个字段（`last_user_reply`、`last_user_reply_at`、`awaiting_staff`），`replies_count` 仍然只数客服的回复（以前表里只有客服的回复，口径不变）。

## 0. 要解决的问题

- 工单往来只有客服能回。用户想补一张截图说明、一个银行卡尾号，或者说「还是没到账」，只能再开一张工单：两张单可能落到两个客服手里，前一张的上下文就丢了。
- 后台工单台只显示「客服回了几次」，看不到提单人后来说了什么，也看不出这张单是不是在等客服。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 提单人回复会重新打开已解决的工单 | Zendesk 的默认行为：请求者回复「已解决」的工单会变回「打开」，社区里不少团队为「谢谢」这类回复误重开写了自动化（<https://support.zendesk.com/hc/de/community/posts/6716715016986-Stop-Thank-You-Responses-From-Reopening-Tickets-2024>）；已关闭的工单则建后续工单（<https://www.eesel.ai/blog/zendesk-ticket-views-solved-reopen>，厂商博客） |
| 后台标出「等客服回复」 | 主流客服系统都区分「等客服」与「等客户」两种待办状态，按最后一条消息是谁说的来判断 |

我们的取舍：已结 7 天内的追加会重新打开，更早的请新开一张并写上原单号；转了纠纷的到纠纷里补（仲裁员只看纠纷里的材料）。

## 2. 数据

不新增表。提单人的追加写进已有的 `ticket_replies`（`is_staff=false`），注销处置与数据导出照旧覆盖（160 号 spec 已经按工单清理往来）。

## 3. 接口

| 接口 | 说明 |
|---|---|
| `POST /support/tickets/{id}/replies` `{body}` | 只能是自己的工单（别人的 404）；空内容 409；转了纠纷 409 `ticket_in_dispute`（写明纠纷号）；已结超过 7 天 409 `ticket_closed_too_long`（写明原单号）；每张单最多追加 30 次（`ticket_reply_limit`）；已结 7 天内追加会重新打开；有接手人就通知他；返回工单行 + `reopened` |
| `GET /admin/tickets`（已有） | 多 `last_user_reply`、`last_user_reply_at`、`awaiting_staff`（最后一句是提单人说的） |

## 4. 两端

- **Web「我的工单」与 App「我的工单」**：开着或已结的工单下面都有「补充」框；已结的提示「补充说明会重新打开这张工单」；往来里列出「我」说的话。
- **Web 后台工单台**：显示「提单人补充（时间）：……」，最后一句是提单人说的标「提单人补充了，等你回」。

## 5. 隐私、授权与边界

- 只能往自己的工单里写；纠纷里的事到纠纷里补，不在工单里绕开仲裁。
- 每张单最多 30 次追加，防止刷屏；需要更多就新开一张。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_ticket_user_reply.py`） | 红验 |
|---|---|---|
| 追加进往来、通知接手人；后台看到这句、标出在等客服；客服回过之后不再算在等，提单人的话不算客服回复次数 | `test_user_reply_lands_in_the_thread_and_wakes_the_assignee` | 不通知 → 红；「在等」判断错 → 红；回复次数把提单人的也数进去 → 红 |
| 已结 7 天内追加重新打开；更早的要新开并写明原单号 | `test_reply_to_a_resolved_ticket_within_7_days_reopens_it_older_ones_need_a_new_ticket` | 不重新打开 → 红；不拦 7 天 → 红 |
| 只能是自己的工单；转纠纷后不能补；空内容；次数上限 | `test_only_my_ticket_not_after_dispute_not_empty_and_capped` | 不查归属 → 红；不拦纠纷 → 红；不限次数 → 红 |
| 对象级授权、补救入口登记 | `test_object_level_authz.py`、`test_remedy_ui.py` | — |
| 两端 | `web/src/TicketUserReply.test.tsx`、`app/supportTickets.test.tsx` | — |

## 7. 没做的

- **ESCA-057 工单里追加图片**：现在只能追加文字；截图要走上传与审核（与内容上传同一套），还没接（欠）。
- **ESCA-059 「谢谢」误重开**：业界的老问题——用户回一句「谢谢」也会把已结的单重新打开。现在照样会重开（宁可多开不漏）；可以加「只说谢谢就不重开」的判断，或让用户选「问题已解决 / 还没解决」（欠）。
- **ESCA-058 后台查看完整往来**：后台只看到提单人最新一句与回复次数，完整往来要到详情里看——后台还没有工单详情页（欠）。
