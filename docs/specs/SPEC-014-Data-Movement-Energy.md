# SPEC-014 数据搬运能量模型(Data-Movement Energy)

文档状态:**v0.1 Draft(implementation spec)** · 最后更新:2026-09-27
Owners:架构组
派生自:SPEC-006 §8(estimate/energy)、SPEC-013(physical per-access 能量)、
`docs/Platform-Capability-Assessment.md` 🔴A(最高优先缺口)

## 0. 动机

平台此前的 workload 能量只算**计算**能量(MAC = macs × per-MAC)。但 Horowitz
ISSCC'14:**DRAM 32b 访问 = 640 pJ,int MAC ≈ 1 pJ,差 640×**。真实 NPU 的能量
常由**数据搬运**主导。缺它导致:(1) 总能量低估数倍;(2) "能量随设计不变"是假象
——数据搬运恰是随片上缓冲大小变化的项(权重放得下→SRAM,放不下→DRAM 溢出)。

本规范定义**一级(first-order)数据搬运能量模型**:每算子按其 operand 字节数,
依"是否放得进片上缓冲"判 SRAM vs DRAM,计 per-access 能量,计入 workload 能量。

**明确不做(v0.1 边界,不臆想)**:不建模 dataflow/tiling/data-reuse 优化——
即假设每算子的 operand **各流一遍**(no-reuse 上界)。真实 dataflow 会靠复用降低
流量;本模型给"无复用"上界,tiling/reuse 归 v0.2(见 §5)。带宽 roofline(访存
→计算 stall)也归 v0.2;v0.1 只做能量。

## 1. 每算子 operand 流量(bytes)

| 算子 | 激活读入 | 权重读入 | 输出写出 |
|---|---|---|---|
| matmul(M,K,N,p) | `M·K·p` | `K·N·p` | `M·N·out_bytes` |
| elementwise(n,p)(relu/gelu/softmax/layernorm/…) | `n·p` | 0 | `n·p` |

- `p` = 输入精度字节(int8/int4/bfp8=1、bf16/fp16/bfp16=2、int32/fp32=4),取自
  `op.precision.kind.value`。
- `out_bytes` = matmul 默认 **4**(FP32 psum,与 SPEC-013 MAC 累加口径一致);
  elementwise 输出同输入精度。`n` = `n_elements`。

## 2. 存放层级判定(SRAM vs DRAM)

片上缓冲总容量 `C_onchip`(bytes)= 架构中各存储模块容量之和(遍历
`arch.modules`,`getattr` 探测 `_capacity_bytes` / `_buffer_kb`×1024 /
`_capacity_kb`×1024 / `_tile_kb`×1024;无则 0),不依赖固定模块名。

- **权重**:`weight_bytes ≤ C_onchip` → 常驻片上,**SRAM 读**;否则**溢出 DRAM**,
  **DRAM 读**(缓冲不足的代价)。
- **激活 / 输出**:视为已 staged 片上 → **SRAM 读/写**(激活的 DRAM 溢出留 v0.2)。

per-byte 能量(SPEC-013 / Horowitz @45nm):SRAM = 1.25 pJ/B;
DRAM = `E_DRAM_RD_32B_PJ/4` = 160 pJ/B(~128× SRAM)。

## 3. 能量合成

```
movement_pj(op) = act·e_sram + weight·e_level + out·e_sram
data_movement_pj = Σ_op movement_pj(op)
workload_total_pj = compute_dynamic_pj + data_movement_pj + static_pj
```

报告须分列 compute / movement / static 三项,使"数据搬运占比"可见。

## 4. 契约 / 实现

- `evaluation/data_movement.py`:`op_traffic_bytes(op)`、`onchip_capacity_bytes(arch)`、
  `data_movement_energy_pj(ops, arch) -> DataMovementReport(total_pj,
  weight_dram_pj, onchip_capacity_bytes, any_weight_spilled)`。
- `evaluation/energy.py`:`EnergyReport` 增 `movement_pj/weight_dram_pj/
  weights_spilled`;`analyze_energy` 计入 `total_pj`;render 增"数据搬运"行。
- per-access 能量复用 `physical.sram_read_energy_pj` / 新增 `dram_access_energy_pj`。

## 5. v0.2 候选(明示留白)

- **dataflow / tiling / data-reuse**(weight/output/row-stationary,权重跨 M-tile 复用)。
- **带宽 roofline**:op_time = max(compute_cycles, bytes/bandwidth)。
- 激活的 DRAM 溢出(大 batch/seq)。

## 6. 测试要求

- **§T.1** matmul/elementwise 的 `op_traffic_bytes` 等于 §1 公式(精度按字节缩放)。
- **§T.2** 权重放得下 → SRAM;放不下 → DRAM(≥128× SRAM/byte)。
- **§T.3** `analyze_energy` total = compute + movement + static;movement>0。
- **§T.4** 小缓冲设计(权重溢出 DRAM)总能量 **>** 大缓冲设计——数据搬运使能量
  **随设计分化**(修正 `docs/NPU-Design-Study.md` §3.2 的"能量设计不变"假象)。
