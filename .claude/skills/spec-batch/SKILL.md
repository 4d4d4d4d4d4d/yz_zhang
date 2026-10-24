---
name: spec-batch
description: Run one spec-driven batch in this repo end to end — pick the next item from docs/BACKLOG.md, scaffold the spec with server/scripts/harness.py, implement server + SDK + web + app with red-verified tests, register gates, update docs, run tools/regress.sh, commit and push. Use whenever continuing work on the platform without asking the user.
---

# 一批的完整做法

规则总纲见仓库根 `CLAUDE.md`。这里是逐步清单，**按顺序做，每一步做完再下一步**。

## 1. 取活
- `cd server && python -m scripts.harness backlog`：列出未完成的批次，取第一条。
- 读这一条引用的 spec（如果已经有）、`docs/VISION.md` 相关行、台账里相关 ID。

## 2. 写 spec
- `python -m scripts.harness new-spec "标题" --batch V1xx --ids XXX-001~010`
  会生成 `docs/specs/NNN-<slug>.md` 骨架（状态、来源、业界、数据、接口、两端、闸门、没做的）并登记进 `docs/specs/README.md`。
- 先查业界做法（WebSearch），写进「业界」一节，带来源链接。

## 3. 实现（只增不减）
- 服务端模块：`server/app/modules/<模块>/`（models / service / router），在 `app/main.py` 与 `app/modules/models_all.py` 登记。
- 迁移：`server/migrations/versions/c1d2202600NN_<名>.py`，`alembic upgrade head && alembic check`（SQLite 与 Postgres 都验）。
- 共享 SDK：`packages/core/src/types.ts`（接口**一行一个字段**，形状闸门按行解析）、`client.ts`（类型具名导入）、`i18n.ts`（新错误码）。
- Web：`web/src/pages/`，路由进 `web/src/App.tsx`；App：`app/*.tsx`，入口进 `app/TeamCoopDev.tsx` 的子页列表。

## 4. 测试与红验
- 后端：`server/tests/test_<主题>.py`；前端：`web/src/*.test.tsx`、`app/*.test.tsx`。
- 每条关键判断做一次变异：改坏 → 跑对应测试必须红 → 改回。

## 5. 登记（漏了任何一项全量回归会红）
- 功能面清单：`python -m scripts.feature_surface --write`
- 对象级授权：`server/tests/test_object_level_authz.py` 的 `OWNERSHIP_RULES`
- 补救入口：新的祈使句错误码进 `server/tests/test_remedy_ui.py`
- 注销处置与数据导出：`app/modules/account/deletion.py`、`/users/me/export`
- 定时任务：`app/core/jobs.py`
- SDK 方法分诊：两端都还没调用的，进 `server/tests/test_sdk_method_triage.py`

## 6. 文档
- spec 状态改成「本批实现（V1xx）」；`docs/BACKLOG.md` 勾掉；台账（72 号）对应 ID 改成「已做」；
  `docs/VISION.md` 对照行；`docs/STATUS-*.md`；版本号 `server/app/core/config.py`。
- 计数：`python -m pytest tests/test_doc_counts.py` 报的真实数写进文档（不要改断言）。
- `python -m scripts.harness closeout V1xx` 全部 `[x]`（打钩、spec、没做的去处；外层循环见 skill `iterate`）。
- `python -m scripts.harness check` 全绿。

## 7. 回归、提交、推送
- `tools/regress.sh`（skill `regression`），全绿才推。
- 提交说明：`V1xx <一句话>（<spec 号>）` + 要点 + 规定的署名行。
