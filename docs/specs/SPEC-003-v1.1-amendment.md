# SPEC-003 v1.1 增订 — 拓扑迁移 Override + Clock Domain 配置

文档状态：**v1.1 Draft（amendment to SPEC-003 v1.0 Accepted — Review pending）**
最后更新：2026-06-04
Owners：架构组
背景:用户 2026-06-04 评估需求中 "3D 架构 DAGC 外置,预估 10% 代价" 和
"提频" 这两类**拓扑/时钟级 variation** 在 v1.0 override DSL(SPEC-003 §6)
下无法表达,本增订增加两类 override 操作 + 一个新的顶层节。

## 1. 动机回顾

v1.0 SPEC-003 §6 override 支持的操作:
- 标量字段覆写
- 列表 `__append__` / `__remove__`
- module config 局部 patch

不支持的操作(产生本增订的需求):

| 用户场景 | v1.0 缺什么 |
|---|---|
| "DAGC 外置 10% 代价":把 DAGC 从片内迁到片外 die,并加 10% latency/area | 没有 `relocate_module` 操作 |
| "3D 架构":同一逻辑模块物理上分到不同 die,跨 die 连接带 penalty | 没有 `physical_die` 字段 / penalty 模型 |
| "提频":compute path 跑 2 GHz,control path 跑 500 MHz | 没有 per-domain clock 配置(SPEC-001 v1.1 §3.1.x 已加 module 端,但 DSL 端没有) |

## 2. 增订内容

### 2.1 新顶层节 `clock_domains:`(对应 SPEC-001 v1.1 §3.1.x.2)

```yaml
clock_domains:
  global:
    freq_hz: 1_000_000_000        # 默认 1 GHz
  compute_high:
    freq_hz: 2_000_000_000        # 提频实验
  control_slow:
    freq_hz: 500_000_000

modules:
  mac_0:
    type: MAC
    config:
      clock_domain: compute_high
  mcu_0:
    type: MCU
    config:
      clock_domain: control_slow
```

- **§3.7.1**(新增)`clock_domains` 是顶层可选节;若缺省,所有模块默认
  绑定 `global` domain。
- **§3.7.2** `freq_hz` 必须为正整数,**精确到 Hz**(因为 SPEC-002 §5.1
  CDC 协议依赖整数周期对齐)。
- **§3.7.3** 模块 config 里引用未声明 domain 名 → Elaborator Phase 2
  raise `ConfigurationError`(SPEC-003 §5 Phase 2 校验扩展点)。

### 2.2 Override 新操作 `__relocate__`(对应 §6.x)

```yaml
base: baseline.yaml
overrides:
  modules:
    dagc_0:
      __relocate__:
        from_die: 0                 # 信息性
        to_die: 1                   # 信息性
        latency_penalty_pct: 10     # 加到所有 estimate_latency 返回值
        energy_penalty_pct: 10
        area_penalty_pct: 0         # 外置不增 area,只增延迟和能耗
```

- **§6.x.1** `__relocate__` **只动 estimate_* 系数**,不改 port 拓扑、
  不改 module_type、不改 capability。它本质是"系数 patch"的语法糖。
- **§6.x.2** 三个 penalty 都是**百分比加成**:`new = old × (1 + pct/100)`。
- **§6.x.3** 若同一模块既有 `__relocate__` 又有 config 局部 patch,
  config patch 先生效,然后 relocate penalty 应用到最终系数上。
- **§6.x.4** Elaborator Phase 3 校验:`to_die ≠ from_die`、所有 penalty
  ≥ 0;Phase 3.5 warn:若 `latency_penalty_pct > 50` 或 `area_penalty_pct
  > 50`,提示"超出 relocate 合理范围,考虑用全替换"。

### 2.3 Connection 拓扑提示 `physical_dimension:`(对应 §3.x)

```yaml
connections:
  - from: dagc_0.out
    to:   dsb_0.in
    physical_dimension: cross_die   # 可选枚举: "intra_die" | "cross_die" | "stacked_3d"
    cross_die_extra_cycles: 2       # 当 cross_die / stacked_3d 时强制 ≥ 1
```

- **§3.x.1** `physical_dimension` 缺省 `"intra_die"`,即 v1.0 行为
  (无额外周期)。
- **§3.x.2** `cross_die`/`stacked_3d` 时,transport 在 SPEC-002 §3 既有
  契约上**注入额外的 transport latency**;tracer 上报反压时,应在
  `transport_stall` 类别下单独记录(reason="cross_die")。
- **§3.x.3** 校验:`cross_die_extra_cycles` 仅在 `physical_dimension ≠
  intra_die` 时允许,且必须 ≥ 1。

## 3. 影响面

| 文件 | 改动 |
|---|---|
| `npu_sim/architecture/dsl_schema.py` | 加 `clock_domains` schema、`__relocate__` schema、`physical_dimension` schema |
| `npu_sim/architecture/overrides.py` | 实现 `__relocate__` 处理 |
| `npu_sim/architecture/elaborator.py` | Phase 2 注入 per-domain clocks;Phase 3 cross_die 校验;Phase 5 把 penalty 包到 estimate_* |
| `npu_sim/runtime/transport.py` | cross_die_extra_cycles 注入 |
| Spec | SPEC-001 v1.1(已起草)、SPEC-005 v1.1(area 系数) |

## 4. v1.1 候选(本增订之外)

- 多 floorplan 描述(每个 die 内部 X/Y 坐标) → v1.2;现在 die 只是
  enum 不是坐标。
- 跨 die 带宽建模(目前只有 latency 加成) → v1.2。

## 5. 测试要求

- **§5.1** `tests/fixtures/architectures/usecase_dagc_external.yaml` —
  baseline 的 `__relocate__` 变体,断言 drain_time / energy / area
  delta 与 SPEC-007 §6.3.1 类似的不等式成立。
- **§5.2** `tests/fixtures/architectures/usecase_high_freq.yaml` —
  compute domain 提频 2×,断言 drain_time 减半(理想 case),energy
  不变(active cycles 不变,频率仅缩短 wall time)。
