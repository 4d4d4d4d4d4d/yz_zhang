# 整体 Review（v0.1）

文档状态：Draft v0.1
作者：架构组
范围：对 SPEC-001 / SPEC-002 / SPEC-003 / ADR-001 做交叉一致性 review

本节对前面三份 SPEC 和 ADR-001 做交叉一致性 review，找出潜在问题、漏洞、改进点。

## R1：交叉一致性检查

### R1.1：IModule 与反压协议的衔接 — ✅ 一致

- IModule.input_ports() / output_ports() 返回的就是 ITransportPort 实例
- 模块通过 send() 实现反压，无需自己处理
- IModule.bind_services 注入 IStatSink，反压自动通过 transport 层记录到 stat_sink
- 验证：SPEC-001 §3.1 的接口与 SPEC-002 §3.1 的 ITransportPort 引用一致

### R1.2：IModule 与 DSL 的衔接 — ⚠️ 发现 1 个问题

DSL 中 `modules.<id>.type` 字符串与 `IModule.module_type()` 必须严格匹配。

**问题**：当前 SPEC-003 中 DSL 用了诸如 "DAGC", "MatVecArray", "DDRController" 等类型名，但 SPEC-001 没有规定命名规范，只说"PascalCase，全平台唯一"。

**建议修订**：在 SPEC-001 §3.1 增加：

> `module_type()` 命名规范：
> - PascalCase
> - 第一个字母大写
> - 不含数字开头
> - 不含特殊字符
> - 推荐 ≤ 24 字符
> - 必须与 `docs/module_specs/<filename>.md` 文件名（去扩展名后 snake_case）对应

修订后应在 SPEC-001 与 SPEC-003 之间保持引用一致。

### R1.3：DSL Override 与 IModule 配置的一致性 — ⚠️ 发现 1 个潜在问题

**问题**：override 中 `modules.<id>.config.<key>` 是 shallow merge。如果某个 config 是嵌套 dict（如 `precision_modes: [INT8, FP16]`），shallow merge 会完全替换列表，而不是合并。这可能导致用户期望"在原列表上加一个 FP8"时意外地删除了其他模式。

**建议修订**：

- 在 SPEC-003 §6 明确：列表类 config override 默认是替换，不是 append
- 提供 `__append__` / `__remove__` 特殊语法支持列表修改：

```yaml
modules:
  mac:
    config:
      precision_modes:
        __append__: [FP8]   # 在原列表上追加
```

### R1.4：反压链追溯与 EventBus 的衔接 — ✅ 一致

- BackpressureTracer 订阅 `stall.*` topic
- transport 层和模块都通过 `IStatSink.record_stall()` 上报
- record_stall 应该同时发 EventBus 事件，便于 Tracer 实时订阅

**补充**：SPEC-002 §3.3 的 BackpressureTracer 应明确说明它通过 EventBus 还是直接通过 StatSink 历史记录工作。建议：

- **实时模式**：订阅 EventBus
- **离线模式**：扫描 StatSink 的历史记录

### R1.5：ADR-001.4 与 SPEC-002 的衔接 — ✅ 一致

ADR 决策的 blocking transport 模型与 SPEC-002 的 send() 语义一致。

## R2：缺失点识别

### R2.1：缺失 — 多生产者归因策略

**问题**：当多个 producer 向同一个 sink 写入（典型场景：vau, mac, mtu, tau 都往 dsb 写），下游反压时，caused_by 字段指向 dsb，但 dsb 自身可能是因为 bank conflict，bank conflict 又是因为多个 producer 同时申请同一 bank。

**建议补充到 SPEC-002**：

- §3.3 增加"多生产者反压归因"小节
- BackpressureTracer 提供 `trace_multi_producer_contention()` 方法
- 当 caused_by 是有 internal_resource_conflict 的模块时，进一步追溯所有 producer

### R2.2：缺失 — Functional 仿真与 Timing 仿真的关系

**问题**：之前讨论中提到"MU 量化 ROUND vs RNE 的精度评估"是 functional 仿真，不是 timing 仿真。但当前三份 SPEC 都聚焦 timing 仿真，没有定义 functional 仿真的接口。

**建议**：写 SPEC-004：Functional Simulation Interface（数值精度评估管线）。这是独立的子系统，与 timing 仿真共用模块定义但不共用 ITransportPort。

