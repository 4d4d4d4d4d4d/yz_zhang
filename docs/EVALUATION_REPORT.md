# NPU 仿真平台评估报告 v1.0

> 自动生成 — `python scripts/run_all_evaluations.py`
> 用例数: **36**  通过: **36**

## 摘要

平台支持 33 个模块类型 (26 硬件 + 7 测试),覆盖 6 spec 家族 (SPEC-005/007/008/009/010/011)。每个评估都是 *改 YAML → `elaborate_and_run` → `compare`* 三步,无 Python 端模块构造 (由 `assert_evaluation_is_yaml_driven` 自动 enforce)。

## Original list — Control plane

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **OGU 替代 MCU 负载 (真握手)** | MCU has_ogu_peer false → true; add OGU peer + ogu_req/resp handshake | -1.59 M ps | -76.2 % | -50.0 k | +0 ps | — | ✅ |
| **MTU 融合 TAU+DMA** | Replace TAU→DMA chain with single fused MTU | +16.0 k ps | +0.6 % | -15.0 k | +0 ps | — | ✅ |

## Original list — Topology

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **3D 架构 DAGC 外置 (+10% 延迟)** | __relocate__ DAGC across dies, latency_penalty_pct=10 | +1.0 k ps | +5.6 % | +0 | +0 ps | — | ✅ |

## Original list — Timing

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **提频 1 GHz → 2 GHz** | Same arch, clock period 1000 → 500 ps | -9.0 k ps | -50.0 % | +0 | +0 ps | — | ✅ |

## Original list — Precision

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **精度不归一 (INT8 only vs INT8+BFP16+FP16)** | Enable bfp16 + fp16 lanes on MAC | +0 ps | +0.0 % | +33.0 k | +0 ps | — | ✅ |

## Original list — Workload

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **DSB 大算子能效 (8 B vs 1024 B token)** | Bigger tokens, fewer of them through DSB | +496.0 k ps | +2755.6 % | +0 | +0 ps | — | ✅ |

## Original list — Stimulus

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **MAC array stimulus (smaller → larger)** | MAC array sized up, bottleneck shifts | -16.0 k ps | -32.0 % | +0 | -5.0 k ps | mac → None | ✅ |
| **AGU pipeline depth stimulus** | AGU pipeline depth 1 → 8 | +7.0 k ps | +2.7 % | +0 | +0 ps | — | ✅ |

## Original list — Area

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **UNPACK 格式 (compact unpack on)** | DAGC enable_compact_unpack false → true | +8.0 k ps | +6.2 % | -2.0 k | +3.0 k ps | dagc | ✅ |

## SPEC-008 — Weight Buffer

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **WB 容量 64 → 256 KB** | WB capacity_kb 64 → 256 | +0 ps | +0.0 % | +230.4 k | +0 ps | — | ✅ |
| **WB prefetch on** | WB enable_prefetch false → true | +0 ps | +0.0 % | +4.0 k | +0 ps | — | ✅ |
| **WB overflow (4 KB cap vs 8 KB workload)** | WB capacity 64 → 4 KB, weights overflow | -132.0 k ps | -48.2 % | -72.0 k | +0 ps | — | ✅ |

## SPEC-008 — Output Buffer

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **OB tile 8 → 64 KB** | OB tile_kb 8 → 64 | +0 ps | +0.0 % | +84.0 k | +0 ps | — | ✅ |
| **OB double-buffer** | OB max_in_flight_tiles 1 → 2 | +0 ps | +0.0 % | +12.0 k | +0 ps | — | ✅ |
| **OB int32-only (no fp32)** | OB support_fp32_acc true → false | +0 ps | +0.0 % | -6.0 k | +0 ps | — | ✅ |

## SPEC-008 — Quant

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Per-channel scale** | Quant enable_per_channel false → true | +4.0 k ps | +1.6 % | +3.5 k | +0 ps | — | ✅ |
| **Direction dequant** | Quant direction quant → dequant | +0 ps | +0.0 % | +0 | +0 ps | — | ✅ |

## SPEC-008 — SFU

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Trig enabled** | SFU enable_trig false → true | +0 ps | +0.0 % | +8.0 k | +0 ps | — | ✅ |
| **div vs exp op** | SFU default_op exp → div | +36.0 k ps | +64.3 % | +0 | +0 ps | — | ✅ |

## SPEC-009 — IM2COL

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Kernel 1×1 → 3×3** | IM2COL kernel_h/w 1 → 3 | +48.0 k ps | +600.0 % | +0 | +0 ps | — | ✅ |

