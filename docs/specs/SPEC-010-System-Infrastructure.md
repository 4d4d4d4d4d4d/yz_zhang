# SPEC-010 系统基础设施(System Infrastructure)

文档状态：**v0.1 Draft(implementation spec — full review)**
最后更新：2026-06-23
Owners：架构组

## 0. 范围

Tier 3 系统级模块。本版 2 个 § 一次交付:

| § | 模块 | 角色 |
|---|---|---|
| §1 | **PMU**(Performance Counter Unit) | 硬件 profiling counter |
| §2 | **SYNC**(Sync / Event Controller) | barrier / semaphore for multi-core |

PCIe 和 Multi-core(架构概念非单一模块)推迟到后续 spec。

## §1 PMU(Performance Monitor Unit)

### 1.1 capability + 身份
- `module_type()` = `"PMU"`
- capabilities:`cycle_counter`、`event_counter`、`module_busy_tracker`
- 新 IModule 子类:从 stat_sink 抽 counter 数据,不直接参与 token 流

### 1.2 端口
- `event_in`(INPUT, COMMAND, 可选,接 mcu 触发的事件)
- `report_out`(OUTPUT, COMMAND, 可选,定期 flush counter snapshot)

### 1.3 行为 / latency
- 后台运行,不消耗 token 流。每 `report_period_cycles` 拍 dump 一次 counter 到 stat_sink
- 默认 `report_period_cycles=100`,`counters=["cycle","stall","tokens"]`

### 1.4 area / energy
- `AreaModel(um2 = 5_000 × n_counters)`,`n_counters=3` 默认 `[calibration knob]`
- dynamic = negligible(0.05 pJ/cycle)

### 1.5 stage
`idle` / `sample` / `flush_report`

### 1.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| PMU on/off 面积代价 | 无 PMU | 加 PMU |
| counters 数量影响 | `n_counters=2` | `=8` |
| report_period 影响 | `=100` | `=10`(高频) |

## §2 SYNC(Sync / Event Controller)

### 2.1 capability + 身份
- `module_type()` = `"SYNC"`
- capabilities:`barrier`、`semaphore`、`event_dispatch`
- 新 IModule 子类:多 core 调度原语,扇入扇出 trigger

### 2.2 端口
- `arrive_in`(INPUT, COMMAND):某 core barrier-arrive
- `release_out`(OUTPUT, COMMAND):全员到齐后释放

### 2.3 行为 / latency
- 收到 `n_participants` 个 arrive token → 1 cycle 后发 release(广播)
- 默认 `n_participants=2`,`barrier_overhead_cycles=2` `[calibration knob]`

### 2.4 area / energy
- `AreaModel(um2 = 8_000 + n_participants × 1_500)` `[calibration knob]`
- dynamic = `1.0 pJ/barrier_event`

### 2.5 stage
`idle` / `wait_arrive` / `release_broadcast`

### 2.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| 参与者数影响 | `n_participants=2` | `=8` |
| barrier overhead | `=1` | `=8` |
| 与 MCU-only 对比 | 无 SYNC | 加 SYNC |

## 实施路线 + Step 7

两个 § 一次实现 + 各 2 对 YAML use case + 各 1 个测试文件。Step 7 系统集成:
SPEC-005 + SPEC-007 + SPEC-008 + SPEC-009 + SPEC-010 全部 19 个模块同 YAML。