**优先级**：中。可以放到 Phase 2。

### R2.3：缺失 — 时钟域跨越（CDC）建模

**问题**：DSL 支持多时钟域（main_clk / ctrl_clk / ddr_clk），但 SPEC-002 的 ITransportPort 没有规定 CDC 处理。

**建议补充到 SPEC-002**：

- 增加 "Cross-Domain Transport" 小节
- 跨时钟域的连接自动插入异步 FIFO，增加额外 latency
- 跨域 stall 的追溯保留时钟域信息

### R2.4：缺失 — 配置变更的影响传播

**问题**：override 改了 module A 的配置，是否影响 module B 的行为？例如改 mac 的 cols 从 128 到 64，可能影响 dsb 的 read pattern。

**当前**：DSL 只覆盖 A 的配置，B 的配置不变。但实际 B 的最优配置可能依赖 A。

**建议**：

- DSL 不自动传播（保持声明式简单性）
- 但 Elaborator 在 semantic validation 阶段做"配置一致性检查"，提示潜在不匹配（warning 不是 error）
- 例：mac.cols=64 但 dsb.read_burst_size=128_bytes → warn "read burst 大于 mac 列宽，可能造成 unaligned 访问"

**优先级**：低。Phase 3 再加。

### R2.5：缺失 — 仿真器自身的 self-check

**问题**：仿真结果出来怎么判断仿真本身没错？

**建议**：

- 每次仿真结束输出 invariant check：
  - 所有 input token 都被消费了
  - 所有 in-flight token 都到达目的地
  - 无死锁
  - 反压链无环
- 不通过的仿真标记为 INVALID

写到 SPEC-002 §3.3 的扩展。

## R3：风险点识别

### R3.1：风险 — SystemC 性能不达标

**风险描述**：SystemC AT mode 对 BERT-base 完整推理可能仍然慢（每层 matmul tile 数 × 模块状态机推进）。

**预防措施**：

- Phase 1 早期跑 micro-benchmark 验证（单层 matmul 仿真 < 30 秒）
- 若达不到，考虑：
  - 简化非关键模块到 throughput model
  - 大 tile 用 LT mode（loosely timed）+ 关键路径 AT mode
  - 并行 DES（每个模块独立 thread）

### R3.2：风险 — DSL 的 base+overrides 演变成不可维护的"补丁堆"

**风险描述**：随着 variant 越来越多，每个 variant 都基于 baseline 打补丁，最终 baseline 改一处所有 variant 都受影响，且无人能预测影响。

**预防措施**：

- 每个 variant 必须有 expiration 或 promotion 计划：要么淘汰，要么提升为新 baseline
- 定期 "baseline refresh"：当 variant 趋于稳定，作为新 baseline 发布，旧 variant 归档
- 不允许 variant 链式继承（一个 base 一个 override，不能 base 别人的 override）

写入 ADR-001.2 的 consequences。

### R3.3：风险 — 模块开发者绕过 caused_by 强制规则

**风险描述**：开发者为了"看起来干净"或图省事，可能用 try_send + 自定义 stall 上报，绕过自动归因，导致反压链断裂。

**预防措施**：

- StatSink 在收到 `record_stall(reason=OUTPUT_FULL, caused_by=None)` 时报错或 warn，因为这种组合在协议上是不合法的
- CI 中 lint：模块代码扫描 record_stall 的所有调用点，校验 caused_by 是否合理填写
- 文档明确：try_send 用于实现优先级仲裁等高级场景，常规情况用 send

## R4：演进路径检查

### R4.1：3D 架构（DAGC 外置）的演进路径 — ✅ 支持

DSL 的 topology 已支持 `multi_die_3d`，inter_die 连接可以建模 TSV。
新增 `die_id` 字段，DAGC 移动到另一 die 即可。
不需要修改 IModule 或反压协议。

### R4.2：多 die 多 chip 演进路径 — ✅ 支持

Topology 设计已考虑多 die。未来扩展到多 chip，可以增加 cluster 层级。
Astra-sim 风格的网络层可以挂在 inter_die 之上，作为新的子系统。

### R4.3：从 timing 仿真到 functional 仿真的演进 — ⚠️ 需要新 SPEC

