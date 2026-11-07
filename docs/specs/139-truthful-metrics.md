
# 139 指标说真话：审核积压指标恒为 0，与后端「一定是错」的静态检查

> 状态：本批实现（V168）。编号 LINT-001~003。
> 来源：V165 收尾时跑 ruff 看到的一条 `F821 Undefined name func`（`app/core/observability.py`）；DRILL-041「引用不存在指标的告警永远不会触发，而且是静默的」。
> 只增不减：指标名、告警规则、指标端点「一个聚合出错不整体 500」的行为都不变；只是让那个指标真的算出来，并让兜底留痕。

## 0. 要解决的问题

`_pending_uploads` 用了没导入的 `sqlalchemy.func`。每次算指标都抛 `NameError`，被它自己的 `except Exception: return 0` 吞掉，
于是 `platform_uploads_pending_review` **恒为 0**，`deploy/alerts.prom.yml` 里「审核积压 > 500」那条告警从上线起就不可能响。
原有测试只检查了「指标存在」与「聚合出错不 500」，正好都过——这是「配了却从不告警」的又一例。

根因有两层：一是没有任何检查会对「未定义的名字」变红（后端没有 lint）；二是兜底的 `except` 什么都不留，错误只剩一个看起来正常的 0。

## 1. 业界怎么做（带来源链接）

- **静态检查只开确定是错的规则**：pyflakes 一类的检查（ruff 的 F 规则，<https://docs.astral.sh/ruff/rules/#pyflakes-f>）报告未定义名字、重复字典键等「一定是错」的问题；本仓库前端 lint 的做法相同（APPB-052b：只开会红在真问题上的规则，否则会被人用 `--quiet` 绕过）。
- **不要悄悄吞异常**：Google SRE 书「Monitoring Distributed Systems」强调告警依赖的信号本身要可信（<https://sre.google/sre-book/monitoring-distributed-systems/>）；指标计算失败时可以给保守值，但必须留下可以被看见的错误记录。

## 2. 数据

无。

## 3. 规则

| 编号 | 内容 |
|---|---|
| LINT-001 | `platform_uploads_pending_review` 真的按 `moderation_status = review` 计数（补上导入） |
| LINT-002 | `observability.py` 的指标计算函数里，每个 `except Exception` 必须记错误日志或重新抛出；`reconcile_ok` 与审核积压的兜底都记 `app.error` |
| LINT-003 | 后端静态检查：`ruff check --select F821,F822,F823,F632,F601,F7 app scripts`（未定义名字、`__all__` 里不存在的名字、赋值前使用、对字面量用 `is`、重复字典键、语法层面的误用），由测试调用；CI 安装固定版本 `ruff==0.15.8` |

顺带核对：全仓 `tests/` 里没有同名测试函数互相遮蔽（同名会让前一个悄悄不跑）；两处 F811 是有意的导入（fixture 显式导入、局部重名），不是遮蔽。

## 4. 两端

无。

## 5. 隐私、授权与边界

错误日志走已有的脱敏格式化（SEC-065），只记指标名与堆栈。

## 6. 闸门与红验

5 处变异全部变红（`scratchpad/mut168.py`）：

| 闸门 | 红验 |
|---|---|
| 审核积压指标真的计数 | 删掉导入 → `test_pending_uploads_metric_counts_the_review_queue` 红（同时 ruff 闸门也红） |
| 只数待审的 | 改成「不是驳回的都算」→ 同上红 |
| 审核积压兜底留痕 | 删掉日志 → `test_every_fallback_in_the_metrics_module_leaves_a_trace` 红 |
| 对账兜底留痕 | 删掉日志 → `test_a_swallowed_metric_error_is_logged` 与上一条红 |
| 一定是错的名字 | 在任一模块里引用未定义的名字 → `test_no_names_that_are_certainly_wrong` 红 |
| 原有行为 | `test_ops_drills.py`（对账指标真的算、聚合出错不 500）照旧通过 |

## 7. 没做的

- **LINT-004 后端风格类 lint**：全仓还有 150 余条未用导入之类的提示，不影响行为；要清理就一次清完再开规则，不在这批做。
- **LINT-005 本机没有 ruff 时静态检查会跳过**：CI 与回归环境都装了；要做到本机也必跑，得把 ruff 放进开发依赖文件（现在只有运行依赖 `requirements.txt`）。
