# SPEC-005 模块库规范（Phase 2 Module Library）

文档状态：**v0.1 Draft（implementation spec）**
最后更新：2026-05-28
Owners：架构组
派生自：SPEC-001（IModule 契约）、SPEC-002（反压协议）、SPEC-004
（Functional Simulation）、ADR-002（模块身份判定）

## 0. 范围与方法

本规范定义 Phase 2 模块库中四个真实 NPU 宏模块的**行为契约**：

| 模块 | 角色 | 数据通路位置 |
|---|---|---|
| **DSB** | Data Staging Buffer：片上缓存 / 分块暂存 / 广播 | DAGC → **DSB** → MAC |
| **MAC** | Multiply-Accumulate 阵列：矩阵乘 / 卷积的核心算力 | DSB → **MAC** → VAU |
| **VAU** | Vector Arithmetic Unit：逐元素向量运算（bias/residual/scale）| MAC → **VAU** → AVP |
| **AVP** | Activation & Vector Post-processor：非线性激活 / 归一化 / 池化 | VAU → **AVP** → out |

配合 DAGC（SPEC-001 §5，已实现）可组成一条完整数据通路：
`DAGC（解包）→ DSB（暂存）→ MAC（矩阵乘）→ VAU（向量后处理）→ AVP（激活）`。

**方法**：SPEC-001/002/004 已经定义了*框架契约*，本规范只补充各模块的
*行为语义*（能力、端口、config、latency/energy 模型、运行时 token 流、
functional 数值行为）。平台运行结构化数据流（ADR-001.1 + CLAUDE.md），
故 timing 用解析模型近似、functional 用代表性算子的 golden 模型，二者均不
追求 bit-accurate RTL 对齐（留待 v1.1 + 校准）。

每条行为规则以 `§x.y` 编号，实现的测试 docstring/注释须 `grep` 得到对应
编号（CLAUDE.md 约定）。

## 1. 通用约定（适用于全部四个模块）

- **§1.1 身份**：四个模块均为独立 `IModule` 子类（非 capability flag），
  依据 ADR-002 ——各自拥有不同的 port_specs、不同的数据通路职责、不同的
  functional 语义，满足"新子类"判定。
- **§1.2 命名**：`module_type()` 分别返回 `"DSB"`、`"MAC"`、`"VAU"`、
  `"AVP"`，均匹配 SPEC-001 §3.1.1 正则 `^[A-Z][A-Za-z0-9]{0,23}$`。
- **§1.3 版本**：初始 `module_version()` 均为 `"1.0.0"`。
- **§1.4 运行时约定**：遵循 Phase 2 Python 约定（ADR-001.1）——`behavior()`
  生成器轮询 `TlmInputPort.try_receive()`，用 `yield from
  TlmOutputPort.send()` 推送，使输出反压自动归因到下游 sink（SPEC-002 §3.5）。
  未连接的输入端口 `try_receive()` 返回 `None`，模块须容忍（如 MAC 的
  `in_weight`、VAU 的 `in_b` 在单输入链路中可悬空）。
- **§1.5 面积/功耗**：沿用 SPEC-001 §3.1 默认聚合（按 active capability 求和）。
- **§1.6 estimate_latency/estimate_energy 纯函数**：同一 operation 多次调用
  结果相等（SPEC-001 §3.2）；不支持的 precision/op 返回 `min_cycles == 0`。
- **§1.7 functional 纯函数**：`INumericalModel.execute()` 不得修改 inputs，
  同输入多次调用结果一致（SPEC-004 §3.1）；`supported_capabilities()` ⊆
  配对 IModule 的 `declared_capabilities()` 名（SPEC-004 §7）。golden 模型
  fidelity 为 `FIDELITY_GOLDEN`。

## 2. DSB — Data Staging Buffer

- **§2.1 角色**：SRAM-backed 暂存缓冲，位于解包与算力之间。对 tile 做
  双缓冲（double-buffer）以隐藏下游延迟，并可将一个输入 tile 广播
  （broadcast）到多个 MAC 行。结构化语义为"按容量暂存并转发"。
- **§2.2 能力**：
  - `tile_buffer`（常开）：基本分块缓存 + 转发。
  - `double_buffer`（config 门控）：读写双 bank 重叠。
  - `broadcast`（config 门控）：将一个输入 token 复制为 `broadcast_factor` 份。
