
# 359 响应形状扫除闸门改读语法树、棘轮 44 → 22

> 状态：本批实现（V386）。编号 CLI-083b、CLI-083c。
> 来源：357 号 spec 第 7 节「没做的」；BACKLOG V386。
> 只增不减：SDK 只加字段、把读不出的写法改成等价的具名接口；有一处是把错误的声明改对（`amlStats`，见第 2 节）。服务端不改。

## 0. 要解决的问题

1. **扫除闸门本身数得不准（CLI-083c）**。它用文本正则找 `_assert_shape(第一个参数, "名字")`：
   - 写在没被执行的地方的断言也算覆盖：改了名的函数、被 `skip` 的测试，甚至文档字符串里的一行字；
   - 第一个参数里有逗号（`client.get(url, headers=h).json()`）就认不出；
   - SDK 声明写成 `import('./types').OwnSpace` 时，接口名对不上已有的 `_assert_shape(x, "OwnSpace")`。
2. 未验证的调用点还有 44 个（CLI-083b）。

## 1. 做法

- `_runtime_checks_in(source)` 改读语法树：只认 `test_` 开头、没被 `skip` / `skipif` 的函数里（含其中的嵌套函数）的 `_assert_shape(…, "名字")` / `_assert_inline_shape(…, "名字")`。
- 扫除时把 `import('./types').X` 归一成 `X` 再找断言。
- 闸门自测 `test_cli083c_only_assertions_that_actually_run_count`：一段样例源码里，改名函数、辅助函数、被 skip 的、写在文档字符串里的断言都不算；参数带逗号的和嵌套函数里的照样算。
- 实测：改读语法树前后，多认出 12 个（参数带逗号），去掉 5 个文本误报，没有任何断言是放在辅助函数里的（所以不会有正当的检查被误伤）。
- `test_shape_sweep_v384.py` 再补一批真实响应断言：合规与封禁、资质待审队列、存证链、合作体分配提案与主体记录、新建合作体、团队支出、机器授权。

## 2. 扫出来的问题

| 接口 | 问题 | 改法 |
|---|---|---|
| `amlStats` | SDK 声明 `Record<string, number>`，服务端实际返回 `{ total, by_status: {…}, by_pattern: {…} }`——按声明读 `by_status` 会当成数字 | 新接口 `AmlStats`（两端都还没有界面用它，改对没有破坏） |
| `banUser` | 服务端一并返回封禁时的影响面 `impact`，SDK 没声明 | 加 `impact: BanImpactView` |
| `verifyAnchorChain` | 链完好时服务端给链头哈希 `head`，SDK 没声明 | 加 `head?: string` |
| `requestTeamSpend` | 额度内自动批准时没有 `reason`（只有进审批才有），两条路都有 `amount_cents`；SDK 把 `reason` 写成必有、漏了 `amount_cents` | `amount_cents: number`、`reason?: string`（Web 与 App 的调用处类型检查照过） |
| `PayoutProposalView` | 一行多字段，闸门读不出任何字段 | 逐行，`approvals` 改具名 `PayoutApproval` |
| `AnchorCoverage.receipts` | 多行内联数组 | 具名 `AnchorReceipt` |

## 3. 结果

- 未验证调用点：44 → **22**；棘轮 `MAX_UNVERIFIED` 44 → 22。
- 剩下 22 个多是交叉类型声明（`Task & {…}`、`Mission & {…}`、`Contract & {…}`）、`Partial<Me>`、`string[]` 与 `X | null` 这类闸门比不了的写法，以及要造复杂数据的接口（核验单、智能体执行、争议和解）。

## 4. 两端

不涉及界面改动（SDK 类型改动两端类型检查照过）。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_response_shape_sweep.py`（闸门自测 + 棘轮 22）、`test_shape_sweep_v384.py`（14 条） | `scratchpad/mut386.py` 10 处首轮全部变红：<br>闸门不看函数名、不看 skip、不归一 `import()` 写法；去掉 `head`、`impact`、`AmlStats.by_pattern`、`requestTeamSpend.amount_cents`；`reason` 改回必有；`PayoutApproval` 改错键；棘轮改成 21 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| CLI-083b | 还有 22 个调用点未验证（多是交叉类型等闸门比不了的写法） | 欠：下一步让比较器认交叉类型（`A & { … }` = A 的字段加内联字段），而不是逐个改写 SDK 声明 |
| — | `AnchorCoverage.receipts` 在测试里是空列表，嵌套的回执字段没被真实比到 | 欠：要接第三方存证（「外」）后才有回执 |
