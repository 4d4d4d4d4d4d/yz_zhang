
# 122 个人知识库：收件箱、笔记与链接、标签与检索、助手引用、纪要抽待办、个人方法蒸馏

> 状态：本批实现（V147）。编号 KB-100~110。
> 来源：用户 2026-10-13：「本身自己的门户就是通过助手管理和知识库的构建，这样也方便对外的合作。」
> VISION 1.6（门户 = 助手 + 知识库）、1.8（知识库是平台资产之一）；121 号 spec 第 16、22 章的差距；BACKLOG V147。
> 只增不减：工作台的「让助手拆一下」原有字段（`source`、`steps`）不变，只**多给**一个 `references`；
> 导航原有五项一个不少，只多一项「知识库」；平台经验库（`knowledge` 模块、`/knowledge/*`）不动。

## 0. 要解决的问题

V141 做了门户的一半（个人任务、进度、助手）。另一半**知识库整个没有**：
随手看到的链接、会议纪要、自己摸索出的做法，没有地方放；放了也找不回来；找回来了助手也用不上。
蓝皮书第 16 章的原话是「收藏不是知识管理，能再用起来才是」。

## 1. 业界怎么做

- **CODE / PARA（Tiago Forte《Building a Second Brain》）**：捕获（Capture）→ 整理（Organize）→ 提炼（Distill）→ 表达（Express）。
  捕获要零摩擦（先进收件箱，晚点再整理）；提炼是反复回看时把要点收出来；表达是把笔记变成产出。
  [charterworks 书摘](https://www.charterworks.com/building-second-brain-tiago-forte/)、
  [mmapped 书摘](https://mmapped.blog/posts/16-building-a-second-brain)。
  对应到这里：随手记进**收件箱** → 加标签即「整理过」→ **蒸馏成我的方法** → 方法**套到工作台任务上**变成清单（表达）。
- **Notion AI Q&A**：从自己的工作区里找答案，答案**链回出处页面**，只引用提问者有权看的页面。
  [aiwiki 条目](https://aiwiki.ai/wiki/notion_ai)。对应到这里：「问问我的笔记」只查本人笔记、每条都带出处、没记过的不编。
- **WorkBuddy 蓝皮书第 17 章**（会议纪要 → 待办）、**第 22 章**（把资料蒸馏成可执行 Skill，三重验证）：
  对应到这里：纪要抽待办只出草稿、人确认才进工作台；蒸馏只出草稿、人确认才保存。

## 2. 数据

| 表 | 字段 | 说明 |
|---|---|---|
| `nb_notes` | `owner_id`、`kind`（note / link / minutes）、`title`、`body`（≤2 万字）、`url`、`status`（inbox / filed / archived）、`tags`（≤10 个，每个 ≤20 字）、`pinned`、`project_id`、`revision`、时间 | 每人上限 5000 条 |
| `nb_methods` | `owner_id`、`name`、`description`、`steps`（[{title, note}]，≤30 步）、`source_note_ids`、`uses`、时间 | 每人上限 100 个 |

迁移 `c1d220260014`，SQLite 与 Postgres 都验过 `upgrade head && alembic check`。

## 3. 接口（全部 `/notebook/*`，全部只对本人）

| 编号 | 接口 | 做什么 |
|---|---|---|
| KB-101 | `POST /notebook/notes` | 随手记。正文只有一个链接 → `link`（标题取域名 + 路径）；认出 ≥2 条待办 → `minutes`；否则 `note`。标题默认取第一行。**服务端不抓取链接**（SSRF 与版权）。只收 http / https |
| KB-101 | `GET/PATCH/DELETE /notebook/notes/{id}` | 改动带 `revision`，过期 409 `nb_revision_conflict`；改了标签 / 标题 / 正文就自动出收件箱（只改置顶不算） |
| KB-102 | `GET /notebook/notes?q=&tag=&status=&kind=` | 字面检索（见下），默认不含已归档；带 q 时按相关度排、摘要取命中处 |
| KB-103 | `GET /notebook/summary` | 总数、收件箱数、归档数、方法数、标签计数 |
| KB-104 | `POST /notebook/ask`、`GET /notebook/related?item_id=` | 助手引用：摘录式回答，每条带出处；工作台任务的相关笔记。工作台「让助手拆一下」的草稿多给 `references`，配了模型时把相关笔记作为上下文 |
| KB-105 | `POST /notebook/notes/{id}/extract-todos` → `POST /notebook/notes/{id}/todos` | 纪要抽待办：先草稿（不写库），确认后建工作台任务（备注写「来自笔记『…』」，进展记一笔） |
| KB-106 | `POST /notebook/methods/distill` → `POST /notebook/methods` | 个人方法蒸馏：有编号的步骤优先，没有再取圆点；「标题：说明」拆成步骤与备注；去重；找不到就如实说 `found: none` |
| KB-107 | `POST /notebook/methods/{id}/apply` | 方法套到工作台任务：步骤变清单子项，复用工作台的层级与上限规则，`uses + 1` |
| KB-108 | `GET /notebook/export` | 导出 Markdown（笔记 + 方法） |
| KB-109 | 注销与数据导出 | 注销物理删除笔记与方法；`/users/me/export` 多一节 `notebook`（含正文） |

**检索的做法（KB-102）**：
- 词：英文 / 数字按词；中文连续串整串（权重 3）+ 二字切片（权重 1）。
- 去虚词（「专票**要什么**」→「专票」）和带前缀的时间词（「**十月**报税」→「报税」；「周报」「年报」不动）。
- 打分：标题 ×3、标签 ×2、正文出现次数（封顶 3）、链接 ×1。
- **覆盖门槛**：长中文串没有整串命中时，二字切片至少命中一半且不少于 2 个（短词就是全部），否则这一组不算——「增值税」不命中「和增值无关」，「个税申报」能命中「增值税申报」，问句「验收过期会怎样」能命中「验收……过期自动放款」（V148 调整：原先的 60% 让自然问句答不上）。
- 「相关笔记」与问答要求分数 ≥3：宁缺毋滥，助手不引一条不沾边的。
- **不是语义检索**：个人笔记不送去向量化供应商（隐私）。回答带 `mode: "extractive"`，不冒充语义。语义检索与 V155 一起做。

**日期识别（KB-105）**：「周五前」「下周三」「明天」「后天」「10月20日」「10/20」→ 北京时间当天 18:00；
已过去 30 天以上的月日算明年；认不出（「尽快」「2月30日」「1/2/3」）就不猜。

## 4. 两端

- **Web**：导航多一项「知识库」（`/notebook`）。收件箱 / 全部 / 我的方法 / 问问我的笔记 四个视图；随手记框；搜索与标签筛选；
  勾选笔记蒸馏成方法（草稿可删步、可改名）；笔记面板里改标题 / 正文 / 标签、整理、归档、置顶、删除、**抽出待办**（草稿可取消勾选）；
  方法可改名；一键导出 Markdown。工作台任务面板多「相关笔记」（链到笔记）与「套用我的方法」。
- **App**：「我的」多一个子页「我的知识库」：随手记、收件箱 / 全部 / 我的方法 / 问笔记、笔记详情（标签、归档、置顶、抽待办）。
  工作台任务详情多「相关笔记」与「套用我的方法」。蒸馏在网页上做（App 上只看方法）。

## 5. 隐私、授权与边界

- 对象级授权：`^\w+ /notebook/` 为 `self`；别人的 id 一律 404。蒸馏 / 存方法时混进别人的笔记 id **整批 404**，不悄悄丢掉（否则能探测 id）。
- 不进全站搜索（测试钉住）、不进推荐、不进经验库、不送向量化供应商、不写日志。
- 链接只存地址；Web 打开链接带 `rel="noopener noreferrer nofollow"`。
- 草稿（抽待办、蒸馏）一律不写库；写库都要人确认。
- 请求体多收字段 422（`extra="forbid"`）。

## 6. 闸门与红验

| 闸门 | 红验（改坏 → 对应测试变红 → 改回） |
|---|---|
| 别人的笔记 404 | 去掉 `_own` 的 owner 判断 → `test_other_people_get_404…` 红 |
| 蒸馏混进别人的 id 整批 404 | 去掉 `_own_notes` 的数目比对 → 同上红 |
| 覆盖门槛 | `max(2, …)` 改成 `max(1, …)`（只沾一个二字边也算）→ `test_terms_and_score_units` 红 |
| 已勾掉的不抽 | 去掉 `_CHECK_DONE` → `test_extract_todos…` 红 |
| 整理即出收件箱 | 去掉自动 filed → `test_editing_files_out…` 红 |
| 注销删除 | 删掉 `NbMethod, NbNote` 处置 → `test_account_erase…` 红 |
| 编号步骤优先 | `numbered or bullets` → `numbered + bullets` → `test_distill_prefers…` 红 |
| 拆清单带引用 | generic 分支 `references` 改空 → `test_workbench_breakdown_and_related…` 红 |
| 过去的月日算明年 | 去掉判断 → `test_due_hint_units` 红 |
| 响应形状 | `test_responses_match_sdk_types`：每个 Nb* 接口与 SDK 声明逐字段比（三个方向） |
| 真浏览器 | `scripts/e2e_web.py`：随手记纪要 → 抽待办进工作台 → 问笔记带出处 |

## 7. 没做的

- **KB-110 语义检索**：要把个人笔记送去向量化，先要有本地模型或明确授权，与 V155 一起做。
- 网页正文抓取与摘要：SSRF、版权、成本；现在由用户粘贴要点。
- 附件 / 图片笔记：走现有文件存储即可，等有真实需求再接。
- 生成式回答（模型综合多条笔记作答）：等 V153 把模型调用的运行合同、成本与日志统一后接入；现在只摘录。
- 笔记之间的双向链接（Zettelkasten）：先看收件箱与标签用起来的情况。
