# ADR-001：关键技术决策记录

文档状态：Draft v0.2
作者：架构组
依赖：SPEC-001 / SPEC-002 / SPEC-003

v0.2 变更：
- ADR-001.2 Consequences 补充"禁止 variant 链式继承"约束（R6#7）
- 其他 ADR 内容不变

---

## ADR-001.1：仿真内核选用 SystemC TLM-2.0 而非纯 Python

### Status

Accepted

### Context

需要选择仿真内核技术栈。候选方案：

- **SystemC + TLM-2.0**：C++ 框架，IEEE 标准，工业界 EDA 主流
- **纯 Python**（如 SimPy / 自研 event loop）：开发快，团队熟悉
- **gem5**：复用现有仿真器，但 NPU 改造工作量大
- **SST**（Structural Simulation Toolkit）：并行 DES 框架，学术界用

### Decision

选择 **SystemC TLM-2.0 (AT mode) + Python 外围**。

- 仿真内核与模块用 C++/SystemC
- 架构描述、Mapper、报告、可视化用 Python
- 通过 pybind11 桥接

### Rationale

为什么 SystemC：

- **性能**：跑 encoder 完整推理在分钟级，纯 Python 会到小时级
- **反压语义成熟**：TLM AT mode 的 blocking transport 天然支持反压传播
- **工业生态**：未来与 RTL co-simulation、与 EDA 工具链集成有路径
- **IEEE 1666 标准**：长期可维护

为什么不纯 Python：

- 性能不可接受（已用 SimPy 做了原型 benchmark：单层 matmul 仿真比 SystemC 慢 50x）
- 反压协议要从头写，工程量大且容易错

为什么不 gem5：

- gem5 强项在 CPU/Cache/Memory 系统，NPU 模块要重写
- gem5 的 SimObject 系统重，加载慢，不利于实验迭代
- 与团队期望的"差分友好"评估流程不匹配

为什么不 SST：

- 学习曲线陡，生态相比 SystemC 小
- 并行 DES 的收益对单 NPU 场景不显著

### Consequences

正面：

- 性能满足需求（目标：BERT-base 推理仿真 < 10 分钟）
- 反压机制有标准参考
- 长期可与硬件 co-sim 集成

负面：

- 团队需要 SystemC 培训（估算 2-3 周）
- C++ 部分调试复杂度高
- pybind11 桥接需要额外维护

缓解措施：

- C++ 部分严格限制在 Layer 1-2 + 模块库内
- 模块基类用 pybind11 暴露干净的 Python 接口
- 所有上层（架构、Mapper、报告）用 Python，开发速度有保证

---

## ADR-001.2：架构描述用 YAML 而非 Python DSL

### Status

Accepted

### Context

架构描述格式候选：

- **YAML**（声明式数据）
- **Python DSL**（可编程，参数化强）
- **JSON**
- **自定义 DSL**（如 chipyard 的 Scala）

### Decision

选用 YAML。

### Rationale

- **可 review**：架构变更要走 spec review 流程，YAML 易于 diff、加注释、PR review
- **可校验**：JSON Schema 工具链成熟，schema 校验先于代码
- **解耦**：架构描述纯数据，与平台代码完全解耦，未来换实现语言不影响
- **可生成**：未来可以从 IP-XACT、SystemRDL 等转换
- **避免逻辑陷阱**：Python DSL 允许嵌入任意代码，容易混入业务逻辑，破坏架构即数据的原则

不选 Python DSL 的关键原因：架构描述里出现 if/for/import 是个 smell，会让架构演进难以追踪、难以 review。

### Consequences

正面：

- 架构演进有清晰审计路径
- 工具链多（验证、转换、可视化）

负面：

- 参数化弱：100 个相似模块要写 100 遍（虽然现实中不会有这么多）
- 复杂依赖表达受限

缓解措施：

- 通过 override 机制减少重复
- 必要时提供 YAML 预处理器（如 Jinja2 模板，但只作为生成 YAML 的工具，不嵌入运行时）

### Constraints（v0.2 新增）

- **禁止 variant 链式继承**：variant 文件的 `base` 必须指向 baseline 文件（不含 `base` 字段的完整架构）。不允许 variant 再 base 另一个 variant。
  - 理由：链式继承让"baseline 改一处所有 variant 都受影响"变得不可推理，与 ADR 选 YAML 的"可 review、可追溯"初衷冲突
  - 替代路径：variant 趋于稳定后做 **baseline refresh**，把它 promote 为新 baseline，旧 variant 归档
  - 实现：Elaborator Phase 1 加载 `base` 文件时若再发现 `base` 字段，直接抛 `OverrideError`（详见 SPEC-003 §6.3）
