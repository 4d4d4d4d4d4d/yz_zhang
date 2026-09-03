# SPEC-007 控制与数据传输模块族（Control & Transfer Module Family）

文档状态：**v0.1 Draft（implementation spec — Review pending）**
最后更新：2026-06-04
Owners：架构组
派生自：SPEC-001（IModule 契约）、SPEC-002（反压协议）、SPEC-005
（Phase 2 计算模块库)、ADR-002（模块身份判定）、SPEC-001-v1.1（area 维度,
见 §1）

## 0. 范围与方法

SPEC-005 覆盖了**数据通路上的算力模块**（DAGC/DSB/MAC/VAU/AVP）。
本规范补齐**控制面与数据搬运面**的模块族,目的是让平台能够回答以下
硬件评估问题（用户 2026-06-04 需求）:

1. "OGU 加速算子生成,预期 MCU 负载优化 2×;单/双线程下能节省几个 MCU?"
2. "MTU 融合 TAU/DMA 的两用模块,对端到端 drain_time / 反压链有何影响?"
3. "MAC/DSB/AGU 的算法激励"——AGU 作为独立模块时的 stall 归因。

涉及的 6 个模块及其相互关系:

| 模块 | 角色 | 数据 / 控制通路位置 |
|---|---|---|
| **MCU** | Micro Control Unit:host 调度器,跑 op-gen / BD-gen / op-config | host → **MCU** → 全体模块 |
| **OGU** | Op Generation Unit:标量协加速器,卸载 buffsize 计算/地址/BD 生成/op 配置 | MCU ↔ **OGU** ↔ 全体模块 |
| **TAU** | Tensor Address Unit:为 DMA 生成多维 tensor 地址流 | MCU → **TAU** → DMA |
| **DMA** | Direct Memory Access:外存 ↔ 片上 bulk 搬运 | DRAM ↔ **DMA** ↔ DSB |
| **MTU** | Memory Transfer Unit:**融合**形态,同一模块兼任 TAU + DMA | MCU → **MTU** ↔ DRAM ↔ DSB |
| **AGU** | Address Generation Unit:为 MAC / DSB 生成 inner-loop 地址 | MCU → **AGU** → {MAC, DSB} |

**身份判定**（ADR-002):MCU、OGU、TAU、DMA、MTU、AGU 全部为**独立
IModule 子类**——各自有不同 port_specs、不同 functional 语义、独立的
latency/energy 模型;MTU 不是 TAU+DMA 的 capability flag,因为它合并后
端口数减少、内部仲裁不同(见 §6)。

## 1. 通用约定

- **§1.1 命名** 严格匹配 SPEC-001 §3.1.1:`"MCU"` / `"OGU"` / `"TAU"` /
  `"DMA"` / `"MTU"` / `"AGU"`。
- **§1.2 版本** 初始 `module_version()` 均为 `"1.0.0"`。
- **§1.3 运行时** 与 SPEC-005 §1.4 一致:Python `behavior()` 生成器,
  `TlmOutputPort.send` / `TlmInputPort.try_receive`,等待时
  `yield WAIT(...)`。
- **§1.4 area 维度** 本规范全部模块的 `estimate_area()` 必须返回
  `AreaModel`(SPEC-001 v1.1 §3.2.5),否则无法回答用户的 UNPACK 面积
  / OGU 面积代价类问题。
- **§1.5 控制通路 token 语义** MCU/OGU/TAU/AGU 发出的 token payload
  是**控制指令**(`OpConfigToken`、`AddressStreamToken`、`BDToken`),
  不是数据;但仍遵循 SPEC-002 反压契约,接收方满则上游 stall。
- **§1.6 calibration knob 审计** 同 SPEC-005 §1.6,所有 latency/energy/
  area 系数标 `[calibration knob]`,后续 Phase 5 校准时统一刷数。

## 2. MCU(Micro Control Unit)

### 2.1 capability
- **§2.1.1** `declared_capabilities()` ⊇ `{"op_dispatch", "bd_gen_fallback",
  "op_config_fallback"}`。
- **§2.1.2** 当且仅当 `config["has_ogu_peer"] is False` 时,
  `active_capabilities()` 包含 `bd_gen_fallback` 和 `op_config_fallback`;
  否则这两条卸载给 OGU(§3),MCU 只发 `op_dispatch`。

### 2.2 端口
- **§2.2.1** 输入端口 `cmd_in`(host → MCU,可选;架构无 host 时不连)。
- **§2.2.2** 输出端口 `op_out_*`:每个数据通路模块各一个 fan-out,token
  类型 `OpConfigToken{op_type, shape, precision, target_module_id}`。
- **§2.2.3** 双向端口 `ogu_req` / `ogu_resp`(若 `has_ogu_peer`)。

