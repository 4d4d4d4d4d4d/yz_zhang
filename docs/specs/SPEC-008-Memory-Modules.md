# SPEC-008 内存与精度模块族(Memory & Precision Module Family)

文档状态：**v0.1 Draft(implementation spec — all 4 §§ Review pending)**
最后更新：2026-06-23
Owners：架构组
派生自：SPEC-001(IModule 契约)、SPEC-002(反压协议)、SPEC-005(Phase 2
计算模块)、SPEC-007(控制/传输模块)、ADR-002(模块身份判定)

## 0. 范围与方法

SPEC-005 覆盖数据通路的**计算**模块(DAGC/DSB/MAC/VAU/AVP),SPEC-007
覆盖**控制/传输**(MCU/OGU/TAU/DMA/MTU/AGU)。本规范补齐**专用片上存储 +
精度转换 + 特殊函数**4 个模块,匹配主流 NPU(Ascend / NVDLA / Ethos /
TPU)的标准模块集。

本版**一次性 draft 全部 4 个 §**,统一 review。Accepted 后按顺序实现:
§1 WB → §2 OB → §3 Quant/Dequant → §4 SFU。

| § | 模块 | 主要作用 | 替补/新增 |
|---|---|---|---|
| §1 | **WB** | 权重独立片上缓存 | 替补:今 DSB 兼任权重+激活 |
| §2 | **OB** | MAC psum 累加缓存 | 替补:今 MAC 直接吐 VAU |
| §3 | **Quant / Dequant** | act 量化、weight 反量化 | 替补:今 DAGC 兼任 |
| §4 | **SFU** | exp/log/rsqrt/div 等超越函数 | 替补:今 AVP 用 LUT 近似 |

通用约定(全部 4 个 § 都遵守):
- 命名严格匹配 SPEC-001 §3.1.1 正则
- `module_version()` 初始 `"1.0.0"`
- 运行时:Python `behavior()` 生成器(ADR-001.1)
- area / energy / latency 系数全标 `[calibration knob]`
- 实现遵守 SPEC-001 v1.1 §3.2.5 area 维度
- 使用 SPEC-001 v1.1 命名 stage(snapshot_state.current_op 可见每 sub-stage)
- 所有评估测试必须通过 `assert_evaluation_is_yaml_driven`

---

## §1 WB(Weight Buffer)

### 1.1 动机 / 与 DSB 的区别

DSB 当前同时承担"激活暂存"和"权重暂存"两种角色,这是 v1.0 的简化。
真实 NPU 普遍把它们**分开**,理由:

| 维度 | activation | weight |
|---|---|---|
| 生命周期 | 一次 op,用完就丢 | 跨多个 op 复用(weight stationary) |
| 访问模式 | 流式按 token | 随机 / tile 重用 |
| 写入频率 | 高(每 op 一次) | 低(模型加载时一次) |
| 容量需求 | 几十-几百 KB | 几 MB(LLM 可上 GB) |
| 工艺取舍 | SRAM 高带宽 | SRAM/eDRAM 高容量 |

合在一起 → 无法量化 weight-stationary 优化、无法量化模型超容代价。

### 1.2 capability

- **§1.2.1** `module_type()` = `"WB"`。
- **§1.2.2** `declared_capabilities()`:
  - `weight_storage`(必有)
  - `weight_prefetch`(可选,gated by `enable_prefetch`)
  - `weight_compression`(可选,gated by `enable_compression`)
- **§1.2.3** 身份判定(ADR-002 §3):**新 IModule 子类**
  - 端口拓扑不同于 DSB(WB 有 prefetch 端口)
  - functional 语义不同(weight 不变,act 流变)
  - lifetime 不同(权重跨 op 持久)

### 1.3 端口

- **§1.3.1** `weight_in`(INPUT,DATA)
- **§1.3.2** `weight_out`(OUTPUT,DATA)
- **§1.3.3** `prefetch_cmd_in`(INPUT,COMMAND,可选)
- **§1.3.4** `cmd_in`(INPUT,COMMAND)

### 1.4 行为 / latency

