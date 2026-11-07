# 162 雷达主题一键起草知识条目

> 状态：本批实现（V186）。编号 SCN-112。
> 来源：153 号 spec 第 7 节「没做的」——「`legal_gap` 出现后，补法律 FAQ 或对应场景包的知识条目仍是人工；可以做成雷达上一键『起草知识条目』（只出草稿，审核上线）」；BACKLOG V186；VISION 1.8「场景靠方法发掘，资产是平台的根」。
> 只增不减：雷达的五路信号、场景包的版本与四眼、草稿编辑都不变；提交审核与上线多一道检查（起草留的空没填完不让过）。

## 0. 要解决的问题

- 雷达已经能看到缺口：例如「婚姻家庭」类法律问题近 30 天有 3 个不同的人都没答上。可从「看到」到「补上」中间全靠运营手写一份 JSON，没人去做，雷达就只是一块看板。
- 起草如果直接让模板或模型把「答案」写出来，法律、财税这类内容一旦写错就是平台在给错误建议；而且很容易被一路点「上线」。

## 1. 业界怎么做（带来源链接）

| 做法 | 例子 | 说明 |
|---|---|---|
| 从「没答上的问题」生成知识库建议 | Intercom Fin 的内容缺口建议（<https://www.intercom.com/help/en/articles/11394959-use-ai-powered-content-recommendations-to-improve-fin>）；更早的「没答上的问题」报告（<https://intercom.help/fin4all/en/articles/10672146-analyze-unresolved-questions>） | 按主题聚合没答上的对话，给出补内容的建议；每条建议都可编辑、接受或拒绝后才生效 |
| 从工单发现要写的文章 | Zendesk Content Cues（<https://www.zendesk.co.uk/blog/introducing-content-cues-for-zendesk-guide-enterprise/>） | 用工单内容建议该写或该更新的帮助文章；该功能 2025-05 起已被 Zendesk 下线（使用率低），说明「只给建议」本身不够，要把建议接进写作与审核流程 |
| 草稿占位与发布前检查 | 内容平台常见的「TODO / 待补充」占位、发布前 lint | 占位不清就不能发布，防止半成品上线 |

我们的取舍：只起草**骨架与依据**（主题、人数、常见词、写作要求），回答与出处一律留「【待填写】」，不让模板或模型代写结论。

## 2. 数据

不新增表。起草结果是目标场景包定义里 `knowledge` 的一条：

| 字段 | 内容 |
|---|---|
| key | `radar-<来源>-<n>`，包内不重复 |
| title | 按来源：法律「X：常见问题怎么答」、客服「X：客服常见问题」、搜索「想找『X』时怎么办」、没人接「『X』的需求怎么写才有人接」 |
| body | 「【待填写】」+ 写作要求 + 起草依据（雷达原话的人数与时间窗）+ 该主题常见词（法律 / 客服主题表） |
| source | 「【待填写】出处：法规名与条号、官网链接或平台规则」 |
| kind | 法律问题为 `rule`，其余 `howto` |
| tags | 主题、「雷达起草」 |

## 3. 接口

| 接口 | 角色 | 说明 |
|---|---|---|
| `POST /admin/packs/radar/draft-knowledge` `{source, key, pack_key}` | 运营（ops） | 只认雷达**此刻真有**的信号（至少 3 个不同的人）；目标包最新版本是草稿就加进去，已上线 / 旧版本就建新草稿版本，有版本在审核中则 409 `pack_draft_exists`；返回 `{pack, knowledge_key, new_version, placeholders}`；写审计 `pack_radar_draft` |
| `POST /admin/packs/{id}/submit`、`/approve` | 运营 | 多一道检查：知识的标题 / 正文 / 出处里还有「【待填写】」就 409 `pack_placeholder_left`，写明是哪一条哪一项 |

SDK：`adminDraftKnowledgeFromRadar`，类型 `RadarKnowledgeDraft`；错误码 `pack_placeholder_left` 进 i18n。

## 4. 两端

- **Web 管理后台「服务包运营」**：雷达表每行多「起草知识条目」，上方选「起草进哪个服务包」；起草后编辑器直接打开那份草稿，并提示把「【待填写】」写完再提交。
- **App**：不涉及（场景包运营只在 Web 后台）。

## 5. 隐私、授权与边界

- 雷达本来就只出主题与人数（k-匿名，原文不落库），起草只用雷达给出的这些字段，不碰任何人的提问原文、工单正文或笔记。
- 只认雷达此刻真有的信号：人数不够、过了时间窗的主题起草不了（防止绕过 k-匿名，自己编一个主题当依据）。
- 模板不写结论；钱、签署、申报类的写作要求写在草稿里（只给步骤、不替人决定、拿不准转律师或人工）。
- 上线照旧四眼：写它的人不能自己批。

## 6. 闸门与红验

| 闸门 | 测试（`server/tests/test_radar_draft.py`） | 红验 |
|---|---|---|
| 起草进新草稿版本，回答与出处留空，带上依据与常见词；原上线版本不受影响 | `test_draft_goes_into_a_new_draft_version_with_placeholders_and_cannot_be_submitted_until_filled` | 正文不留空 → 红；出处不留空 → 红 |
| 留空不能提交审核；填完提交，四眼上线；审计有记录 | 同上 | 提交不查空 → 红 |
| 上线时再查一遍（绕过提交直接改成待审核也不行） | `test_approve_also_refuses_leftover_placeholders` | 上线不查空 → 红 |
| 第二次起草进同一份草稿、key 不重复 | `test_a_second_draft_lands_in_the_same_draft_with_a_fresh_key` | 总是建新版本 → 红；key 不去重 → 红 |
| 只认雷达上真有的信号；没有的包 404 | `test_only_signals_that_are_really_on_the_radar` | 不查信号 → 红 |
| 有版本在审核中不往里加；只有运营能起草 | `test_pack_in_review_is_not_touched_and_only_ops_can_draft` | （显式检查与 `_new_version` 重复，属等价变异，已删去重复代码） |
| Web：选包、起草、编辑器打开草稿、提示写完空 | `web/src/Packs.test.tsx` | — |
| 角色表、后台入口表 | `test_admin_roles.py`、`test_admin_surface_coverage.py` | — |

## 7. 没做的

- **SCN-113 用模型起草回答初稿**：现在回答完全留给人写。可以在平台配了模型时，按主题从现有法律知识库与平台规则里检索出处，给出「带出处的初稿」，但必须仍标「待人核对」且上线四眼——等法律知识库的出处字段齐全后再做（欠）。
- ~~**SCN-114 法律 FAQ 也能一键起草**~~ → **已做**（V192，163 号 spec）：现在只进场景包的知识条目；法律问答自己的知识库（`legal`）没有运营可写的草稿流，要先给它加版本与审核（欠）。
