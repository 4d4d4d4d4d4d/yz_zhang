# 200 本地回归与 CI 检查项自动比对

> 状态：本批实现（V233）。编号 CI-006。
> 来源：198 号 spec「没做的」——「从 `.github/workflows` 读出 CI 的检查项，自动比对 `regress.sh` 有没有对应的一步」；BACKLOG V233。
> 只增不减：回归原有步骤不变，多两步（沙箱合规态闭环、迁移与模型一致性的 SQLite 路径）。

## 0. 要解决的问题

这几天的「本地绿、CI 红」全是同一类问题：两边的检查项对不上。CI-001（App 依赖布局）、CI-003（vitest 未处理错误）、CI-004（jest 报告器）、CI-005（App 类型检查）都是事后才发现、逐项补的手写断言。要的是一张表：**CI 的每个 job，要么本地有对应的一步，要么写明为什么只在 CI 上跑**；CI 新加一个 job，不归类就红。

## 1. 业界怎么做

把「本地预检」与 CI 共享同一份检查清单，是减少「本地过、CI 挂」的常规做法（如 pre-commit / Makefile 目标与 CI 共用一套命令）。本仓库的 CI 是 GitHub Actions、本地是 `tools/regress.sh`，两边命令不同，所以用一张显式对照表加自动核对。

## 2. 数据

无。

## 3. 改动

`server/tests/test_ci_portability.py`：

- `LOCAL_STEPS`：CI job → `regress.sh` 里必须出现的命令片段（backend、frontend、app-typecheck、web-e2e、sandbox-compliance、migration-drift）。
- `CI_ONLY`：CI job → 只在 CI 上跑的理由（smart-contracts、boot-smoke、dependency-audit、restore-drill、postgres-acceptance）。
- 测试读 `.github/workflows/ci.yml`：没归类的 job → 红；表里有、CI 里已没有的 job → 红；说了本地有、`regress.sh` 里找不到 → 红；理由少于 15 个字 → 红。

`tools/regress.sh` 补两步（CI 上便宜、不要外部依赖）：沙箱合规态闭环（约 7 秒）、迁移 `upgrade head` + `check`（SQLite）。

## 4. 两端

不涉及界面。

## 5. 隐私、授权与边界

只在 CI 上跑的五项都要外部资源：EVM 编译器、联网漏洞库、Postgres 与 pg 工具、独立服务进程。它们的理由写在表里，CI 上照跑。

## 6. 闸门与红验

`test_every_ci_job_has_a_local_step_or_a_written_reason`：从表里删掉一个 job → 红；把 `regress.sh` 里的 `scripts.sandbox_check` 改坏 → 红。两个新步骤手动跑通过。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| — | 无（只在 CI 上跑的五项见第 5 节，需要外部资源） | — |