- **§1.4.1** 写入:每 token 周期 = `payload_bytes / write_bw_bytes_per_cycle`,`write_bw=32` `[calibration knob]`
- **§1.4.2** 读出:每次请求 = `1 + payload_bytes / read_bw_bytes_per_cycle`,`read_bw=64` `[calibration knob]`
- **§1.4.3** 预取:`enable_prefetch=true` 时 prefetch_cmd_in 触发后台 fill,不占 weight_out 带宽
- **§1.4.4** 容量:`capacity_kb`(默认 256 KB)。装不下 → stall reason `weight_overflow`

### 1.5 area / energy

- **§1.5.1** `AreaModel(um2 = capacity_kb × 1200)` `[calibration knob]`
- **§1.5.2** static = `capacity_kb × 0.5 μW/KB`
- **§1.5.3** dynamic = `0.3 pJ/byte_read + 0.5 pJ/byte_write`

### 1.6 stage 命名

`idle` / `load_weight` / `serve_weight` / `prefetch` / `overflow_drain`

### 1.7 不变量

- 已存权重总量 ≤ `capacity_kb × 1024`
- prefetch 期间 weight_out 仍能 serve

### 1.8 评估口径

| 评估 | baseline | variant |
|---|---|---|
| WB 容量影响 | `capacity_kb=64` | `capacity_kb=256` |
| Prefetch 收益 | `enable_prefetch=false` | `true` |
| 大模型权重溢出 | workload 装得下 | workload 超 capacity |

### 1.9 测试要求

- Conformance(SPEC-001 §6)
- Integration:WB 替代 DSB 当 MAC 权重源,drain_time 不退化
- capacity 减半 → `weight_overflow` stall reason 出现
- prefetch 开启 → drain_time 下降(隐藏 DRAM 延迟)

---

## §2 OB(Output / Accumulator Buffer)

### 2.1 动机 / 与现有 MAC→VAU 直连的区别

当前 MAC.out_psum 直接进 VAU.in_a。真实 NPU 中:
- MAC 输出 psum 是 **FP32**,但 MAC 阵列可能跨多 cycle/tile 累加同一输出 element
- VAU 不能每拍都消费,需要 "完整 output tile 攒齐" 才能开始向量后处理
- OB 是这两者之间的容量缓冲 + 累加器

合并到 MAC 内部 → 评估"累加深度 vs 面积"做不了;评估"OB 容量限制下的 reuse"也做不了。

### 2.2 capability

- **§2.2.1** `module_type()` = `"OB"`。
- **§2.2.2** capabilities:
  - `psum_accumulate`(必有)
  - `int32_acc`(默认 true)
  - `fp32_acc`(可选,gated by `support_fp32_acc`)
- **§2.2.3** 身份判定:**新 IModule 子类**
  - functional 语义独特(累加而非仅暂存)
  - port 方向不同(双向累加 port)
  - lifetime 不同(一个 output tile 横跨多个 MAC pass)

### 2.3 端口

- **§2.3.1** `psum_in`(INPUT,DATA):来自 MAC out_psum
- **§2.3.2** `acc_out`(OUTPUT,DATA):向 VAU 提供完整 output tile
- **§2.3.3** `cmd_in`(INPUT,COMMAND):flush/clear/output-tile 完成信号

### 2.4 行为 / latency

- **§2.4.1** 累加:每 psum token = 1 cycle(in-place add)
- **§2.4.2** flush:`accumulate_depth` 次累加后,把 output tile 发到 acc_out;否则继续累加
- **§2.4.3** 容量:`tile_kb`(默认 16 KB),装不下当前 tile → stall reason `ob_overflow`
- **§2.4.4** 同时 alive tile 数:`max_in_flight_tiles`(默认 2,double buffer)

### 2.5 area / energy

- **§2.5.1** `AreaModel(um2 = tile_kb × max_in_flight_tiles × 1500)` `[calibration knob]`(FP32 累加器寄存器贵)
- **§2.5.2** dynamic = `0.6 pJ per psum accumulate`

### 2.6 stage 命名

`idle` / `accumulate` / `flush_tile` / `wait_acc`

### 2.7 不变量

- 任一 in-flight tile 大小 ≤ `tile_kb × 1024`
- 累加器寄存器宽度匹配 capability(int32 or fp32)

### 2.8 评估口径

| 评估 | baseline | variant |
|---|---|---|
| OB 容量影响 | `tile_kb=8` | `tile_kb=64` |
| Double-buffer 收益 | `max_in_flight_tiles=1` | `=2` |
| FP32 acc 代价 | `int32_acc` only | `+ fp32_acc` enabled |

