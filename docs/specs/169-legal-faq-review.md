# 169 法律条目的有效期与到期复核

> 状态：本批实现（V196）。编号 LAW-062。
> 来源：163 号 spec 第 7 节「没做的」；BACKLOG V196（合规风险项提前）；VISION V-5a。
> 只增不减：法律知识库的草稿 → 审核 → 上线 → 下线流程不变；代码里的四条老常识不受影响（它们没有复核日期，迁进表是 LAW-061）。

## 0. 要解决的问题

- 法规会改、司法解释会更新。条目一旦上线就一直原样回答，没有人会记得一年后回头看它对不对——法律信息过期比答不上更糟：它看起来很权威。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 知识库文章的复核周期 | 合规要求高的知识库普遍给每篇文章设「下次复核日期」，到期前提醒负责人，过期的文章下架或标「待复核」 |
| 过期即停用而不是继续展示 | 法律、医疗这类内容宁可答不上（转人工）也不展示过期结论 |

## 2. 数据

`legal_faqs` 加 `valid_until`（复核日期）与 `review_stage`（提醒进度 0 / 1 / 2），迁移 `c1d220260037`。

## 3. 规则与接口

| 项目 | 说明 |
|---|---|
| 复核日期 | 草稿可以自己写（晚于今天、最多 2 年后，`legal_faq_bad_valid_until`）；上线时没写就默认一年后 |
| 过期 | 过了复核日期，问答不再用它：同样的问题回到「找律师」、重新记成答不上进雷达；后台标「已过复核日期，问答已停用」 |
| 提醒 | 新 job `POST /admin/jobs/remind-legal-reviews`（每天）：到期前 30 天提醒一次、到期当天提醒一次，只发给合规管理员，每条每步只发一次 |
| 续期 | `POST /admin/legal/faqs/{id}/renew {valid_until}`（合规）：只有已上线的能续（`legal_faq_not_published`），日期同上限，续期后提醒重新计、写审计 |

## 4. 两端

- **Web 管理后台「法律知识」**：每条显示复核日期，过期的标红；「复核后续期」按钮。
- **App**：法律知识运营只在 Web 后台；问答页的行为（过期条目不再回答）两端一致，由服务端决定。

## 5. 隐私、授权与边界

- 续期是合规对内容的再次确认，写审计；是否要四眼另议（LAW-063）。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_legal_faq_review.py`） | 红验 |
|---|---|---|
| 上线默认一年后复核；过期后问答不再用它 | `test_default_review_date_and_expired_entries_stop_answering` | 过期了还回答 → 红；不给默认日期 → 红 |
| 到期前 30 天与到期当天各提醒一次、只叫合规 | `test_reminders_30_days_before_and_on_expiry_once_each_to_compliance` | 重复提醒 → 红；发给所有管理员 → 红 |
| 续期：日期范围、能把过期的续回来、提醒重新计、写审计、草稿不能续 | `test_renew_brings_it_back_resets_reminders_and_is_audited` | 不查日期 → 红；不重置提醒 → 红；草稿也能续 → 红 |
| 草稿自带复核日期 | `test_draft_can_carry_its_own_review_date_within_two_years` | — |
| 调度表、角色表、后台入口、job 计数 | `test_job_orchestration.py`、`test_admin_roles.py`、`test_admin_surface_coverage.py`、`test_doc_counts.py` | — |
| Web 后台 | `web/src/AdminLegal.test.tsx` | — |

## 7. 没做的

- **LAW-063 续期四眼**：现在一位合规就能续期；内容有实质变化的应走「下线 + 新起草」，单纯确认仍然对的续期是否也要第二人，待合规定（欠）。
- **LAW-061 代码里的四条迁进表**：仍然欠——它们也该有复核日期。
