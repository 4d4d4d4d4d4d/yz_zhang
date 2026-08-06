# SPEC-013 物理 PPA 模型(literature-grounded,非经验拍值)

文档状态:**v0.1 Draft(implementation spec)**
最后更新:2026-08-05
Owners:架构组
触发:用户要求"要真实模拟,不要臆想"——面积/能量系数必须有可引用的物理依据,
不能是随手拍的圆整常数(见 `docs/Fidelity-Audit.md`)。
派生自:SPEC-001 §3.1(area/power 聚合)、SPEC-005(模块库)、
`npu_sim/physical.py`(实现)。

## 0. 范围与原则

本规范定义把模块 PPA(面积/能量/漏电)从"每能力固定常数"升级为
**参数化物理模型**的口径。核心原则:

1. **每个常数可溯源**到公开文献,并标注工艺节点。代码里 grep 得到引用。
2. **形式物理正确**:面积随数据通路规模缩放(PE 数 / SRAM 字节),能量随
   运算数缩放——即使单位系数有不确定带,函数形式必须对。
3. **不臆造缩放**:能量取自 Horowitz(45nm 实测/报告值)时**就用 45nm**,
   不臆造缩到更细节点;跨节点缩放是 Phase 5 用公开 scaling 因子做的校准步。
4. **渐进迁移**:一次迁一个模块(先 MAC),其余保持现状并在 §5 登记,与
   用户"一个个依次"的工作流一致。

参考节点:**45 nm**。

## 1. 能量:每运算焦耳数 @ 45nm

来源:**M. Horowitz, "1.1 Computing's Energy Problem (and what we can do about
it)", ISSCC 2014, Fig. 1.1.5**(业界最常引用的 energy-per-op 表)。

| 运算 | pJ @45nm | 运算 | pJ @45nm |
|---|---|---|---|
| int8 add | 0.03 | fp16 add | 0.4 |
| int32 add | 0.1 | fp32 add | 0.9 |
| int8 mult | 0.2* | fp16 mult | 1.1 |
| int32 mult | 3.1 | fp32 mult | 3.7 |
| SRAM 32b read (8KB) | 5.0 | DRAM 32b | 640 |

\* int8 mult 非原表直给:乘法能量 ~随位宽平方,int32=3.1pJ → int8≈3.1×(8/32)²≈0.2pJ。

**每 MAC 能量** = 乘 + FP32 累加(psum 通路是 FP32):
`int8 MAC = 0.2 + 0.9 = 1.1 pJ`;`bfp16/fp16 MAC = 1.1 + 0.9 = 2.0 pJ`。
累加的 FP32 加法(0.9pJ)在低精度 MAC 里占主导——这是真实的,低精度省的是
乘法不是累加。

## 2. 面积:解析门/单元计数模型 @ 45nm

**单位成本**(公开值):
- 6T SRAM bitcell ≈ **0.25 µm²** @45nm(TSMC 45nm ~0.25、Intel 45nm 0.346;
  取密集 foundry 6T)。
- NAND2 等效标准单元 ≈ **0.8 µm²** @45nm(各库 0.7–1.0)。
- 漏电 ≈ **3 nW/门**(45nm GP 量级)。

**门计数解析法**:
- n-bit 阵列乘法器 ≈ `n²` 部分积 AND 门 + `n·(n−1)` 全加器;
- n-bit 加法器 ≈ `n` 全加器;n-bit 寄存器 ≈ `n` 触发器;
- 一个全加器 / 触发器 ≈ 5 NAND2 等效门。

**不确定性**:门计数面积是解析估计(±~30%)。校准前**关键是函数形式**
(面积 ∝ PE 数),单位成本引用公开值;Phase 5 用综合替换单位成本收窄误差。

## 3. MAC 物理模型(本规范首个落地模块)

MAC PE = 乘法器 + 累加器。每支持一种精度就多一条乘法器 lane;FP32 累加加
一个 32-bit 加法器 + psum 寄存器。**每 PE 门数** = Σ active capability 门贡献:

| capability | 门贡献 | 计算 |
|---|---|---|
| int8_matmul | 344 | `mult_gates(8)=8²+8·7·5` |
| accumulate_fp32 | 320 | `add_gates(32)+reg_gates(32)=160+160` |
| bfp16_matmul | 394 | `mult_gates(8)+50`(共享指数对齐) |
| fp16_matmul | 726 | `mult_gates(11)+add_gates(11)` |

