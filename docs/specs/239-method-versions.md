# 239 方法按版本分开统计效果

> 状态：本批实现（V266）。编号 AGT-097。
> 来源：168 号 spec「没做的」——「方法改过步骤后，新旧版本的效果混在一起算；要按版本分开才知道改了之后有没有变好」；BACKLOG V266。
> 只增不减：方法的总数、做成、没成、花费、成功率这五个字段与 168 号完全一样（仍把所有版本加在一起）；方法的增删改、套用都不变。
> 写明的行为变化：`nb_methods.version`、`missions.method_version`（迁移 c1d220260057）；方法响应多 `version` 与 `versions`，编排响应多 `method_version`。

## 0. 要解决的问题

168 号让人看得到「这个方法用过几次、做成几次」。但人看到成功率不高就会去改步骤；改完之后旧版本的失败还算在里面，新版本好不好看不出来，改了也不知道该不该留。

## 1. 业界怎么做

模板 / Playbook / 提示词管理工具通常给每次修改记一个版本号，运行记录挂在当时的版本上，看效果时按版本分开，比较「改之前 / 改之后」。小样本不下结论（168 号的「做完 3 个才给成功率」同样按版本适用）。（本批没有另找外部来源。）

## 2. 规则

- 只有**步骤真的变了**才升一版；改名、改说明、把同样的步骤再提交一遍都不升。
- 用方法建编排时记下当时是第几版。没用方法的编排为空。
- 统计多按版本分一层：每一版各自的总数、做成、没成（含取消）、花费、成功率（做完的少于 3 个为空），新版在前；本批之前建的编排没有版本号，归在「记版本之前」一组、排最后。仍是一次查询，不按方法、不按版本逐个查。
- 两端的比较句（共享 SDK `methodVersionCompare`）：
  - 当前版还没用过：「第 N 版还没用过：用过几次后才看得出改了有没有变好」；
  - 当前版或上一版做完的少于 3 个：「做完的还少，先不比较…」；
  - 都够：「第 M 版成功率 x% → 第 N 版 y%：改了之后变好了 / 变差了，看看改了哪一步 / 没有变化」。
  - 上一版指版本号更小的最近一版；没有就和「记版本之前」比。
- 只用过当前一版时不分版本、不比较（与总数那句一样，不重复）。

## 3. 数据

`nb_methods.version`（默认 1，老方法迁移后都是第 1 版）；`missions.method_version`（可空）。迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 4. 接口

| 接口 | 变化 |
|---|---|
| `GET /notebook/methods`、新建 / 改方法的响应 | 多 `version`、`versions[]`（`version`、`missions_total`、`missions_succeeded`、`missions_failed`、`missions_spent_cents`、`success_rate`） |
| `PATCH /notebook/methods/{id}` | 步骤变了升一版 |
| `POST /missions` 及编排响应 | 多 `method_version` |

SDK：`NbMethod.version` / `versions`、`NbMethodVersionStats`、`Mission.method_version`；`methodVersionLines`、`methodVersionCompare`（两端同一句话）。

## 5. 两端

- **Web 知识库「我的方法」**：改过步骤的方法多一块：比较句 + 每一版一行。
- **App 知识库「我的方法」**：同样的句子。

## 6. 隐私、授权与边界

只统计本人的方法与本人的编排（与 168 号一样）；版本号不记步骤的历史内容（见「没做的」）。

## 7. 闸门与红验

`server/tests/test_method_versions.py` 2 条（只有步骤变才升版、编排记下版本、不用方法为空；按版本分开、新版在前、记版本之前排最后、每版小样本不给比率、总数不变）；`packages/core/src/methodVersions.test.ts` 4 条；`web/src/Notebook.test.tsx`、`app/notebook.test.tsx` 各 1 条。

20 处变异（`scratchpad/mut266.py`）：18 处首轮变红；「每版做完 1 个就给比率」「上一版样本不够也比」首轮存活，补「记版本之前做成一个」与「上一版不够样本」两例后变红。

## 8. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| AGT-098 | 方法的版本历史（每一版的步骤原文，可以对比改了哪一步、退回旧版） | 台账「欠」 |
