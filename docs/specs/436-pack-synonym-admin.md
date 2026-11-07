# 436 场景包近义说法在后台维护

> 状态：本批实现（V463）。编号 PACK-092c。
> 来源：435 号（V462）第 7 节的欠账：近义表写在仓库文件 `packs/synonyms.json` 里，新出一个说法就要发版。
> 例子：无人机包的知识写的是「风力」，问「风很大能飞吗」接不住。运营看得到「答不上」，却改不了。
> 只增不减：仓库近义表、`pack_terms` 的规则、V462 的闸门都在；后台只能**加**写法，仓库里写死的收不回。

## 0. 要解决的问题

- 运营要能自己给近义表加写法，不等发版。
- 配错的代价：所有场景包助手检索时都会多带上这些词，可能引用不相干的知识。所以和资质别名（334 号）一样四眼：
  - 一位管理员提出（写理由）；
  - 另一位确认才生效；
  - 任何一位都可以收回，收回立刻失效。

## 1. 业界怎么做（带来源链接）

搜索系统的同义词表一般由运营在后台维护，改动先审后发，并且能先试一句看效果。本轮没有引用外部报道链接。

## 2. 数据

新表 `pack_synonyms`（迁移 `c1d220260101`），一行就是「给一组加几个写法」：

| 字段 | 说明 |
|---|---|
| `name` | 组名。对得上仓库或已生效的一组就并进去，对不上是新的一组（组名自动算一个写法） |
| `words` | 要加的写法 |
| `includes` | 单向包含的组 |
| `reason` | 理由，至少 4 个字 |
| `status` | `pending` / `active` / `revoked` |
| `proposed_by` / `approved_by` | 提出人 / 确认人 |
| `created_at` / `decided_at` | 提出时间 / 处理时间 |

生效的近义表 = 仓库里的 + `active` 的行（按 id 先后并入）。`synonym_groups(db)`、`synonyms_in(q, db)`、`pack_terms(q, db)` 给了 db 才看后台的行。离线试问法和只靠标签的闸门不给 db，只看仓库里的（它们管的是仓库里的种子包）。

## 3. 接口

都要「运营」角色（`ops`），每一步记审计。

| 接口 | 做什么 |
|---|---|
| `GET /admin/pack-synonyms` | 生效的表 `effective` 和后台提出过的每一行 `items` |
| `GET /admin/pack-synonyms/expand?q=` | 试一句：检索时会多带上哪些写法 |
| `POST /admin/pack-synonyms` | 提出 |
| `POST /admin/pack-synonyms/{id}/approve` | 确认 |
| `POST /admin/pack-synonyms/{id}/revoke` | 收回 |

**提出时的检查**，规则与仓库近义表的闸门是同一套（`service.check_synonym`），错误码都进了 `i18n.ts`：

| 拦什么 | 错误码 |
|---|---|
| 少于两个字的 | `pack_synonym_short` |
| 写法已在别的组 | `pack_synonym_word_taken` |
| 是技能概念表里的词 | `pack_synonym_skill_word` |
| 包含的不是已有的另一组 | `pack_synonym_unknown_include` |
| 写法全都已经在组里 | `pack_synonym_exists` |
| 一展开超过 32 个写法 | `pack_synonym_too_wide` |
| 同名一行还在等确认 | `pack_synonym_pending` |

**确认时**：
- 不能确认自己提出的（403 `pack_synonym_self`）；
- 按**当时**的表再查一遍。两个人分别把「风力」加进两组，先确认的生效，后确认的得 409，并说明「提出以后近义表变了」。

**展开上限从 24 放到 32**：V462 定的是 24，可仓库里「天气不好」一组就正好 24，后台一个词都加不进去。

SDK：`packSynonyms` `expandPackSynonyms` `proposePackSynonym` `approvePackSynonym` `revokePackSynonym`，类型 `PackSynonymItem` `PackSynonymGroup` `PackSynonymList` `PackSynonymExpansion`。

## 4. 两端

- Web：管理后台「服务包」页底部加「近义说法」一块：
  - 列出生效的表、后台提出的行；
  - 自己提出的看不到「确认」；
  - 可以收回；
  - 提出时写法按逗号、顿号、空格拆开；
  - 能试一句。
- App：不做。管理后台只在 Web 上，与资质别名、服务包运营一样。

## 5. 隐私、授权与边界

- 只有运营能看、能改，每一步记审计。
- 「试一句」只返回会多带上哪些写法，不记下这句话。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_pack_synonym_admin.py`（4 条）：<br>提出不生效、自己不能确认、另一位确认后无人机包「风很大能飞吗」接住「风力」那条、并进仓库那一组且原写法都在、收回立刻失效、三步都有审计；七种不合规的提出被拦、说清原因；确认时按当时的表再查；新的一组带上组名、单向包含、离线工具只看仓库 | 10 处，全红：<br>自己能确认自己；确认时不再查；待确认和已收回也生效；不看后台的行；不查一个词在两组；不查技能概念词；不查展开太宽；不查包含的组；新组不带组名；同名待确认不拦 |
| `web/src/PackSynonyms.test.tsx`（2 条） | 2 处，全红：<br>网页上自己的也能确认；不按中文逗号拆 |
| `test_admin_roles` / `test_admin_surface_coverage` 登记五个接口；功能面清单 1344 项 | 漏登记即红（既有闸门） |

## 7. 没做的

| 编号 | 内容 | 去处 |
|---|---|---|
| — | App 上的近义表维护 | 有意不做：管理后台只在 Web |
| — | 雷达里「答不上」的问法一键起草成近义提议 | 不记欠账：现在运营看雷达后手动提出，量起来了再排 |