- **面积** = `rows × cols × (Σ per-PE 门) × 0.8 µm²`
- **漏电** = `rows × cols × (Σ per-PE 门) × 3 nW`
- **动态能量** = `MACs × per-MAC 能量(§1,按 op 精度)`

实测(默认 32×32,int8+accum+bfp16 = 1058 门/PE):
面积 = 1024×1058×0.8 = **866,714 µm²**;16×16 → 216,678;64×64 → 3,466,854
(严格 ∝ PE 数)。对比旧的 size-blind 常数 65,000——旧值不随阵列变,新值随
PE 数线性缩放,这才是"真模拟"。

## 3.1 VAU 物理模型(第二个落地模块)

VAU 有 `lanes` 条并行 FP ALU;每条 lane 携带所支持全部 op 的逻辑,故
**每 lane 门数** = Σ active capability 的 lane 逻辑门:

| capability | lane 门(FP32) | 依据 |
|---|---|---|
| vector_add | `fp_add_gates(24)` = 400 | 尾数加 + 对齐/规格化移位器 + 指数加 |
| vector_mul | `fp_mul_gates(24)` = 3496 | 尾数阵列乘 + 指数加 + 规格化 |
| vector_max | `fp_add_gates(24)` = 400 | 比较 ≈ 减法器 |
| relu | `mux_gates(32)` = 96 | max(0,x):符号判断 + 2:1 mux |

- **面积** = `lanes × (Σ per-lane 门) × 0.8 µm²`(默认 16 lanes、全 op = 4392
  门/lane → 56,218 µm²;32 lanes → 112,435,严格 ∝ lanes)。
- **动态能量/元素** = Σ active op 的 Horowitz 值(add 0.9、mul 3.7、max 0.9、
  relu 0.1 pJ)——保留原"sum active"语义(保守上界),每项换成文献值。
- FP 乘法器 lane 比加法器 lane 大 ~8×(`fp_mul_gates ≫ fp_add_gates`),这
  也是真实的(FP 乘法昂贵)。

## 4. 契约变更

- MAC 覆盖 `estimate_area()` / `total_area_um2()` / `static_power_uw()` /
  `estimate_energy()`,读 `npu_sim/physical.py`。
- MAC 的 `declared_capabilities()` 数值字段(area/power/energy)置 0 并注释
  "由物理模型取代"——保留仅为 capability-presence 契约(SPEC-001 §3.1)。
- 面积单调性(lean int8-only < full with bfp16/fp16)由 per-PE 门数保证,
  仍成立。

## 5. 迁移路线(其余模块,一个个依次)

| 模块 | 面积驱动项 | 能量驱动项 | 状态 |
|---|---|---|---|
| **MAC** | PE 数 × per-PE 门 | MACs × per-MAC(Horowitz) | ✅ §3 |
| **VAU** | lanes × per-lane FP-ALU 门 | elems × Σ active fp op(Horowitz) | ✅ §3.1 |
| DSB | buffer_kb × SRAM bit | bytes × SRAM read | 待做 |
| AVP | vector_width + LUT entries | elems × (transcendental≈几×fp) | 待做 |
| DAGC | unpack 数据通路宽度 | bytes × 移位/对齐 | 待做 |
| L2/TLU/MMU | 已 size-aware(`capacity_kb×800`),但 800 待换 SRAM bit 模型 | — | 部分 |

迁移每个模块:先在本规范加一节推导 + 引用 → 加 `physical.py` 函数 →
覆盖模块 PPA 方法 → 更新该模块测试 → flip
`test_area_model_sensitivity.py` 对应断言。

## 6. 测试要求

- **§T.1** `test_physical.py`:每个 `physical.py` 常数/函数对齐 §1–§3 的值与
  引用;门计数公式与缩放(2× PE → 2× 面积/漏电)。
- **§T.2** MAC 面积随 `array_rows×array_cols` 单调缩放(flip 原 size-blind
  tripwire);能量 = MACs × per-MAC。
- **§T.3** 面积单调性:int8-only < +bfp16 < +fp16。

## 7. 与 CLAUDE.md 一致性

CLAUDE.md 称系数是"pre-silicon estimates awaiting Phase 5 calibration"。本
规范**不声称已标定到硅**;它把系数从"无依据经验值"升级为"公开文献 @45nm +
物理正确的函数形式",并为 Phase 5(综合/PDK 替换单位成本 + 节点缩放)留出
干净的替换点。这是"从臆想到可校准"的第一步,不是终点。