### 2.3 行为 / latency
- **§2.3.1** 处理一个算子的*完整*配置流程包含三段成本:
  ```
  T_mcu(op) = T_buffsize(op) + T_bd(op) + T_opcfg(op)
  ```
  各段典型值(典型 shape,calibration knob):
  | 段 | typical_cycles | 说明 |
  |---|---|---|
  | buffsize | 80 | 计算每模块所需 buffer 大小 / 起始地址 |
  | bd_gen | 120 | 生成 burst descriptor 列表 |
  | op_config | 60 | 推送配置到各模块的 cmd 端口 |
- **§2.3.2 OGU 卸载后**:`T_buffsize` 与 `T_bd` 由 OGU 承担,MCU 上
  只剩 `T_opcfg = 60`(§3.3.2 用相同口径)。
- **§2.3.3 多线程** `config["threads"] ∈ {1, 2}`,MCU 内部多线程不并行,
  按 round-robin 分时(等效串行总周期 = Σ_thread T_mcu)。这是用户"
  节省 1 个 MCU @单线程 / 2 个 MCU @双线程"目标的可测口径(§2.5)。

### 2.4 area / energy
- **§2.4.1** `estimate_area()` 返回基线 `AreaModel(um2=120_000)`(单线程)
  或 `240_000`(双线程,因为两套控制流寄存器组),`[calibration knob]`。
- **§2.4.2** `estimate_energy(op)` = `T_mcu(op) × 0.4 pJ/cycle`
  `[calibration knob]`。

### 2.5 评估口径 — "节省几个 MCU"
- **§2.5.1** baseline = "N 个 MCU,无 OGU";variant = "N' 个 MCU + 1 个
  OGU"。
- **§2.5.2** 平台判定"节省"的形式化定义:variant 的总
  `drain_time_ps` ≤ baseline 的 `drain_time_ps × (1 + ε)`,且
  variant 的 MCU 数量 < baseline,其中 `ε ≤ 0.05`(5% 退化容忍)。
- **§2.5.3** 单线程目标:1 个 MCU + 1 OGU 应等价于 2 个 MCU;
  双线程目标:1 个 MCU + 1 OGU 应等价于 3 个 MCU。

## 3. OGU(Op Generation Unit)

### 3.1 capability
- **§3.1.1** `declared_capabilities()` ⊇ `{"buffsize_calc",
  "address_calc", "bd_gen", "op_config_assist"}`。
- **§3.1.2** OGU 是协处理器,**必须与某个 MCU 配对**;`configure()` 中
  `config["mcu_peer_id"]` 缺省时 raise `ConfigurationError`(SPEC-001
  §3.5.2)。

### 3.2 端口
- **§3.2.1** 输入端口 `req_in`(from MCU)。
- **§3.2.2** 输出端口 `resp_out`(to MCU)及 `cfg_broadcast_out`
  (直推数据通路模块,旁路 MCU,节省一次往返)。

### 3.3 行为 / latency
- **§3.3.1** OGU 是**标量定制硬件**,每段 latency 是 MCU 的 1/4:
  | 段 | typical_cycles | 说明 |
  |---|---|---|
  | buffsize | 20 | 标量 ALU + 专用地址生成 |
  | bd_gen | 30 | 硬连线 BD 模板 |
- **§3.3.2** "2× MCU 负载优化"的形式化定义:
  ```
  T_mcu_baseline(op) = 80 + 120 + 60 = 260 cycles
  T_mcu_with_ogu(op) = 60 cycles            (仅 op_config 留 MCU)
  T_ogu(op)          = 20 + 30 = 50 cycles
  ```
  关键不变量(测试断言):
  `T_mcu_baseline / T_mcu_with_ogu ≥ 2.0`(实测 4.33,远超 2×)
  `[calibration knob]` 标注下,系数可校准但 ≥2× 的关系应保留。

### 3.4 area / energy
- **§3.4.1** `estimate_area() = AreaModel(um2=40_000)` `[calibration knob]`
  ——目标:`OGU_area / MCU_area ≤ 0.4`(SPEC-007 设计目标:协加速器
  面积代价远小于多增 1 个 MCU)。
- **§3.4.2** `estimate_energy(op) = T_ogu(op) × 0.25 pJ/cycle`。

## 4. TAU(Tensor Address Unit)

### 4.1 capability
- **§4.1.1** `declared_capabilities() ⊇ {"tensor_address_gen"}`。

### 4.2 端口
- **§4.2.1** 输入 `descriptor_in`(from MCU/OGU 的 BD)。
- **§4.2.2** 输出 `addr_stream_out`(to DMA)。

### 4.3 行为
- **§4.3.1** 每生成一个 burst 地址 typical_cycles = 4
  `[calibration knob]`;一次 op 的地址数 = `op.shape.bursts`。
- **§4.3.2** TAU 内部 FIFO 深度 = `config["addr_fifo_depth"]`(默认 16);
  下游 DMA 满则反压(SPEC-002 §3.4)。

### 4.4 area
- **§4.4.1** `AreaModel(um2=30_000)` `[calibration knob]`。

## 5. DMA(Direct Memory Access)

### 5.1 capability
- **§5.1.1** `declared_capabilities() ⊇ {"bulk_memory_transfer"}`。

