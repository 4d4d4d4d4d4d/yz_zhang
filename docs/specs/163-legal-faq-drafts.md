# 163 法律知识库的运营草稿流

> 状态：本批实现（V192）。编号 LAW-060（并完成 162 号 spec 的 SCN-114）。
> 来源：162 号 spec 第 7 节「没做的」SCN-114——「法律问答自己的知识库（`legal`）没有运营可写的草稿流，要先给它加版本与审核」；BACKLOG V192；VISION V-5a「AI 协助：不懂领域」。
> 只增不减：代码里的四条 `LEGAL_FAQS` 照常在用；法律问答的三种结局（高风险 / 超范围 / 命中）、免责声明、「找律师」补救都不变；响应多一个 `source` 字段（老条目与拒答是空串）。

## 0. 要解决的问题

- 法律问答只认代码里写死的四条。雷达已经能看到「婚姻家庭」类问题 3 个不同的人都没答上（153 号 spec），可补一条知识要改代码、发版本。
- 补进去的法律内容必须有出处、必须有人审，不能让模板或模型替人写结论。

## 1. 业界怎么做（带来源链接）

| 做法 | 例子 | 说明 |
|---|---|---|
| 帮助中心文章的草稿 → 审核 → 发布流程 | Intercom Fin 的内容建议（<https://www.intercom.com/help/en/articles/11394959-use-ai-powered-content-recommendations-to-improve-fin>） | 建议可编辑、接受或拒绝后才生效 |
| 法律信息必须标出处、不构成法律意见 | 平台已有的免责声明（97 号 spec） | 本批让运营补的每一条都带出处，并原样显示给用户 |

## 2. 数据

新表 `legal_faqs`（迁移 `c1d220260034`）：

| 字段 | 说明 |
|---|---|
| topic | 主题（与雷达的法律主题表一致，可空） |
| keywords | 关键词：用户问题里出现就匹配（与老条目同一套命中计数） |
| answer / source | 回答与出处（法规名与条号或官方链接） |
| status | draft / review / published / retired |
| origin | `radar:legal_gap:<主题>` 或 `manual` |
| created_by / reviewed_by / published_at / retired_reason | 四眼与下线理由 |

管理员写的平台内容，不是用户数据：不进注销处置与数据导出（与场景包同一类）。

## 3. 接口（合规管理员）

| 接口 | 说明 |
|---|---|
| `GET /admin/legal/faqs` | 列表（含每条还剩哪些「【待填写】」） |
| `POST /admin/legal/faqs`、`PUT /admin/legal/faqs/{id}` | 新写 / 改草稿（只有草稿能改：`legal_faq_not_draft`）；关键词去空去重，一个都没有就 400 `legal_faq_no_keywords` |
| `POST /admin/legal/faqs/radar-draft` `{topic}` | 只认雷达此刻真有的 `legal_gap` 主题；关键词取主题表里的常见词；回答与出处留「【待填写】」；「其他」这类没有常见词的主题 409；写审计 |
| `POST /admin/legal/faqs/{id}/submit` | 还有「【待填写】」就 409 `pack_placeholder_left` |
| `POST /admin/legal/faqs/{id}/approve` | 四眼（`legal_faq_four_eyes`）；上线时再查一遍空；写审计 |
| `POST /admin/legal/faqs/{id}/reject`、`/retire` `{reason}` | 退回草稿；下线写理由（写审计），问答立刻不再用它 |
| `POST /legal/ask`（已有） | 代码四条 + 已上线条目一起按命中数匹配（同样命中时老条目在前）；响应多 `source` |

## 4. 两端

- **Web 管理后台「法律知识」**：列表与状态、还没填的空、从雷达起草（没有运营角色看不到雷达时可手填主题）、手写一条、提交、上线（写它的人按钮禁用）、退回、下线。
- **Web「不懂就问」与 App 问答页**：命中运营补的条目时显示「出处：……」；老条目不显示空出处。

## 5. 隐私、授权与边界

- 法律内容归合规角色（运营、客服都是 403）；上线四眼。
- 雷达起草只用主题与人数（k-匿名），不碰任何人的提问原文（原文本来就不落库）。
- 高风险问题仍然最先判断：不管知识库有什么，涉人身安全一律引导报警。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_legal_faq.py`） | 红验 |
|---|---|---|
| 雷达主题 → 草稿 → 留空不能提交 → 填完提交 → 四眼上线 → 同样的问题答得上并带出处、不再记成答不上 → 下线后又答不上 | `test_radar_topic_to_published_answer_with_source_closes_the_loop` | 问答不查上线条目 → 红；提交不查空 → 红；四眼去掉 → 红；草稿不留空 → 红；草稿也能改成非草稿 → 红；下线了还在用 → 红 |
| 上线时再查一遍空（绕过提交也不行） | `test_approve_rechecks_placeholders_even_if_submit_was_bypassed` | 上线不查空 → 红 |
| 只认雷达上真有的主题；没有常见词的主题拒绝 | `test_only_real_radar_topics_and_topics_with_keywords` | 不查信号 → 红；不查常见词 → 红 |
| 手写、关键词清洗、角色 | `test_manual_draft_and_roles` | 不拒空关键词 → 红 |
| 老条目照常、`source` 空串 | `test_old_code_faqs_still_answer_and_carry_an_empty_source` | — |
| Web 后台 | `web/src/AdminLegal.test.tsx` | 上线按钮不禁用 → 红 |
| 两端显示出处 | `web/src/Ask.test.tsx`、`app/ask.test.tsx` | 不显示出处 → 红 |

## 7. 没做的

- **LAW-061 把代码里的四条迁进表**：现在两处并存（代码四条 + 表），四条的改动仍要发版。迁进去要处理「老条目没有出处字段」——等法务补齐出处后一次迁完（欠）。
- **SCN-113 用模型给带出处的回答初稿**：仍然欠（162 号 spec），出处字段齐全之后做。
- **LAW-062 法律条目的有效期与到期复核**：法规会改，条目没有有效期，也没有到期提醒（欠）。
