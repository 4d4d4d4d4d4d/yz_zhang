# NPU 仿真平台核心 Spec 文档集

文档状态：**v1.0 Accepted**
最后更新：2026-05-22
Owners：架构组

## 使用手册(先看这个)

| 文档 | 用途 |
|---|---|
| [架构 YAML 编写指南](../YAML-Authoring-Guide.md) | **怎么写评估 YAML** — 骨架、base/overrides、全模块 config/端口参考、CLI、常见坑、完整配方 |
| [评估报告](../EVALUATION_REPORT.md) | 40+ use case 的实测 delta 表(`scripts/run_all_evaluations.py` 一键重跑) |
| [QEMU 对标分析](../QEMU-Benchmark-Analysis.md) | 平台定位 + 4 项改进空间 |

## 目录

| 文档 | 范围 | 状态 |
|---|---|---|
| [SPEC-001 IModule 接口规范](./SPEC-001-IModule.md) | 所有 NPU 宏模块必须实现的统一抽象接口 | v1.0 Accepted |
| [SPEC-002 反压协议规范](./SPEC-002-Backpressure.md) | 模块间数据传输的反压协议、stall 上报、反压链追溯 | v1.0 Accepted |
| [SPEC-003 架构描述 DSL 规范](./SPEC-003-Architecture-DSL.md) | 平台架构描述的声明式 YAML DSL | v1.0 Accepted |
| [SPEC-004 Functional Simulation Interface](./SPEC-004-Functional-Simulation.md) | 数值精度评估管线的接口与契约 | v1.0 Accepted |
| [SPEC-005 模块库规范](./SPEC-005-Module-Library.md) | Phase 2 真实模块（DSB/MAC/VAU/AVP）的行为/时序/functional 契约 | v0.1 Draft |
| [SPEC-006 Rule-based Mapper 规范](./SPEC-006-Mapper.md) | Phase 4 规则化映射器接口与算法（op-graph → 模块指派）| v0.1 Draft |
| [SPEC-007 控制与数据传输模块族](./SPEC-007-Control-Transfer-Modules.md) | MCU / OGU / TAU / DMA / MTU / AGU 行为契约 | v0.1 Draft（Review pending）|
| [SPEC-008 内存与精度模块族](./SPEC-008-Memory-Modules.md) | WB / OB / Quant / SFU | v0.1 Draft（全 4 §§ Accepted + 实现）|
| [SPEC-009 工作负载形变与互连](./SPEC-009-Workload-Interconnect.md) | IM2COL / RDC / NoC / CDE / Transpose | v0.1 Draft（全 5 §§ 实现 + 测试）|
| [SPEC-010 系统基础设施](./SPEC-010-System-Infrastructure.md) | PMU / SYNC | v0.1 Draft（全 2 §§ 实现 + 测试）|
| [SPEC-011 DRAM 子系统与专用计算](./SPEC-011-DRAM-Specialized.md) | MC / L2 / SE / TLU / CMDQ / MMU | v0.1 Draft（全 6 §§ 实现 + 测试）|
| [SPEC-012 Trace-Driven 激励](./SPEC-012-Trace-Driven-Stimulus.md) | TraceProducer — 播放真实模型算子序列 | v0.1 Draft（实现 + 测试）|
| [SPEC-001 v1.1 增订](./SPEC-001-v1.1-amendment.md) | Area 维度 + clock_domain | v1.1 Draft（Review pending）|
| [SPEC-003 v1.1 增订](./SPEC-003-v1.1-amendment.md) | `__relocate__` / `clock_domains` / `physical_dimension` | v1.1 Draft（Review pending）|
| [SPEC-005 v1.1 增订](./SPEC-005-v1.1-amendment.md) | 现存模块 area 系数 + UNPACK capability | v1.1 Draft（Review pending）|
| [v1.1 评审请求](./review-v1.1-proposal.md) | 上述 4 文档的评审入口 | Awaiting Review |
| [ADR-001 关键技术决策记录](./ADR-001-Key-Decisions.md) | 6 条核心决策 | Accepted |
| [ADR-002 模块身份判定标准](./ADR-002-Module-Identity.md) | 新 IModule 子类 vs. capability flag 化的判定规则 | Accepted |
| [Review v0.1](./review-v0.1.md) | v0.1 交叉一致性审查（历史） | 历史 |
| [Review v1.0](./review-v1.0.md) | v1.0 最终评审，决议 Approved | Accepted |

## 依赖关系

```
SPEC-001 (IModule) ──┬── SPEC-002 (Backpressure)
                     ├── SPEC-003 (DSL)
                     ├── SPEC-004 (Functional)
                     └── ADR-002 (Module Identity)

ADR-001 (Key Decisions) → 解释 SPEC-001/002/003 的设计取舍
ADR-002 (Module Identity) → 决定何时新写 IModule 子类
```

