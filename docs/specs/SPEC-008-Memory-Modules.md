# SPEC-008 内存模块族(Memory Module Family)

文档状态：**v0.1 Draft(implementation spec — Review pending,逐模块累加)**
最后更新：2026-06-23
Owners：架构组
派生自：SPEC-001(IModule 契约)、SPEC-002(反压协议)、SPEC-005(Phase 2
计算模块)、SPEC-007(控制/传输模块)、ADR-002(模块身份判定)

## 0. 范围与方法

SPEC-005 覆盖数据通路的**计算**模块(DAGC/DSB/MAC/VAU/AVP),SPEC-007
覆盖**控制/传输**(MCU/OGU/TAU/DMA/MTU/AGU)。本规范补齐**专用片上存储
模块**,以匹配主流 NPU(Ascend / NVDLA / Ethos / TPU)的"权重缓存 +
累加缓存"两级独立存储分工。

**逐模块累加交付**:每个 §N 是一个独立 review/开发周期。Accepted 后才进入
下一个 §。这一版只交付 **§1 WB**。

涉及(完整愿景,后续累加):

| § | 模块 | 角色 | 当前状态 |
|---|---|---|---|
| §1 | **WB**(Weight Buffer) | 权重独立片上缓存,与 act buffer 分开 | **本版** Review pending |
| §2 | OB / ACC(Output / Accumulator Buffer) | MAC 累加结果暂存 | 待 §1 通过 |
| §3 | Quant / Dequant | 量化 / 反量化 | 待 §2 通过 |
| §4 | SFU(Special Function Unit) | exp/log/rsqrt/div | 待 §3 通过 |

通用约定(后续每个 § 都遵守):
- 命名严格匹配 SPEC-001 §3.1.1 正则
- `module_version()` 初始 `"1.0.0"`
- 运行时:Python `behavior()` 生成器(ADR-001.1)
- area / energy / latency 系数全标 `[calibration knob]`
- 实现遵守 SPEC-001 v1.1 §3.2.5 area 维度

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

把两者合在一个 DSB 里,会出现:
- 评估 weight-stationary 优化时无法区分哪部分容量真的在装权重
- 大模型权重溢出的代价 cannot 直接量化
- "weight prefetch 隐藏 DRAM 延迟" 类优化无法建模

**WB 独立模块化**后,以上评估都能纯通过 YAML 配置驱动出来。

### 1.2 capability

- **§1.2.1** `module_type()` = `"WB"`。
- **§1.2.2** `declared_capabilities()`:
  - `weight_storage`(必有)
  - `weight_prefetch`(可选,gated by `enable_prefetch`)
  - `weight_compression`(可选,gated by `enable_compression`)
- **§1.2.3** 身份判定(ADR-002 §3):**新 IModule 子类**,因为
  - 端口拓扑不同于 DSB(WB 有 prefetch 端口,DSB 没有)
  - functional 语义不同(weight 不变,act 流变)
  - lifetime 不同(权重跨 op 持久)

### 1.3 端口

- **§1.3.1** `weight_in`(INPUT,DATA):权重从 DRAM/DMA 写入(模型加载阶段)
- **§1.3.2** `weight_out`(OUTPUT,DATA):向 MAC 提供权重 tile
- **§1.3.3** `prefetch_cmd_in`(INPUT,COMMAND,可选):MCU/OGU 发起预取
- **§1.3.4** `cmd_in`(INPUT,COMMAND):op-config(load_weight、broadcast)

### 1.4 行为 / latency

- **§1.4.1** 写入(weight load):每 token 周期 = `payload_bytes / write_bw_bytes_per_cycle`,默认 `write_bw=32 B/cycle` `[calibration knob]`
- **§1.4.2** 读出(weight serve):每次 MAC 请求 = `1 + payload_bytes / read_bw_bytes_per_cycle`,默认 `read_bw=64 B/cycle` `[calibration knob]`
- **§1.4.3** 预取(prefetch):若 `enable_prefetch=true`,prefetch_cmd_in 触发后台 fill,期间不占 weight_out 带宽(独立 read port)
- **§1.4.4** 容量约束:`capacity_kb` 配置(默认 256 KB)。装不下的权重 → 溢出回 DRAM(报 stall reason `weight_overflow`)

### 1.5 area / energy

- **§1.5.1** baseline `AreaModel(um2 = capacity_kb × area_per_kb)`,默认 `area_per_kb = 1200 μm²/KB` `[calibration knob]`
- **§1.5.2** static power = `capacity_kb × 0.5 μW/KB`
- **§1.5.3** dynamic energy = `0.3 pJ/byte_read + 0.5 pJ/byte_write`

### 1.6 stage(per SPEC-001 v1.1 §3.x naming)

snapshot_state.current_op 暴露:
- `idle` / `load_weight` / `serve_weight` / `prefetch` / `overflow_drain`

### 1.7 不变量

- **§1.7.1** 任一时刻已存权重总量 ≤ `capacity_kb × 1024`,否则视为模块 bug
- **§1.7.2** prefetch 期间 weight_out 必须仍能 serve(独立 port)

### 1.8 评估口径(use case 设计原则)

WB 引入后必须支撑以下评估,各用一对 YAML 表达:

| 评估 | baseline | variant |
|---|---|---|
| WB 容量影响 | `wb.capacity_kb=64` | `wb.capacity_kb=256` |
| Prefetch 收益 | `enable_prefetch=false` | `true` |
| 大模型权重溢出代价 | workload 装得下 | workload 超过 capacity |

### 1.9 测试要求(实现阶段)

- **§1.9.1** Conformance test(SPEC-001 §6): module_type 注册、port_specs、estimate_area
- **§1.9.2** Integration tests:
  - WB 替代 DSB 当 MAC 权重源,drain_time 应优于(or 至少等于)DSB-only baseline
  - capacity 减半 → 大权重 workload 出现 `weight_overflow` stall reason
  - prefetch 开启 → drain_time 减少(隐藏 DRAM 延迟)
- **§1.9.3** YAML fixture pairs 放在 `tests/fixtures/architectures/`
- **§1.9.4** 所有评估测试必须通过 `assert_evaluation_is_yaml_driven`

### 1.10 v1.1 候选(本版之外)

- WB 多 bank 模型(同时服务多个 MAC consumer)
- WB ↔ DRAM 自动 victim eviction 算法
- Compression 真实实现(本版只 capability flag 占位)

---

## §2-§4 待 §1 Accepted 后展开

每个 § 走同样流程:draft → review → 实现 → 测试。

## 评审通过标准

请按 SPEC v1.0 的 review 方法,关注:

1. **与 DSB 的边界**:WB 是真的独立子类还是 DSB 的 capability flag?§1.2.3 给了 ADR-002 §3 三条理由 → 新子类。同意吗?
2. **测量口径**:§1.8 的三个评估能否客观判定"通过/未通过"?
3. **calibration 兜底**:area/energy 系数都标 calibration knob,Phase 5 校准前不可信 — 可接受程度?
4. **依赖链**:WB 落地后,后续 §2 OB 是否需要先调整 MAC 接口?(我倾向是,会在 §2 draft 里说明)