- **§2.3 端口**：`in_data`(IN/DATA/256b/fifo 8)、`in_cmd`(IN/COMMAND/64b/fifo 4)、
  `out_data`(OUT/DATA/256b/fifo 16)。
- **§2.4 config**：`buffer_kb`(int 1..512, default 64)、`n_banks`(int 1..8,
  default 2)、`read_throughput`(int 1..16 elem/cyc, default 4)、
  `enable_double_buffer`(bool, default true)、`broadcast_factor`(int 1..8,
  default 1)。required: `buffer_kb`。
- **§2.5 latency**：`cycles = ceil(n_elements / read_throughput)`；双缓冲启用
  时 typical 不加额外 fill（重叠隐藏），未启用时 typical = min + n_banks 行
  fill。confidence 0.7。
- **§2.6 energy**：每元素 SRAM 读写动态能量 = active cap dynamic 之和 × n。
- **§2.7 运行时行为**：轮询 `in_data`；收到 token 后暂存（`ceil(size_bytes/
  read_throughput)` cycle），随后转发 `broadcast_factor` 份到 `out_data`
  （未启用 broadcast 即 1 份）；`in_cmd` opportunistic 排空。
- **§2.8 functional**：暂存不改变数值——golden 模型为 identity 拷贝（dtype/
  shape 保持），`broadcast_factor>1` 时沿新轴复制。`supported_capabilities`
  = `["tile_buffer"]`。

## 3. MAC — Multiply-Accumulate Array

- **§3.1 角色**：脉动 MAC 阵列，执行矩阵乘 / 卷积 GEMM。权重 stationary
  预载，激活流入，部分和（psum）以 FP32 累加流出。
- **§3.2 能力**：
  - `int8_matmul`（常开）、`accumulate_fp32`（常开）。
  - `bfp16_matmul`、`fp16_matmul`（config 门控）。
- **§3.3 端口**：`in_act`(IN/DATA/256b/fifo 8)、`in_weight`(IN/DATA/256b/
  fifo 8)、`in_cmd`(IN/COMMAND/64b/fifo 4)、`out_psum`(OUT/DATA/512b/fifo 16)。
- **§3.4 config**：`array_rows`(int 4..256, default 32)、`array_cols`
  (int 4..256, default 32)、`support_bfp16`(bool, default true)、
  `support_fp16`(bool, default false)。required: `array_rows`,`array_cols`。
- **§3.5 latency**：以 GEMM 规模 `macs = m*k*n`（取 `shape_info` 的 `m`,`k`,`n`，
  缺省用 `n_elements` 作为 macs）估算
  `cycles = ceil(macs / (array_rows*array_cols)) + (array_rows + array_cols)`
  （后者为脉动填充/排空）。不支持的 precision → 0。confidence 0.6。
- **§3.6 energy**：每 MAC 动态能量 × macs。
- **§3.7 运行时行为**：权重 stationary——`in_weight` opportunistic 排空并标记
  已载；轮询 `in_act`，每个激活 token "计算" `ceil(array_cols/ array_rows)`
  + 1 cycle 后产出一个 psum token（size×2，FP32 累加更宽）写 `out_psum`。
  单输入链路（仅接 `in_act`）下权重视为预载常量，链路仍可跑通。
- **§3.8 functional**：golden 模型——若 inputs 同时含 `in_act` 与 `in_weight`
  且二者为 2D 且可乘，输出 `out_psum = (act.astype(fp32) @ weight.astype
  (fp32))`，dtype=FP32；否则退化为对 `in_act` 的 FP32 加宽拷贝（表示尚未载入
  权重的直通）。`supported_capabilities` = `["int8_matmul","accumulate_fp32"]`。

## 4. VAU — Vector Arithmetic Unit

- **§4.1 角色**：逐元素向量 ALU，做 bias add、residual add、scale、relu 等
  逐点运算，位于 MAC 之后。
- **§4.2 能力**：`vector_add`（常开）、`vector_mul`（常开）、
  `vector_max`（config）、`relu`（config）。
- **§4.3 端口**：`in_a`(IN/DATA/512b/fifo 8)、`in_b`(IN/DATA/512b/fifo 8)、
  `in_cmd`(IN/COMMAND/64b/fifo 4)、`out`(OUT/DATA/512b/fifo 16)。
