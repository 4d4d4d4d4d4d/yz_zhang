
# 290 测试 fixture 由 conftest 共享，F811 扩到 tests/

> 状态：本批实现（V317）。编号 LINT-008。
> 来源：270 号 spec「没做的」——「测试里的 fixture 改由 conftest 共享，再把 F811 扩到 tests/」；BACKLOG V317。
> 只增不减：没有删任何测试或断言；三个 fixture 原样挪进 `tests/conftest.py`（内容不变），各文件只是不再导入它们。ruff 规则只加不减：F811 进了四个目录的 `RULES`，`APP_ONLY_RULES` 那一遍照旧跑。

## 0. 先数

`ruff check --select F811 tests migrations`：12 处、4 个文件，全是「从别的测试文件按名字导入 pytest fixture，再作为参数出现」：

| fixture | 原来在 | 导入它的文件 |
|---|---|---|
| `admins`（两位运营） | `test_packs.py` | `test_radar_draft.py`（5 处）、`test_knowledge_expiring.py`（2 处） |
| `withholding`（切到平台代扣） | `test_tax_withholding.py` | `test_tax_remit_confirm.py`（4 处） |
| `runner`（换上 RecordingRunner） | `test_orchestrator_agents.py` | `test_experience_scrub.py`（1 处） |

## 1. 业界怎么做

pytest 官方建议跨文件共用的 fixture 放 `conftest.py`，自动对同目录下的测试可见、不用导入；这样静态检查也不会把参数当成重复定义。（本批没有另找外部来源。）

## 2. 做了什么

- 三个 fixture 原样挪进 `tests/conftest.py`（`runner` 在 fixture 里按需导入 `RecordingRunner`，假实现仍只有一份）；原文件留一行注释指向 conftest。自己定义了 `runner` 的测试文件（5 个）照旧用自己的——同名时文件内的优先。
- 四个文件去掉对这三个名字的导入；`test_packs.py`、`test_orchestrator_agents.py` 去掉因此不再用的导入。
- `test_metrics_truthful.py`：`RULES` 加 `F811`（app/、scripts/、tests/、migrations/ 都查）。

## 3. 数据 / 接口

不涉及。

## 4. 两端

不涉及界面。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_metrics_truthful.py::test_no_names_that_are_certainly_wrong` | 在 tests/ 下放一个「从 test_packs 导入 `_publish` 再定义同名函数」的文件 → 变红并指出 F811；删掉后变绿 |
| 受影响的 11 个测试文件 | 挪动前后全部通过 |

## 7. 没做的

无新增欠账。
