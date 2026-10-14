---
name: iterate
description: 固定的迭代范式：每一批做完都必须打钩、更新 spec、把没做的写进台账或 BACKLOG，然后直接接着做下一批（含没做的）；不等用户提醒、不问用户。每批收尾和开下一批之前都要走一遍。
---

# 迭代范式（每一批都这么走）

用户原话（2026-10-14）：「做完的记得在文档里打钩，更新 spec，然后继续把没做的完成，这个需要描述成一个固定的范式 skill，每次应该都要这么迭代。」

这是**外层循环**；一批里面怎么做，看 skill `spec-batch`。总规则看根目录 `CLAUDE.md`。

```
取活 → spec-batch 做一批 → 收尾打钩 → 没做的有去处 → 回归推送 → 取下一批（循环，不停）
```

## 1. 取活（每轮开头）

1. 用户这一轮说了新需求：先走 skill `vision-sync`，把原话写进 `docs/VISION.md`（新的一节加对照行），在 `docs/BACKLOG.md` 插一行。
   用户点名要做的，排在待办**最前面**。
2. `cd server && python -m scripts.harness backlog`，取最上面的 `todo`。
3. 待办少于 3 条：走 skill `scenario-discovery` 补，不要只做用户举过的例子。

## 2. 做一批

按 skill `spec-batch` 的 1～6 步做：写 spec、实现（服务端、SDK、Web、App 一起）、红验、登记闸门。

## 3. 收尾打钩（必做，`harness check` 会核对）

`python -m scripts.harness closeout V1xx` 会逐项列出 `[x]` / `[ ]`，**全部 `[x]` 才算做完**：

| 项 | 在哪 |
|---|---|
| BACKLOG 这一批改成 `done`，写上 spec 号 | `docs/BACKLOG.md` |
| spec 状态行改成「本批实现（V1xx）」 | `docs/specs/NNN-*.md` |
| spec「没做的」一节写清还欠什么，每件带编号（如 `INF-110`） | 同上 |
| 台账加「已做」行；「没做的」编号进台账的未做表 | `docs/specs/72-status-ledger.md` |
| 愿景对照行改成「两端已接」并写上批次号与 SDK 方法 | `docs/VISION.md` |
| 现状文档划掉这一项（`~~…~~ | 已做`） | `docs/STATUS-*.md` |
| 版本号、计数（以测试输出为准） | `server/app/core/config.py`，`tests/test_doc_counts.py` 报的数 |

`harness check` 会拦下三种漏网：spec 写着已实现而 BACKLOG 没打钩；做完的批次没有「没做的」；「没做的」里的编号既不在台账也不在 BACKLOG。

## 4. 没做的要有去处，然后接着做

- 能在本仓库做完的：在 BACKLOG 插一行 `todo`（新批次号），**排在合适的位置**，之后照常去做。
- 需要外部资源的（持牌机构、外部账号、真机、费用）：BACKLOG 写一行「外」，说清缺什么。不阻塞别的。
- 有意不做的：在 spec 里写理由，台账写「有意不做」。

## 5. 回归、提交、推送，然后回到第 1 步

- `tools/regress.sh` 全绿才推（skill `regression`），一批一个提交，提交说明写批次号与 spec 号。
- 推送后**不停**：回到第 1 步取下一批。只有 BACKLOG 里全是「外」且场景发掘也补不出新批次时才停下汇报。

## 6. 汇报给用户（每批一段，人话）

做了什么、怎么验的（红验、回归数）、没做的去了哪里、下一批是什么。不问用户要不要继续。
