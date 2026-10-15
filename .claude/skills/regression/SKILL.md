---
name: regression
description: Run the full regression for this repo in an isolated git worktree before pushing — backend pytest, web/SDK/app tests, lint, typecheck, frontend count check, and the real-browser e2e — via tools/regress.sh. Use before every push.
---

# 推送前的全量回归

- `tools/regress.sh <提交>`：在 scratch 目录建一个独立 worktree，检出该提交，依次跑：
  后端全量 pytest（独立 SQLite 文件）→ SDK / Web（JSON 报告）→ App jest → eslint → web 类型检查 →
  前端计数与文档核对（`scripts.check_frontend_counts`）→ 构建网页 → 真浏览器联调（`scripts.e2e_web`）。
- 结果写在 worktree 下的 `be.txt`（后端）与 `fe.txt`（其余），最后一行是 `done`。
- 跑的时候不要在本机并行跑别的重活：真浏览器联调有 30 秒超时，抢 CPU 会偶发超时。
- 任何一项红：修、在主工作区提交、重新跑整套；**全绿才推送**。判断以脚本的退出码与最后一行为准（「回归全绿」才算过，「回归失败」或非 0 退出就是红）——**不要只看输出的最后几行**：V171 的回归后端有 3 条失败，而当时脚本照样以 0 退出，被误推了一次（REG-001）。
- Postgres 专项（迁移与并发）：本机 `127.0.0.1:55432`，停了就用 `pg_ctl` 拉起（见 `docs/OPERATIONS.md`）。