- **§4.4 config**：`lanes`(int 1..64, default 16)、`support_max`(bool, default
  true)、`support_relu`(bool, default true)。required: `lanes`。
- **§4.5 latency**：`cycles = ceil(n_elements / lanes)`。confidence 0.8。
- **§4.6 energy**：每元素 ALU 动态能量之和 × n。
- **§4.7 运行时行为**：轮询 `in_a`，逐 token 应用配置算子，`ceil(size_bytes/
  lanes)` cycle 后写 `out`；`in_b`（第二操作数）与 `in_cmd` opportunistic
  排空。单输入链路下退化为一元运算（identity / relu）。
- **§4.8 functional**：golden 模型按 `operation.op_type` 选择运算：
  `"add"`/`"mul"`/`"max"` 为二元（需 `in_a`+`in_b`，缺 `in_b` 退化为
  identity），`"relu"` 为一元 `maximum(x,0)`，默认 identity。保持 dtype/shape。
  `supported_capabilities` = `["vector_add","vector_mul"]`。

## 5. AVP — Activation & Vector Post-processor

- **§5.1 角色**：非线性激活 / 归一化 / 池化后处理（gelu / softmax / layernorm
  / pooling），数据通路末端。
- **§5.2 能力**：`gelu`（常开）、`softmax`（config）、`layernorm`（config）、
  `pooling`（config）。
- **§5.3 端口**：`in_data`(IN/DATA/512b/fifo 8)、`in_cmd`(IN/COMMAND/64b/
  fifo 4)、`out_data`(OUT/DATA/512b/fifo 16)。
- **§5.4 config**：`vector_width`(int 1..64, default 16)、`support_softmax`
  (bool, default true)、`support_layernorm`(bool, default true)、
  `support_pooling`(bool, default false)、`lut_entries`(int 16..1024, default
  256)。required: `vector_width`。
- **§5.5 latency**：`cycles = ceil(n_elements / vector_width) * cost`，其中
  超越函数（softmax/gelu/layernorm）`cost = 2`，pooling `cost = 1`。
  confidence 0.6。
- **§5.6 energy**：每元素含 LUT 查表动态能量之和 × n。
- **§5.7 运行时行为**：轮询 `in_data`，逐 token 应用激活，`ceil(size_bytes/
  vector_width) * cost` cycle 后写 `out_data`；`in_cmd` opportunistic 排空。
- **§5.8 functional**：golden 模型按 `operation.op_type` 选择：`"gelu"`（默认）
  用 tanh 近似 `0.5*x*(1+tanh(√(2/π)(x+0.044715x³)))`；`"softmax"` 沿末轴；
  `"layernorm"` 沿末轴零均值单位方差（eps=1e-5）；`"relu"` 兜底。保持 shape，
  dtype 提升为 FP32。`supported_capabilities` = `["gelu"]`。

## 6. 测试要求（每模块）

每个模块须有（镜像 DAGC：`tests/unit/test_dagc_module.py` +
`tests/integration/test_dagc_end_to_end.py`）：

- **§6.1 单元 conformance**（SPEC-001 §6）：module_type/version/schema 合法、
  默认 config 通过校验、非法 config 被拒、capability 依赖一致、端口名唯一、
  注册可见、create 可用、configure 激活能力正确且只能一次、端口在 configure
  后暴露、能力查询纯函数、面积随能力增减、snapshot 初始 idle。
- **§6.2 functional**（SPEC-004 §7）：注册并与 IModule 配对、
  supported_capabilities ⊆ declared、execute 纯函数且不改 inputs、
  代表性数值正确（如 MAC 矩阵乘、AVP gelu/softmax）。
- **§6.3 端到端**（SPEC-002 §6）：Producer→模块→Consumer 链路 token 全数流通、
  无死锁（INV-3）；slow consumer 链路下模块输出 stall 且归因到 consumer
  （SPEC-002 §3.5）。

## 7. v1.1 候选 / 实现期发现

本规范为 Phase 2 实现而设的 v0.1 草案。timing 系数（面积/能量/cycle）为
合理工程估计，未经硅前校准——校准记录属 Phase 5（见 README 路线图）。任何
与 SPEC-001/002/004 框架契约的冲突须按 CLAUDE.md 流程升级为 v1.1 候选，记入
`docs/specs/README.md`，不得在实现中静默改框架 spec。