### 5.2 端口
- **§5.2.1** 输入 `addr_stream_in`(from TAU 或 MTU 内部)。
- **§5.2.2** 双向 `mem_io`(外存接口,Phase 2 用 latency 模型近似)。
- **§5.2.3** 输出 `data_out`(to DSB)。

### 5.3 行为
- **§5.3.1** 每 burst typical_cycles = `dram_burst_latency + payload_bytes /
  bus_width`;`dram_burst_latency` 默认 40,`bus_width` 默认 32 B
  `[calibration knob]`。
- **§5.3.2** 反压契约:`data_out` 满则 DMA stall,且自然向上游 TAU 反压。

### 5.4 area
- **§5.4.1** `AreaModel(um2=80_000)` `[calibration knob]`。

## 6. MTU(Memory Transfer Unit — 融合 TAU+DMA)

### 6.1 capability
- **§6.1.1** `declared_capabilities() ⊇ {"tensor_address_gen",
  "bulk_memory_transfer"}` ——**同时**具备 TAU 和 DMA 的能力(这是
  ADR-002 "新子类 vs capability flag" 边界案例:见 §6.5)。

### 6.2 端口
- **§6.2.1** 输入 `descriptor_in`(取代 TAU+DMA 的两个对外端口)。
- **§6.2.2** 双向 `mem_io`。
- **§6.2.3** 输出 `data_out`。

  ——*相对独立 TAU+DMA 减少了一对内部互连端口*,这是 MTU 的拓扑收益。

### 6.3 行为
- **§6.3.1** typical_cycles = `max(T_tau(op), T_dma(op))`
  ——融合后地址生成和数据搬运可以**完全 overlap**(独立 TAU+DMA 因
  跨模块 FIFO 至少多 1 拍 ping-pong)。形式化:
  ```
  T_mtu(op) ≤ T_tau(op) + T_dma(op) - overlap_savings
  overlap_savings ≥ min(T_tau, T_dma) × 0.8     [calibration knob]
  ```
- **§6.3.2** 反压契约同 §5.3.2。

### 6.4 area
- **§6.4.1** `AreaModel(um2=95_000)` `[calibration knob]` ——略小于
  TAU(30k) + DMA(80k) = 110k,因共享地址寄存器和总线接口。

### 6.5 身份判定理由(ADR-002 §3 应用)
ADR-002 §3 6 条规则中,MTU 触发以下 3 条 → 独立子类:
1. **端口拓扑不同**:TAU+DMA 是两个模块,MTU 是一个;
2. **内部仲裁逻辑不同**:MTU 地址流和数据流共享同一时序,需要独立的
   `behavior()`;
3. **functional 模型不同**:MTU 单次 `forward(op)` 内联完成 addr+data,
   TAU/DMA 必须串接。

## 7. AGU(Address Generation Unit)

### 7.1 capability
- **§7.1.1** `declared_capabilities() ⊇ {"inner_loop_address_gen"}`。
- **§7.1.2** 必须与 MAC 或 DSB 配对(`config["client_module_id"]`)。

### 7.2 端口
- **§7.2.1** 输入 `op_in`(算子描述符)、`tick_in`(client 的步进信号)。
- **§7.2.2** 输出 `inner_addr_out`(to MAC/DSB inner-loop)。

### 7.3 行为
- **§7.3.1** AGU 必须以 **1 周期/地址** 的吞吐供给 client,否则 client
  stall。`config["agu_pipeline_depth"]` 默认 3。
- **§7.3.2 用户"MAC/DSB/AGU 的算法激励"** 通过 SPEC-005 §1.6 的 MAC
  数组规模 / DSB 容量 + AGU 流水深度联合扫描出最坏 stall 点。

### 7.4 area
- **§7.4.1** `AreaModel(um2=15_000)` `[calibration knob]`。

## 8. v1.1 候选

- **§8.1** OGU 命中率模型:并非所有算子都能 100% 卸载给 OGU(如 BD
  含复杂条件分支时回退 MCU),v1.0 暂按 100% 卸载;v1.1 加 `hit_rate`
  config。
- **§8.2** MTU 多通道(multi-channel)模型 → v1.1 SPEC-007.2。
- **§8.3** AGU 共享(一个 AGU 同时服务多个 MAC/DSB)需要资源调度模型 →
  v1.1。

## 9. 配套测试要求(实现阶段)

- **§9.1** 每个模块至少 1 个 conformance test(对应 SPEC-001 §6 与
  SPEC-007 各小节)。
- **§9.2** Integration:
  - **§9.2.1** MCU baseline vs (MCU+OGU) variant,断言 §2.5.2 / §2.5.3
    节省关系成立。
  - **§9.2.2** (TAU+DMA) baseline vs MTU variant,断言 §6.3.1
    overlap_savings ≥ 80% × min(T_tau, T_dma)。
  - **§9.2.3** AGU 流水深度扫描 → stall 归因(SPEC-002 §3.3 tracer)。
- **§9.3** 全部 fixture 落 `tests/fixtures/architectures/`。
