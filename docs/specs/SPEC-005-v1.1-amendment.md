# SPEC-005 v1.1 增订 — Area 系数 + UNPACK 格式 capability

文档状态：**v1.1 Draft（amendment to SPEC-005 v0.1 Draft — Review pending）**
最后更新：2026-06-04
Owners：架构组
背景:配合 SPEC-001 v1.1 §3.2.5(area 维度)与 SPEC-007(控制/传输模块),
为 SPEC-005 已有的 DAGC/DSB/MAC/VAU/AVP 补充 area 系数,并新增 UNPACK
格式相关的 capability,以回答用户"UNPACK 格式的面积优化"评估。

## 1. Area 系数表

全部 `[calibration knob]`,Phase 5 校准前为占位估计。

| 模块 | 基线 area_um2 | 主要拆分(`AreaModel.breakdown`) |
|---|---|---|
| DAGC | 60_000 | logic=20_000, sram=35_000, io=5_000 |
| DSB | 200_000 | logic=30_000, sram=160_000, io=10_000 |
| MAC | 350_000 | logic=300_000(MAC array), sram=40_000, io=10_000 |
| VAU | 80_000 | logic=70_000, sram=5_000, io=5_000 |
| AVP | 50_000 | logic=45_000, sram=2_000, io=3_000 |

- **§A.1** Probe modules(producer / consumer / passthrough / merger)和
  dummy 返回 `AreaModel(um2=0.0, notes="virtual")`。
- **§A.2** SPEC-005 §1.6 已有的 calibration knob 列表加一行:
  `"area_um2_<module>"` 全部 calibration knob。

## 2. UNPACK 格式 capability

### 2.1 capability flag(不是新模块)

按 ADR-002 判定,**不**新建 INTERLEAVER/UNPACK 模块 —— UNPACK 在
逻辑上是 DAGC 的一种数据 reshape 模式,与现有 DAGC 共享 port_specs /
functional 数值语义;符合 "capability flag" 判据。

新增 declared_capability:`"compact_unpack"`(默认关闭)。

```yaml
modules:
  dagc_0:
    type: DAGC
    config:
      enable_compact_unpack: true   # 默认 false
```

### 2.2 行为差异

- **§U.1** `enable_compact_unpack=true` 时,DAGC 走压缩 unpack 路径:
  | 维度 | 关 unpack | 开 compact_unpack |
  |---|---|---|
  | latency / token | 4 cycles | 5 cycles(+1 cycle 解码) |
  | area_um2 | 60_000 | 48_000(**-20%**,因为消除了完整的 unpack
    寄存器组,改用动态解码) |
  | energy / token | 1.2 pJ | 1.0 pJ |

- **§U.2** **面积优化口径**:variant("开 compact_unpack")vs baseline:
  ```
  Δarea_um2 ≤ -10_000              (绝对值)
  Δlatency_ps ≤ +5% × baseline      (退化容忍 5%)
  ```
  这是平台对"UNPACK 格式的面积优化"评估的形式化通过标准。

- **§U.3** functional(SPEC-004 §5):开关 compact_unpack 不改变 DAGC
  数值输出 → `compare_tensors(baseline, variant)` 必须返回
  `ComparisonResult(equal=True)`。这把"格式优化不破坏数值正确性"做成
  断言。

## 3. 知识闭环 — 用户清单对照

| 用户评估项 | 落到本增订 / SPEC-007 哪条 |
|---|---|
| OGU 加速 op-gen / MCU 负载 2× | SPEC-007 §2.5 / §3.3.2 |
| 节省 N 个 MCU @ 单/双线程 | SPEC-007 §2.3.3 / §2.5.3 |
| MTU 融合 TAU/DMA | SPEC-007 §6 |
| 3D 架构 DAGC 外置 10% 代价 | SPEC-003 v1.1 §2.2 `__relocate__` |
| 提频 | SPEC-001 v1.1 §3.1.x + SPEC-003 v1.1 §2.1 |
| 精度不归一 | SPEC-005 v1.0 已支持(Precision config + Mapper) |
| DSB / 大算子能效 | SPEC-005 v1.0 已支持(estimate_energy + 大 shape op) |
| MAC/DSB/AGU 算法激励 | SPEC-007 §7 + SPEC-005 §1.6 联合扫描 |
| UNPACK 格式面积优化 | 本文 §2 |

## 4. 测试要求

- **§T.1** 每个 SPEC-005 模块的 conformance test 增加 `estimate_area()`
  返回值范围检查(±20% bound,因 calibration knob)。
- **§T.2** `tests/integration/test_unpack_area_tradeoff.py`:用 baseline vs
  variant 验证 §U.2 不等式 + §U.3 functional 等价。