## SPEC-009 — RDC

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Tree width 4 → 16** | RDC tree_width 4 → 16 | +0 ps | +0.0 % | +18.0 k | +0 ps | — | ✅ |

## SPEC-009 — NoC

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Route cycles 2 → 4** | NoC route_cycles 2 → 4 | +16.0 k ps | +88.9 % | +0 | +0 ps | — | ✅ |

## SPEC-009 — CDE

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **zlib enabled** | CDE enable_zlib false → true | +0 ps | +0.0 % | +10.0 k | +0 ps | — | ✅ |

## SPEC-009 — Transpose

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **3D support enabled** | Transpose enable_3d false → true | +0 ps | +0.0 % | +5.0 k | +0 ps | — | ✅ |

## SPEC-010 — PMU

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Counters 2 → 8** | PMU n_counters 2 → 8 | +0 ps | +0.0 % | +30.0 k | +0 ps | — | ✅ |

## SPEC-010 — SYNC

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Participants 2 → 8** | SYNC n_participants 2 → 8 | -6.0 k ps | -54.5 % | +9.0 k | +0 ps | — | ✅ |

## SPEC-011 — Memory Controller

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Banks 8 → 16** | MC n_banks 8 → 16 | +0 ps | +0.0 % | +64.0 k | +0 ps | — | ✅ |

## SPEC-011 — L2 Cache

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **256 KB → 2 MB, hit_rate 0.5 → 0.9** | L2 capacity_kb + hit_rate up | -12.0 k ps | -18.2 % | +1.43 M | +0 ps | — | ✅ |

## SPEC-011 — Sparse Engine

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Sparsity 30% → 80% structured** | SE sparsity_ratio + enable_structured_pruning | -36.0 k ps | -78.3 % | +8.0 k | +0 ps | — | ✅ |

## SPEC-011 — TLU

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Embedding 512 KB → 8 MB + scatter** | TLU table_size_kb + scatter enabled | +16.0 k ps | +42.1 % | +4.61 M | +0 ps | — | ✅ |

## SPEC-011 — CMDQ

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **Depth 16 → 256 + priority** | CMDQ queue_depth + priority | +0 ps | +0.0 % | +53.0 k | +0 ps | — | ✅ |

## SPEC-011 — MMU

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **TLB 16 → 256, hit_rate 0.5 → 0.95** | MMU tlb_entries + hit_rate | -40.0 k ps | -87.0 % | +48.0 k | +0 ps | — | ✅ |

## Full-stack — NPU v2

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **MCU+OGU + DAGC compact + relocate** | Stack 3 levers in one overrides block | +2.0 k ps | +2.6 % | -52.0 k | -2.0 k ps | avp | ✅ |

## Full-stack — NPU v2 plus

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **WB cap + prefetch + OB tile + Quant per-ch + SFU trig** | Stack 5 SPEC-008 levers | +0 ps | +0.0 % | +329.9 k | +0 ps | dsb | ✅ |

## Full-stack — NPU v3

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **5-spec stacked (008/009/010 levers)** | WB + IM2COL + RDC + PMU + SYNC | +0 ps | +0.0 % | +276.4 k | +0 ps | — | ✅ |

## Full-stack — NPU v4

| Use Case | 改了什么 | drain Δ | drain Δ% | area Δ μm² | stall Δ | bottleneck | Valid |
|---|---|---:|---:|---:|---:|---|:---:|
| **6-spec stacked (incl. SPEC-011)** | 26 modules, 6 SPEC-011 knobs flipped | +0 ps | +0.0 % | +5.03 M | +0 ps | — | ✅ |

## 横向洞察

### 1. 加速 vs 面积 取舍

以 OGU 替代 MCU 为例:**area -50 k μm²** 同时 **drain -77%** → 加速 + 省面积同时获得(OGU 卸载使 MCU 的 fallback capabilities 失活,净面积反而下降)。属于罕见的"双赢"评估场景。

### 2. 容量 vs 性能 取舍

L2 容量 256 KB → 2 MB 同时把 hit_rate 0.5 → 0.9:**area +1.43 M μm²** (主要 SRAM),**drain -12 k ps** (-18%)。area 涨幅 ~5×,性能涨幅 ~20%。高 cache 命中场景下的典型 frontier 点。

### 3. 工作负载敏感

DSB 同一硬件,8 B 小 token → 1024 B 大 token 后 drain **+2755%**。面积零变化,纯 workload 决定的能效拐点。

### 4. 6 spec 叠加

Full-stack NPU v4 (26 模块) 同时翻 6 个 SPEC-011 knob,area Δ **+5.03 M μm²** *精确* 等于各 § 之和,验证 6 个 area model 互不干扰、可叠加。