### 2.9 测试要求

- Conformance
- Integration:MAC→OB→VAU 替代 MAC→VAU 直连,drain_time 不退化
- accumulate_depth 增大 → MAC↔OB 反压减少
- tile_kb 减半 + 大 output → `ob_overflow` stall

### 2.10 §2 ↔ MAC 接口微调

§2 落地需要 MAC 的 `out_psum` 行为支持 "partial psum"(带 `tile_id` /
`partial_idx` metadata),让 OB 知道何时 flush。变更范围:仅 MAC token metadata,不动 port_specs / capability。

---

## §3 Quant / Dequant

### 3.1 动机 / 与现状的区别

当前 DAGC 兼任"BFP unpack"角色(里面包含 dequant 含义)。真实 NPU:
- **Dequant** 通常贴在 weight buffer 输出(W → FP)和 act 输入(int8 → int8 with scale)
- **Quant** 通常贴在 VAU/AVP 输出(FP → int8,送回 DSB 或 DRAM)
- 这两个**独立**于 BFP unpack,因为它们涉及 per-channel scale / zero-point,需要查 scale table

### 3.2 capability

- **§3.2.1** `module_type()` = `"Quant"`(共用模块,通过 `direction` 配置切换 quant vs dequant)
- **§3.2.2** capabilities:
  - `int8_to_fp32`(dequant)
  - `fp32_to_int8`(quant)
  - `per_tensor_scale`
  - `per_channel_scale`(可选,gated by `enable_per_channel`)
  - `symmetric_quant` / `asymmetric_quant`(互斥,看 zero_point 是否非零)
- **§3.2.3** 身份判定:**新 IModule 子类**
  - 需要独立 scale table 存储(area)
  - functional 行为是数值变换,不同于 DAGC 的纯格式重排
  - 同一物理 NPU 可能多 Quant 实例(weight-side / act-side)

### 3.3 端口

- **§3.3.1** `data_in`(INPUT,DATA)
- **§3.3.2** `data_out`(OUTPUT,DATA)
- **§3.3.3** `scale_in`(INPUT,COMMAND):scale + zero_point 表加载
- **§3.3.4** `cmd_in`(INPUT,COMMAND)

### 3.4 行为 / latency

- **§3.4.1** 每 element 周期 = 1(管线化),per-channel 模式 +1 拍 LUT 查表
- **§3.4.2** 配置:`direction` ∈ {`quant`, `dequant`}, `bits_in`, `bits_out`
- **§3.4.3** 不支持的精度组合 → stall reason `precision_mismatch`

### 3.5 area / energy

- **§3.5.1** `AreaModel(um2 = 8000 + (enable_per_channel ? 4000 : 0))` `[calibration knob]`
- **§3.5.2** dynamic = `0.15 pJ/element`(quant)、`0.10 pJ/element`(dequant)

### 3.6 stage 命名

`idle` / `load_scale` / `quantize` / `dequantize` / `emit`

### 3.7 评估口径

| 评估 | baseline | variant |
|---|---|---|
| Quant 链路面积 | DAGC-only baseline | + Quant 模块 |
| Per-tensor vs per-channel 代价 | `enable_per_channel=false` | `=true`(+ area + 1 cycle/elem) |
| 完整 int8 推理链路 | INT8 throughput | Q→MAC→DQ 完整环 |

### 3.8 测试要求

- Conformance
- Integration:Q 插在 DSB→MAC 之间,act 量化下 drain_time 增加可量化
- per_channel on/off → area delta = 4000 μm²
- direction=dequant 时数据宽度膨胀(int8→fp32 = 4×),下游 FIFO 反压可见

---

## §4 SFU(Special Function Unit)

### 4.1 动机 / 与 AVP 的区别

AVP 当前用 LUT 近似各种激活函数(softmax / layernorm 等)。真实 NPU:
- LUT 对 exp / log / rsqrt 的精度损失大(softmax 数值稳定性会出问题)
- 现代 NPU(Ascend 910B / H100 TC)有独立 SFU 跑 transcendentals
- AVP 主要做"用 SFU 结果 + 向量加减乘除"的 LayerNorm/softmax 组合

### 4.2 capability

- **§4.2.1** `module_type()` = `"SFU"`
- **§4.2.2** capabilities:
  - `exp` / `log`(必有)
  - `rsqrt`(必有,LayerNorm 需要)
  - `div`(必有)
  - `sin` / `cos`(可选,gated by `enable_trig`)