## v1.0 状态

### Review R6 修订（10/10 完成）

| # | 严重度 | 位置 | 状态 |
|---|---|---|---|
| 1 | 高 | SPEC-001 §3.1 / 3.1.1 | ✅ `module_type()` 命名规范 + 正则 |
| 2 | 高 | SPEC-002 §3.4 | ✅ 多生产者反压归因 |
| 3 | 高 | SPEC-002 §5.1 | ✅ Cross-Domain Transport (CDC) |
| 4 | 高 | SPEC-003 §6 | ✅ 列表 override `__append__` / `__remove__` |
| 5 | 中 | SPEC-002 §3.3.1 | ✅ Tracer Realtime vs Offline |
| 6 | 中 | SPEC-002 §7 | ✅ 7+3 条仿真不变量 |
| 7 | 中 | ADR-001.2 Constraints | ✅ 禁链式继承 + 生命周期 tag |
| 8 | 中 | SPEC-001 §3.3 | ✅ IClock 接口完整定义 |
| 9 | 低 | SPEC-003 §5 Phase 3.5 | ✅ 配置一致性 warning |
| 10 | 低 | SPEC-004 | ✅ Functional Simulation Interface |

### 开放问题决议（全部落地）

| ID | 决议 | 落地位置 |
|---|---|---|
| D1 | 模块身份判定 6 条硬规则 | ADR-002 |
| D2 | mapping_hints 仅消歧、窄 schema | SPEC-003 §3.4 + §4 |
| D3 | remove_modules 自动 prune（warn）+ add_connections 引用检查（error） | SPEC-003 §5 + §6 |

## 后续:Spec-Driven 实现

v1.0 已 Accepted,以此为契约启动实现。任何与 spec 不符的实现视为 bug,通过修订 spec 或修订代码来恢复一致(spec 修订需重新走 review)。

### 实现 Phase

| Phase | 范围 | 主要交付 |
|---|---|---|
| Phase 0 | 详细设计 | SystemC kernel + pybind11 binding 设计文档、IClock 实现细节、SPEC-004 NumericalEngine 实现路径 |
| Phase 1 | Python 骨架 | interfaces/ + core/ 抽象类、ModuleRegistry、NumericalModelRegistry、Dummy 模块、端到端最小链路测试 |
| Phase 2 | 模块库 | DAGC / DSB / MAC / VAU / AVP 真实模块的 timing + functional 实现 ✅（行为契约见 SPEC-005；timing 系数待 Phase 5 校准）|
| Phase 3 | 架构描述与 Elaborator | YAML 加载、Schema 校验、Override 合并、9 阶段 elaboration |
| Phase 4 | Mapper 与报告 | Rule-based Mapper ✅（SPEC-006）、反压链追溯 ✅、不变量检查 ✅、报告生成 ✅ |
| Phase 5 | 校准与 Use Case | DAGC/DSB/MAC 校准记录、AGU-W 减半 use case 端到端跑通 |

### v1.1 候选项

源自 v1.0 spec:
- 随机算子 / stochastic rounding（SPEC-004 §9）
- 多 die / 多 chip functional sim 精度建模（SPEC-004 §9）
- MAC 劈裂按 ADR-002 重新判定身份
- 模块 spec 模板加 ADR-002 触发条件标注栏
- 实现层批量改名 `MTU_Fused → MtuFused`,同步 DSL 例