如 R2.2 所述，需要 SPEC-004 定义 functional 仿真接口。
模块定义本身不需要改，functional 仿真复用 IModule 的 capability 描述，但用独立的 numeric simulation engine。

### R4.4：从 rule-based mapper 到 search-based 的演进 — ✅ 支持

IMapper 接口是抽象的，rule-based 和 search-based 都实现这个接口。
迁移成本：替换 mapper 实现，规则迁移为搜索约束。

## R5：可执行性检查

### R5.1：第一周能做什么？

读完这份 spec 文档，第一周应该能：

- 实例化 ModuleRegistry，注册一个 dummy module
- 实现 SystemCKernel + 简单 EventBus
- 实现一个 IModule 子类（如 dummy producer / dummy consumer）
- 跑通最简单的 send + 自动 stall 上报路径
- BackpressureTracer 能输出最简单的反压链

验证：spec 文档是否足够支撑第一周开发？

逐项核对：

- [x] IModule 接口已定义完整
- [x] ITransportPort.send 语义清晰
- [x] StatSink 接口存在
- [x] EventBus 接口存在
- [x] ModuleRegistry 用法清晰
- [⚠️] SystemC kernel 的具体实现（pybind11 binding 细节）未详述 → 这是实现 ADR，留给 Phase 0 detailed design
- [⚠️] Clock 抽象 IClock 提了但接口很简略 → 需要补充

### R5.2：spec 是否过度设计？

自查清单：

- ❓ ModuleState 真的有 5 个字段那么必要吗？
  - 答：busy 和 current_op 是必需，pipeline_occupancy 和 fifo_levels 用于可视化但可选。建议把可选字段标 Optional
- ❓ EnergyEstimate 区分 dynamic 和 static_pj_per_cycle 必要吗？
  - 答：必要。AGU-W 砍带宽主要省 dynamic，静态省得少。这个 trade-off 必须能算
- ❓ Capability.depends_on 真的有用吗？
  - 答：必要。bfp8_bfp16_mix 依赖 bfp8 和 bfp16 都激活。Schema 校验需要

结论：当前 spec 没有明显过度设计。

## R6：Review 总结与修订建议

需要修订的点列表（按优先级排序）：

| # | 严重度 | 位置 | 修订内容 |
|---|---|---|---|
| 1 | 高 | SPEC-001 §3.1 | 增加 `module_type()` 命名规范 |
| 2 | 高 | SPEC-002 §3.3 | 增加"多生产者反压归因"小节 |
| 3 | 高 | SPEC-002 全文 | 增加 Cross-Domain Transport 小节 |
| 4 | 高 | SPEC-003 §6 | 明确列表 override 语义，引入 `__append__` |
| 5 | 中 | SPEC-002 §3.3 | 明确 BackpressureTracer 是实时还是离线 |
| 6 | 中 | SPEC-002 | 增加 simulation invariant check |
| 7 | 中 | ADR-001.2 | 补充"避免 variant 链式继承"约束 |
| 8 | 中 | SPEC-001 | 补充 IClock 接口细节 |
| 9 | 低 | SPEC-003 §5 | Elaborator 增加配置一致性 warning |
| 10 | 低 | 新文档 | SPEC-004 Functional Simulation Interface（Phase 2） |

修订后应再走一次 review，确认无新引入的不一致。

## R7：下一步行动建议

按 spec-driven 流程，下一步应该：

- **本周内**：依据 R6 列表修订三份 SPEC，发新版给团队 review
- **下周**：组织 1-2 次 spec walk-through 会议，逐条过设计意图
- **第 3 周**：开始 Phase 0 detailed design（重点是 SystemC kernel 的 pybind11 binding 设计、IClock 完整定义、Functional simulation 的 SPEC-004 草案）
- **第 4 周开始 Phase 1 实现**

并行任务：

- 起草 ADR-002 ~ ADR-005（针对 R6 的其他决策点）
- 起草模块 spec 模板，挑 DAGC、DSB、MAC 三个先写
- 起草第一个 Use Case spec（AGU-W 带宽减半）

---

## 文档元信息

| 字段 | 值 |
|---|---|
| Document Set | NPU Simulator Platform Core Specs |
| Version | 0.1 (Draft) |
| Status | Under Review |
| Last Updated | 2026-05-22 |
| Next Review | TBD |
| Owners | 架构组 |