- **§4.2.3** 身份判定:**新 IModule 子类**
  - 独立 datapath(Newton-Raphson / CORDIC 迭代单元)
  - port 与 AVP 独立(SFU 是 AVP 的 sub-call,而非串联)
  - functional 精度 ≠ LUT(更准)

### 4.3 端口

- **§4.3.1** `req_in`(INPUT,COMMAND):`{op_type, operand_token_id}`
- **§4.3.2** `operand_in`(INPUT,DATA)
- **§4.3.3** `result_out`(OUTPUT,DATA)

### 4.4 行为 / latency

- **§4.4.1** 每操作 latency 表(`[calibration knob]`):
  | op | cycles |
  |---|---|
  | exp / log | 8 |
  | rsqrt | 12 |
  | div | 14 |
  | sin / cos | 16 |
- **§4.4.2** throughput:1 op/cycle(全管线化)
- **§4.4.3** 不支持的 op_type → stall reason `sfu_unsupported_op`

### 4.5 area / energy

- **§4.5.1** `AreaModel(um2 = 25000 + (enable_trig ? 8000 : 0))` `[calibration knob]`
- **§4.5.2** dynamic = `2.5 pJ/op`(每 op 平均)

### 4.6 stage 命名

`idle` / `recv_req` / `compute_<op>` / `emit_result`

### 4.7 评估口径

| 评估 | baseline | variant |
|---|---|---|
| SFU vs LUT 精度 | AVP LUT-only | + SFU |
| Softmax 链路 | AVP-only(慢且不准) | AVP + SFU(快且准) |
| Trig 代价 | `enable_trig=false` | `=true`(+8000 μm²) |

### 4.8 测试要求

- Conformance
- Integration:softmax workload(需 exp + div)的 drain_time 比 AVP-only 显著降低
- enable_trig on/off → area delta = 8000 μm²
- 不支持的 op_type 触发 `sfu_unsupported_op` stall

### 4.9 §4 ↔ AVP 接口

§4 落地时,AVP 需要可选 `sfu_peer_id` config(类似 SPEC-007 OGU 模式):
有 SFU 时把 transcendentals 卸载,没有时退化到 LUT。AVP 的 port_specs
不变;capabilities 加 `sfu_peer_offload`(active iff `sfu_peer_id` 设置)。

---

## 全规范评审通过标准

请按 SPEC v1.0 R1–R6 同样的方法 review,关注:

1. **4 个模块的边界与现有冲突**:
   - WB vs DSB(§1.2.3 给了 ADR-002 三条) — OK?
   - OB vs MAC 内部 accumulator(§2.10 改 MAC metadata 不改 port) — OK?
   - Quant vs DAGC(§3.2.3 给了 scale table + 数值变换两条) — OK?
   - SFU vs AVP(§4.9 给了 AVP 加 sfu_peer 模式) — OK?
2. **依赖链顺序**:WB → OB → Quant → SFU。各自独立可实现;§2 改 MAC metadata,§4 改 AVP capabilities,**这两处接口微调可接受吗**?
3. **测量口径**:每 § §X.7 / §X.8 的评估能否客观判定"通过/未通过"?
4. **calibration 兜底**:所有系数都 `[calibration knob]`,Phase 5 校准前不可信。可接受程度?
5. **后续 v1.1 候选**(本规范之外,但相关):
   - WB 多 bank
   - OB victim eviction
   - Quant per-token dynamic scale
   - SFU CORDIC 迭代精度配置

---

## 实施路线(全规范 Accepted 后)

| 步骤 | 内容 |
|---|---|
| Step 1 | §1 WB 实现 + use case 测试(3 对 YAML) |
| Step 2 | §2 OB 实现 + MAC metadata 微调 + use case 测试(3 对) |
| Step 3 | §3 Quant 实现 + use case 测试(3 对) |
| Step 4 | §4 SFU 实现 + AVP 微调 + use case 测试(3 对) |
| Step 5 | 全系统集成 fixture(WB+OB+Q+SFU+SPEC-005+SPEC-007 同 yaml)+ 叠加评估 |

每步独立 commit,全程跑 471+ 已有测试 + 新加 ~24 个测试。无代码改动直到本规范 Accepted。
