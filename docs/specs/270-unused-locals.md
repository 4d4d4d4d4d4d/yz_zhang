
# 270 未用局部变量与重复定义进静态检查

> 状态：本批实现（V297）。编号 LINT-007。
> 来源：264 号 spec「没做的」——「未用的局部变量（F841）与重复定义（F811）是否打开，先数一数有多少」；BACKLOG V297。
> 只增不减：没有删任何断言或调用；4 处测试只是去掉了没人用的变量名（调用本身保留，它们是造数据的前置步骤）。ruff 规则只加不减。

## 0. 先数

| 规则 | app/ + scripts/ | tests/ + migrations/ | 结论 |
|---|---|---|---|
| F841 未用的局部变量 | 0 | 4 | 4 处都是「造数据的调用、返回值没用」：去掉变量名、保留调用；四个目录都打开 |
| F811 重复定义 | 0 | 6 | 6 处全是误报：从别的测试文件按名字导进 pytest fixture、再作为参数出现，就是 F811 的样子；**只对 app/ 与 scripts/ 打开** |

## 1. 业界怎么做

F841 / F811 是 pyflakes 的默认规则；测试目录里 F811 与 fixture 冲突是常见误报，通常按目录分开配置。（本批没有另找外部来源。）

## 2. 做了什么

- `test_banned_creator_listings.py`、`test_im_dispute_support.py`、`test_search_privacy.py`、`test_task_flow.py` 各 1 处：`x = 造数据(...)` → `造数据(...)`。
- `test_metrics_truthful.py`：`RULES` 加 `F841`（四个目录）；新增 `APP_ONLY_RULES = "F811"`，只查 app/ 与 scripts/。

## 3. 数据 / 接口

不涉及。

## 4. 两端

不涉及界面。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_metrics_truthful.py::test_no_names_that_are_certainly_wrong` | tests/ 下放一个函数里有未用变量的文件 → 变红并指出 F841；app/ 下放一个重复 `import os` 的文件 → 变红并指出 F811；都删掉后变绿 |

注：ruff 0.15.8 的 F811 不报「同名函数重复定义」（只报导入等被重新绑定的情形），红验用的是重复导入。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| LINT-005 | 本机没装 ruff 时静态检查跳过（沿用） | 台账「欠」 |
| LINT-008 | 测试里的 fixture 改由 conftest 共享，再把 F811 扩到 tests/ | 台账「欠」 |
