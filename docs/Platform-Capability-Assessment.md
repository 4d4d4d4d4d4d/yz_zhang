# 平台能力评估:已实现 vs 缺失

文档状态:**评估报告 v1.0** · 最后更新:2026-09-03
用途:诚实盘点本平台能做什么、不能做什么,给设计验证使用者定预期,给后续
开发定优先级。缺口同步登记在 `docs/specs/README.md` 的 v1.1 候选清单。

## 1. 已实现(按层次)

| 层 | 内容 | Spec |
|---|---|---|
| 仿真内核 | IModule 契约、反压协议、逐拍协程调度(SystemC stand-in)、YAML DSL(base+override、9 阶段 elaborator)、不变量、waveform tracer、确定性、quiescence 早退、全片状态快照 | 001/002/003 |
| 硬件模块库(34) | 计算 MAC/VAU/AVP/DAGC/DSB;控制 OGU/MCU/MTU/TAU/AGU/DMA;存储 WB/OB/L2/TLU/MMU/MC/CMDQ;负载/互连 IM2COL/RDC/Transpose/NoC/SE/CDE/Quant/SFU;系统 PMU/SYNC;激励 Producer/Consumer/TraceProducer | 005/007–011 |
| 映射 | rule-based op→module、estimate-vs-measured 对账、拓扑感知**实测**瓶颈归因(复算 0.1–0.4%) | 006 |
| 物理 PPA | 文献接地面积/能量(45nm,90% 面积物理化,vs 公开参考区间内,±30%);`fidelity` 查任意芯片 | 013 |
| 功能模型 | MAC/VAU/AVP/DAGC/DSB 的 golden 结构模型(非 bit-accurate) | 004 |
| 分析工具链(13 CLI) | simulate/compare/trace/estimate/reconcile/**bottleneck**/**energy**/**fidelity**/**sweep**/**optimize**(drain/energy/edp 目标)/snapshot/snapshot-diff | 006/012/013 |
| 端到端案例 | trace 驱动真实模型层;完整 encoder 设计研究(`docs/NPU-Design-Study.md`) | 012 |

**可信度**:逐拍时序机制真实;计算侧 PPA(面积/计算能量/延迟)文献接地、±30%
带、外部锚点校核。**做计算受限层的相对架构权衡可信。**

## 2. 缺失(按重要性,🔴 最关键)

### 🔴 A. 数据搬运能量 + 访存带宽/dataflow 建模(最大缺口)

**现状(已验证)**:workload 动态能量 = Σ 每算子**计算**能量(MAC = macs ×
per-mac),**不含**从 L2/DRAM/HBM 取操作数、模块间搬数据的能量;**无
bandwidth/roofline/data-reuse/tiling/dataflow 模型**。MC 只是模块,DRAM 带宽
未耦合到计算 stall,DRAM 访问能量未计入 workload 总能量。

**为什么关键**:Horowitz 数据——DRAM 32b 访问 640 pJ vs int MAC ~1 pJ,差
**640×**。真实 NPU 的能量与(访存受限层的)延迟**常由数据搬运主导**。当前:
- 只算计算能量 → 总能量可能**低估几倍到几十倍**;
- `docs/NPU-Design-Study.md` 结论"能量是设计不变量"**部分是此缺失的假象**——
  数据搬运恰是随 dataflow/tiling/buffer 变化的那部分,补上后设计间能量会分化。

**需要**:operand/weight 的 DRAM↔on-chip 流量模型、data reuse/tiling
(weight/output/row-stationary)、每字节访存能量计入 workload、带宽饱和→计算
stall 的 roofline。这是离"可信 NPU PPA"最大一步(Timeloop/MAESTRO 类核心)。

### 🟠 B. 建模深度
- **Mapper 基础**:只吃扁平算子表,无 DAG/依赖边、无空间映射(systolic
  tiling/sharding)、无 cost-model/ILP/RL 搜索;`optimize` 只加宽不缩小。
- **无 dataflow/loop-nest 建模**(见 A)。
- **无热 / 时变功耗 / DVFS / power-gating**;能量是聚合量,非功率曲线。
- **无多 die / chiplet / scale-out**。
- **无 floorplan / 布线面积与线延迟**(NoC 是模块,非带线成本的物理 mesh)。
- **量化精度**:precision 影响选算子和能量,但**无数值精度↔PPA 权衡**。

### 🟡 C. 保真度/正确性(已知,已文档化)
- 控制面 FSM 面积(~10%)仍 `[calibration knob]`,需 RTL 综合(Phase 5)。
- **只 45nm 单节点**,跨节点缩放待标定;±30% 带未对硅校准。
- 功能模型是 **golden-reference 结构级,非 bit-accurate RTL**,不做数值验证。

### 🟢 D. 引擎/前端
- 非 event-driven(只 quiescence 早退);SystemC 内核未接(Phase 5)。
- 无二进制 checkpoint/restore(生成器帧阻断,只确定性重放)。
- **wired-pipeline 拓扑盲**:流式通路每 token 穿过每级(mapper 归属正确,
  sim 全流过)。
- **无 ONNX/框架导入**:workload 手写 op YAML,无自动算子图抽取;无 batching /
  全图调度。

## 3. 一句话结论

平台在"逐拍时序 + 计算侧 PPA + 设计空间探索"上真实可查证,适合**计算受限**层
的相对架构权衡。要成为**可信的全面 NPU 设计验证**,首要补 **🔴A:数据搬运能量
+ 访存带宽/dataflow 建模**——真实 NPU 的 PPA 常由数据搬运决定,而这块目前为空。

**优先级建议**:A(数据搬运/带宽)> B.Mapper(DAG/tiling)> C.Phase5 标定 >
D.前端(ONNX 导入)。
