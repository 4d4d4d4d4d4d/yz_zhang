
# 382 功能面漏登记在 harness check 当场报（FEAT-002）

> 状态：本批实现（V410）。编号 FEAT-002。
> 来源：V408 的全量回归（ca51646）失败了 1 条。新增的 App 子页 `verifyDesk` 没登记进 `docs/FEATURE-SURFACE.txt`，等了 74 分钟才红。
> 只增不减：`harness check` 多一项检查，功能面清单的规则（只增不减、下线进 `RETIRED`）不变。

## 0. 要解决的问题

功能面清单（FEAT-001）要求每个接口、网页路由、SDK 方法、App 文件都登记在案，只增不减。漏登记由 `tests/test_feature_surface.py` 抓。

这个测试要导入整个服务端，放在提交前的静态闸门集里。V408 收尾时我只跑了其中几项，把它漏了，结果等到 74 分钟的全量回归才发现。

问题不在于没有闸门，在于闸门离写代码的地方太远。

## 1. 做法

网页路由、SDK 方法、App 文件这三类功能面，只读文件就算得出来，不用启动服务端。
- 把这部分搬进 `harness check`：算出应有的项，和清单比，缺的逐条报「功能面清单漏登记：…（运行 `python -m scripts.feature_surface --write`）」。
- 接口那一类要导入应用才算得出，仍由 `test_feature_surface.py` 管。
- `harness check` 每批收尾都跑，几秒钟就出结果。

## 2. 数据 / 接口

不涉及。

## 3. 补登记

`docs/FEATURE-SURFACE.txt` 补上 `app verifyDesk`，共 1325 项。

## 4. 两端

不涉及界面：只改工程检查。

## 5. 隐私、授权与边界

只读仓库里的源文件与清单文件。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_harness.py` 新增 1 条：<br>清单里删掉 `app verifyDesk` 必须报；删掉 `sdk declineVerificationOrder` 必须报；补回后不报 | 去掉 `check()` 里这一行调用：红 |
| 完整的提交前静态闸门集（13 个文件） | 177 条照过 |

## 7. 没做的

没有新增欠账。
