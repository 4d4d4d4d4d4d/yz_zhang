
# 280 没装 ruff 时静态检查不再静默跳过

> 状态：本批实现（V308）。编号 LINT-005。
> 来源：262、264、270 号 spec「没做的」——「本机没装 ruff 时静态检查跳过」；BACKLOG V308。
> 只增不减：规则与检查范围不变；开发者本机随手跑时没装 ruff 仍然跳过。

## 0. 要解决的问题

V168 起的静态检查（未定义名字、未用导入、未用变量……）写成「没装 ruff 就跳过」。在没装 ruff 的机器或流水线上，整条闸门安静地变成「已跳过」，没人会注意到——等于没有。

## 1. 规则

- `ruff_missing_action(env)`：环境里有 `CI`（GitHub Actions 自带 `CI=true`）或 `PLATFORM_REQUIRE_RUFF` 时，没装 ruff 就**失败**并写明怎么装（与 ci.yml 同版本）；否则跳过。
- `tools/regress.sh` 跑后端全量时设 `PLATFORM_REQUIRE_RUFF=1`。

## 2. 数据 / 接口 / 两端

不涉及。

## 3. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_metrics_truthful.py::test_ruff_missing_fails_where_it_must`（新增） | 把判断改成只认 `CI` → 变红 |
| `test_no_names_that_are_certainly_wrong`（改成在测试里判断） | 去掉 PATH 里的 ruff 并设 `PLATFORM_REQUIRE_RUFF=1` → 失败并写明怎么装；不设 → 跳过 |

## 4. 没做的

无新增欠账。
