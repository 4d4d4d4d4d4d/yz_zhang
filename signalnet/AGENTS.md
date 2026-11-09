# AGENTS.md —— 贡献者工作协议（AI 代理与人类通用）

> 这是进入本项目后**第一个**要读的文件。所有写入 `signalnet/` 的代码都必须遵守本协议。

## 1. 入库前必读（按顺序）

| # | 文件 | 读什么 | 何时可跳过 |
|---|---|---|---|
| 1 | `AGENTS.md`（本文件） | 工作协议 | 从不 |
| 2 | `TODO.md` | 当前最该做什么（自动区由 harness 生成） | 从不 |
| 3 | `docs/SPEC.md` | 你要实现的需求行 + §4 不变量 | 从不 |
| 4 | `docs/ARCHITECTURE.md` | 分层规则、禁止依赖 | 改动只涉及测试/文档时 |
| 5 | `docs/VISION.md` | 为什么这么设计 | 已熟悉项目时 |
| 6 | 目标模块源码 + 对应 `tests/test_*.py` | 现有实现与测试风格 | 从不 |
| 7 | `docs/adr/` | 相关历史决策 | 不涉及架构变更时 |

## 2. 怎么写

### 2.1 一次迭代 = 一个需求

1. 从 `TODO.md` 取**最上面**一项（🔴 > 🟠 > 🟡 > 🔵 > ⚪）。
2. 若是新需求：先在 `docs/SPEC.md` 把它的优先级改为 `P0`，补全验收标准（**先改 SPEC，再写代码**）。
3. **先写测试**：在测试 docstring 里写上需求 ID，例如 `"""REQ-RK-005"""`。确认测试失败。
4. 写最小实现让测试通过。
5. 运行门禁，全部通过后提交。

### 2.2 编码规范

- Python ≥ 3.11，只依赖标准库 + `cryptography`。新增依赖需要写 ADR。
- 模块顶部 docstring 必须列出“相关需求：REQ-...”。
- 数据对象用 `@dataclass(frozen=True)`；签名对象提供 `payload()`、`id`、`verify()`、`to_dict()/from_dict()`。
- 机制层（L0–L2）**不得**读取时间、随机数、网络、文件；一律参数传入。
- 金额一律整数 micros；分数用 float 但结算结果 `round(.., 6)`。
- 错误用模块内的 `XxxError` 异常，不要返回 None 表示错误（“无效曝光”这类业务结果除外）。
- 注释与文档用中文；标识符用英文。
- 新模块必须在 `harness/gate.py::LAYERS` 登记层级。

### 2.3 禁止事项（直接违背 SPEC §4 不变量）

- ❌ 加入任何可转让余额、代币、`transfer` 接口（INV-1）
- ❌ 让排序读取广告、出价、付费字段（INV-2）
- ❌ 分账出现未分配的余数（INV-3）
- ❌ 为了让门禁通过而删除/跳过测试、降低断言强度、修改门禁阈值

## 3. 写完以后怎么测

```bash
cd signalnet
pip install -r requirements-dev.txt   # 首次
make hooks                            # 首次：安装 pre-commit 门禁
make test                             # 快速：单元测试
make gate                             # 入库前必须：6 道门禁全部 PASS
make iterate                          # 刷新 TODO.md，看下一项
```

门禁说明（`harness/gate.py`）：

| 门禁 | 检查 | 常见失败与修复 |
|---|---|---|
| docs | 必备文档、SPEC 格式、ID 唯一、Last-Reviewed | 按 SPEC 表格四列格式书写 |
| layers | 分层依赖、禁止边、机制层确定性 | 把时间/随机数改成参数；不要从 ranking 引 ads |
| lint | `ruff check` + `ruff format --check` | `make fmt` |
| tests | unittest 全量 | 修实现，不要改断言 |
| trace | P0 需求必须被测试引用；测试不得引用不存在的 ID | 在测试 docstring 写 REQ-ID |
| demo | 端到端仿真：日志可校验、重放一致 | 新事件类型要在 `SignalNode.replay` 支持 |

## 4. 自动化持续迭代协议

```
┌──────────────┐   ┌────────────────────┐   ┌──────────────┐   ┌───────────┐
│ make iterate │──►│ 取 TODO 自动区第一项 │──►│ SPEC→测试→代码 │──►│ make gate │
└──────▲───────┘   └────────────────────┘   └──────────────┘   └─────┬─────┘
       │                                                           PASS│FAIL→回到修复
       └───────────── commit（message 引用 REQ-ID）+ push ◄───────────┘
```

每一轮：

1. `make iterate` —— 跑全部门禁，把发现的问题写入 `TODO.md` 自动区并打印“▶ 下一项任务”。
2. 实现该任务（遵守 §2）。
3. 实现中发现的、不属于本任务的问题 → 写到 `TODO.md` **手工区**，不要顺手改。
4. `make gate` 通过后提交：`feat(REQ-RK-005): 低共识内容不进入推荐流`。
5. 再次 `make iterate`，确认该项已从自动区消失。
6. 单轮最多处理 1 个需求；连续 3 次门禁失败则停止并在 TODO 手工区记录阻塞原因，等待人工。

驱动方式：

- 人工：按上面步骤执行。
- Claude Code：`/loop make iterate 然后按 signalnet/AGENTS.md §4 完成下一项任务`（自定步调循环）。
- CI：`.github/workflows/signalnet.yml` 在每次推送和每周一运行门禁与 iterate 报告。

## 5. 定期完善 SPEC（每 14 天，或每完成一个里程碑）

`iterate.py` 在 `Last-Reviewed` 超过 14 天时生成 🟠 待办。复核清单：

1. 已实现需求的验收标准是否仍与代码一致？不一致以 SPEC 为准修代码，或修 SPEC 并在变更记录说明。
2. `TODO.md` 手工区中积累的问题，是否需要变成新需求（分配新 ID，ID 永不复用）？
3. P1 中哪些应升为下一批 P0？更新 `docs/ROADMAP.md`。
4. VISION §9 开放问题有无新答案？有则写 ADR。
5. 更新 `Last-Reviewed` 日期与 §5 变更记录。