源自实现期暴露的 spec 澄清(implementation-phase findings):
- **SPEC-001 §3.1 增加 `assign_id(instance_id)` 约定** —— 模块需要知道自己的 DSL 实例 id 才能正确填 `record_stall(module=...)` 与 port `owner_module`,目前以非正式约定挂在 Elaborator Phase 5 中 (commit cdeed59)。建议作为 IModule 必选生命周期方法,在 bind_services 之前调用。
- **SPEC-002 §7 INV-3 收紧定义** —— 字面"survivors > 0 即 deadlock"会把空轮询的 Consumer 误判为死锁。实现中改为"survivors > 0 **且** 任一连接 in_flight > 0",与 §7 原文"BACKPRESSURE 挂起"对齐 (commit 3157746)。建议在 §7 加旁注澄清。
- **SPEC-002 §7 INV-W3 平均利用率采样方法** —— 当前实现用终态采样近似,完整方案需要 per-cycle 采样基础设施。建议明确两种实现路径与各自精度等级。
- **SPEC-002 §3.4 multi-producer 归因数据源** —— v1.0 spec 未明确归因数据是来自 stall 事件还是连接级 per-producer 计数。实现选择后者(`TlmConnection.producer_activity()`),并在 §3.4 加约定。
- **SPEC-002 §3.3 BackpressureTracer 时间窗口** —— v1.0 spec 写 `time_window_ps` 是必需参数,实现期默认 None 表示完整历史更实用。建议 §3.3 显式说明 None 语义。
- **SPEC-003 §7 / comparator `cycle_delta` 不是延迟指标** —— 已落地:Phase 2 模块 `behavior()` 是无限生成器(永不 StopIteration),调度器对任何含常驻模块的架构都会跑满 `max_cycles`,故 `cycles_run` 反映预算而非完成时间。**实现层已补强**:`TlmConnection.last_dequeue_time_ps` 记录最后一次成功 dequeue 时刻,`SimulationResult.drain_time_ps = max(c.last_dequeue_time_ps)` 是稳态流水线的真延迟指标;`compare()` 输出 `drain_time_delta_ps`/`drain_time_delta_pct`,markdown 报表与 summary_text 均以 drain_time 为首要行。建议在 SPEC-003 §7 显式补一句"`cycles_run` 是预算,稳态延迟用 `drain_time_ps`"。
- **ADR-001.1 生成器帧阻断二进制 checkpoint(QEMU §3.2 / 路线 #4)** —— 已诊断并部分落地:模块在途时序状态活在 `behavior()` **生成器帧**内(如 MAC 的 `for _ in range(fill_n): yield` 倒计数),`snapshot_state()`(SPEC-001 §3.1)不暴露、Python 生成器不可 pickle,故**二进制 loadvm 在 Python 运行时结构性不可行**,需把每个 `behavior()` 重写成显式外化状态机 —— 属 Phase 5 SystemC。**实现层已落地可行子集**:`evaluation/snapshot.py` 的 `capture_state`/`snapshot_at_cycle` 产出只读全片 `StateSnapshot`(savevm 数据视图,CLI `snapshot`),并利用 §3.3 确定性把"restore 到第 N 拍"实现为**确定性重放**(两次重放逐字段相同,`test_state_snapshot.py` 证明)。建议 ADR-001.1 补一句"mid-op 二进制 checkpoint 依赖 SystemC;Python 运行时以确定性重放替代"。
- **SPEC-006 Mapper 拓扑盲 → 瓶颈误判** —— 已诊断并旁路:RuleBasedMapper 只按 op→module 路由算 `bottleneck_module`,**不读架构连接拓扑**,故在 wired 数据通路上误判瓶颈 —— attention chip 上 Mapper 把 `mac`(6 matmul 路由到此)当瓶颈,但真实吞吐由**路径上最慢的级** `avp`(II=512,每个 token 都串过它)决定。`evaluation/pipeline.py::analyze_pipeline_bottleneck` 以**实测**归因绕过(建模 drain 误差 0.1%,`test_pipeline_bottleneck.py`)。**v1.1 候选**:让 cost-model mapper 读连接图,按"路径上所有级的 max II"估吞吐,而非"路由到本模块的 op 串行和"。
- **SPEC-005 AVP 面积对 vector_width 不敏感(area 模型缺项)** —— `sweep avp.vector_width 16,32,64` 实测:drain 随向量宽度显著下降(4232→2440→2312),但 `total_area_um2` **三点完全相同**(141,810)。4× 向量宽度不涨面积不合物理 —— 当前 AVP 面积模型未把 vector_width 计为面积驱动项。属 CLAUDE.md 所述"面积系数是 pre-silicon 估计,待 Phase 5 标定"范畴。**v1.1/Phase 5 候选**:让 AVP(及同类)面积随数据通路宽度缩放,使 PPA 权衡(throughput vs area)在扫描中可见。
- **SPEC-005 estimate_latency 形状敏感 vs 运行时形状无关(MAC 等)** —— 发现不一致:MAC 的 `estimate_latency(op)` 按 `macs=m·k·n`、`compute=ceil(macs/PE)` **随算子形状缩放**,但运行时 `behavior()` 的 `_compute_cycles()` 返回 `max(1,cols//rows)+1` —— 一个**只依赖阵列几何、与 token 形状无关的常数**。两个时序模型用不同公式,互不一致,是 reconcile 静态估 vs 实测 gap 的一个来源(另一来源见上条拓扑盲)。**v1.1 候选**:统一二者 —— 要么让运行时按 token bytes/shape 计算服务拍(更真实),要么让 estimate 退化为与运行时一致的常数下界,并在 SPEC-005 明确"每 token 服务时间"的权威定义。**不在 v1.0 静默改**(CLAUDE.md 约定)。