- **variant 必须有生命周期标记**：DSL `metadata.tags` 必须包含 `experimental` / `staging` / `promoted` / `archived` 之一，CI 检查
  - `experimental`：探索期，<= 6 周
  - `staging`：评估通过，等待 promote 为 baseline
  - `promoted`：已成为或合并入 baseline，文件保留为历史
  - `archived`：已淘汰，不再 elaborate

---

## ADR-001.3：Mapper 先用 Rule-based，预留 Search-based 演进

### Status

Accepted

### Context

Mapper 候选实现方式：

- **Rule-based**：每种算子有 hardcoded 映射规则
- **Search-based**：定义搜索空间，用 ILP / 启发式 / RL 搜最优
- **Hybrid**

### Decision

Phase 1 用 Rule-based，接口预留 Search-based 演进路径。

### Rationale

- 当前需求是"评估架构变化的影响"，不是"找最优 mapping"
- Rule-based 可解释、可调试、可由架构师审阅
- Search-based 引入大量超参数和搜索复杂度，对当前阶段是过度工程
- 真实编译器是 rule-based + heuristic 混合，先与之对齐

### Consequences

正面：

- 第一版交付快
- 评估结果稳定可重现

负面：

- 评估的是"特定 mapping 下的架构"，不一定是架构的最优能力
- 当 mapping 对结果影响大时，需要标注 "under specific mapping"

缓解措施：

- Mapper 接口 `IMapper.map()` 是抽象的，未来可接入 search-based 实现
- 每个评估实验记录 mapping 版本号，便于复现和对比
- 在报告中明确标注 "mapping strategy: rule_based_v1"

---

## ADR-001.4：反压协议——Blocking Transport + 自动追溯

### Status

Accepted

### Context

反压实现方式候选：

- **Blocking transport**（TLM-2.0 标准）：send 阻塞直到接收
- **Credit-based**：发送方维护信用计数，下游归还信用
- **Token-passing handshake**：显式 req/ack 信号
- **Optimistic + rollback**：先发，反压时回滚

### Decision

Blocking transport + 自动 stall 上报。

### Rationale

- TLM-2.0 标准，工具支持好
- 模块开发者代码简洁：调 `send()`，不用管反压
- 自动 stall 上报和 caused_by 追溯天然支持反压链分析
- 反压传播是事件驱动的，与仿真内核完全契合

不选其他方案的原因：

- **Credit-based**：每个端口要维护信用状态，模块代码复杂
- **Token-passing**：信号级别建模，太低层
- **Optimistic**：不适合仿真器（rollback 破坏因果追溯）

### Consequences

正面：

- 模块代码简洁
- 反压追溯自动化

负面：

- 模块开发者要理解 blocking 语义（不能在反压时做副作用）

约束：

- 模块的 `b_transport` 实现必须是幂等的
- 模块不能在 `send()` 调用周围依赖"必然返回的"时序假设

---

## ADR-001.5：Stall 归因——caused_by 字段强制要求

### Status

Accepted

### Context

反压链追溯需要每个 stall 事件知道"是谁让我等的"。如何获取这个信息？

### Decision

`ITransportPort.send()` 在反压时强制记录 `caused_by = downstream_port.owner_module`，由平台自动完成。模块自报的 stall（如内部资源冲突）可以省略 caused_by（表示无外部原因）。

### Rationale

- 把责任放在 transport 层而非模块层，避免模块开发者漏报或错报
- 自动归因保证 caused_by 信息的完整性和正确性
- BackpressureTracer 依赖完整的 caused_by 链，缺失会导致追溯断裂

### Consequences

正面：

- 反压链追溯无盲区

负面：

- 多生产者向同一 sink 写入时，caused_by 的归因可能在不同时间指向不同上游，需要 tracer 做时间窗口聚合

缓解措施：

- BackpressureTracer 提供时间窗口聚合 API
- 报告中区分"瞬时 caused_by"和"窗口内主要 caused_by"

---

## ADR-001.6：技术栈版本锁定

### Status

Accepted

### Context

依赖版本要稳定，避免上游升级破坏平台。

### Decision

| 组件 | 版本 | 备注 |
|---|---|---|
| Python | 3.11+ | 用 dataclass / typing 新特性 |
| SystemC | 2.3.4 | Accellera 当前稳定版 |
| pybind11 | 2.11+ | C++/Python 桥接 |
| jsonschema | 4.x | DSL 校验 |
| PyYAML | 6.x | YAML 解析 |
| import-linter | 1.12+ | 依赖规则强制 |
| pytest | 7.x | 测试 |
| Ramulator | 2 主线 | DRAM 仿真（Layer 3 之外，单独集成） |

所有版本在 `pyproject.toml` / `CMakeLists.txt` 中锁定，CI 中固化。

### Consequences

重大升级走单独 ADR。
