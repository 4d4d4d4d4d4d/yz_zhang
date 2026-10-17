# 198 本地回归补上 App 类型检查

> 状态：本批实现（V232）。编号 CI-005。
> 来源：V223 提交前发现 `app/onBehalf.test.tsx` 里一个类型错误（`status` 字面量推成 string），本地回归没有拦住——`tools/regress.sh` 只对 Web 做类型检查，而 GitHub CI 的 App job 会做。
> 只增不减：回归原有步骤不变，多一步。

## 0. 要解决的问题

本地回归是推送前的最后一道闸。它和 GitHub CI 不一致的地方，就是「本地绿、CI 红」的来源（CI-001、CI-003、CI-004 都是这一类）。这次是 App 的类型检查：CI 有，本地没有。

## 1. 业界怎么做

推送前的本地检查应与 CI 的检查项一一对应（同一套命令），否则本地绿不代表 CI 绿。本批把缺的那一项补上。

## 2. 数据

无。

## 3. 改动

`tools/regress.sh` 在 Web 类型检查之后加 `cd app && npx tsc --noEmit`，非 0 退出写「步骤失败（退出码 N）：App 类型检查」并算失败。

## 4. 两端

不涉及界面。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

`server/tests/test_ci_portability.py::test_local_regression_typechecks_the_app_like_ci_does`：去掉这一步（或它的失败提示）→ 红。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| CI-006 | 从 `.github/workflows` 读出 CI 的检查项，自动比对 `regress.sh` 有没有对应的一步（而不是逐项手写断言） | 欠 |
