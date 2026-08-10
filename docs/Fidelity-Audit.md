# 保真度审计:哪些是"真模拟",哪些是"经验拍的数"

文档状态:**审计报告 v1.0**
最后更新:2026-08-05
触发:用户质疑"是不是真实模拟,感觉所有面积和效率都是随意经验定的值"
关联:CLAUDE.md("coefficients are pre-silicon estimates awaiting Phase 5
calibration")、SPEC-005 v1.1 amendment §A.2、review-v1.1-proposal §30

## 0. 结论先行(直接回答)

**你的直觉基本正确,而且这是平台已知并已记录的限制 —— 但要分两层看:**

1. **机制(structure)是真的、机械的、可信的。** 逐拍调度、反压、FIFO 占用、
   stall 传播是真正的离散事件仿真;**每个 token 的时序是从架构参数 + 数据流
   推导出来的**(不是查表拍的常数),所以吞吐/瓶颈/drain 的**趋势与比值**、
   "加宽某级有没有用/瓶颈迁到哪"这类**相对/方向性结论可信** —— 瓶颈模型对
   实测 drain 复算到 **0.1%**(§2),这是涌现出来的,不是拟合的。

2. **绝对系数(面积 μm²、能量 pJ、功耗 μW)基本是"经验拍的圆整数",不可信。**
   全仓库**没有任何一处**把这些数溯源到工艺节点 / 标准单元库 / 综合结果 /
   datasheet / 实测(§3 grep 证据)。大量是 18000、9000、3500、0.8pJ 这种圆
   整数。平台**自己**在 SPEC-005 v1.1 §A.2 声明它们"全部 `[calibration
   knob]`,Phase 5 校准前为占位估计",review-v1.1-proposal §30 甚至把"这会
   不会让评估结果不可信"列为**公开待决问题**。所以:**这不是 bug,是明示的
   pre-silicon 占位**;但它确实意味着**绝对 PPA 数字不能信**。

一句话:**这是一个"时序/数据流机制真实、绝对 PPA 系数是占位"的仿真器。**
拿它做**相对架构权衡**是可信的;拿它报**这颗芯片多少 μm²/多少 pJ** 不可信。

> **更新(2026-08-05,本次起):** 已开始把占位系数**逐模块换成 literature-
> grounded 物理模型**(SPEC-013)。**MAC、VAU、DSB 已迁移**:面积 = 规模
> (PE 数 / lanes / SRAM 字节)× 单位成本(@45nm),能量 = 运算数 × per-op
> (Horowitz ISSCC'14),面积随规模真实缩放(MAC 16²→64² = 217k→3.47M;VAU
> 16→64 lanes = 56k→225k;DSB 32→128 KB = 187k→749k µm²)。其余 compute 模块
> (AVP/DAGC)按 SPEC-013 §5 路线逐个跟进。下表的 "compute 面积/能量" 结论对
> **已迁移模块不再适用**。

## 1. 信任矩阵(TL;DR 速查)

| 你想得到的结论 | 可信? | 原因 |
|---|---|---|
| 哪个器件是吞吐瓶颈 | ✅ 可信 | 从 config+数据流实测,复算 0.1%(§2) |
| 加宽 X 能不能提吞吐 / 提多少(相对%) | ✅ 可信 | 时序机械推导,趋势正确 |
| 瓶颈会不会迁移、迁到哪 | ✅ 可信 | 同上(`optimize`/`sweep` 实测) |
| 反压/stall/FIFO 满在哪、死锁 | ✅ 可信 | 真正的逐拍协议 |
| 两个变体的 drain 谁快、快几倍 | ✅ 大体可信 | 时序推导;但见 §4 MAC 例外 |
| 这颗芯片的**绝对** drain(ns) | ⚠️ 半信 | 拍数机械,但时钟周期/绝对延迟未标定 |
| 这颗芯片**绝对**面积(μm²)/能量(pJ)/功耗 | ❌ 不可信 | 圆整占位常数,无溯源(§3) |
| 跨模块面积/能量**比值**(MAC vs DSB 谁大) | ❌ 不可信 | 各自独立拍的常数,比值无意义 |
| 加宽 compute 器件的**面积代价** | ❌ 不可信 | 面积对规模无感(§4 结构缺口) |

## 2. 时序是"真推导"的证据(为什么机制可信)

每个数据通路模块的**每 token 服务拍**是架构参数 + token 大小的函数,不是常数:

| 模块 | 服务拍公式(`file`) | 解读 |
|---|---|---|
| DSB | `ceil(size_bytes / read_throughput)` (`dsb_module.py:_stage_cycles`) | 延迟 ∝ 数据量 / 带宽 ✔形式正确 |
| VAU | `ceil(size_bytes / lanes)` (`vau_module.py:_op_cycles`) | ∝ 数据量 / 并行度 ✔ |
| AVP | `ceil(size_bytes / vector_width) × 2` (`avp_module.py:_act_cycles`) | ∝ 数据 / 宽度,×2 超越函数 ✔ |
| DAGC | `f(size_bytes, unpack_throughput)` (`dagc_module.py:_unpack_cycles`) | ∝ 数据 / 解包带宽 ✔ |
| MAC | `cols // rows + 1` (`mac_module.py:_compute_cycles`) | ⚠ **与 token 无关**(§4 例外) |

因为服务拍是 config 的函数,改 YAML 里的 `read_throughput`/`lanes`/
`vector_width` 会真实改变仿真结果(`test_area_model_sensitivity` /
`test_sweep` 均实测到 drain 随之变化)。**瓶颈模型**(`evaluation/pipeline.py`)
用实测每级 II 复算 drain = `Σ II + (N−1)·II_bottleneck`,对 attention chip
实测 4232 拍复算 4226 拍(**0.1% 误差**,`test_pipeline_bottleneck.py`)。
**这个吻合是机械涌现的,不可能靠拍系数拟合出来** —— 这是"真模拟"的硬证据。

## 3. 绝对系数是"经验拍值"的证据(为什么绝对 PPA 不可信)

**溯源 grep 结论**:对 `nm|tsmc|process node|synthes|datasheet|measured
from|calibrat` 全模块搜索,**没有任何一处**把面积/能量常数关联到工艺或综合
数据。存在的只有 `[calibration knob]` 占位标记(明示"待标定")。

| 轴 | 取值方式 | 可信度 |
|---|---|---|
| 面积(compute:**MAC / VAU / DSB 已迁移**) | 规模 × 单位成本 @45nm(SPEC-013;DSB 用 SRAM macro 模型) | ✅ 物理正确形式 + 引用单位成本(±30%,待综合) |
| 面积(compute:AVP/DAGC,未迁移) | 每 capability 固定圆整常数,**与规模无关** | ❌ 占位 + 结构缺口(§4) |
| 面积(memory/DRAM:L2/TLU/MMU) | **随容量缩放** `capacity_kb × 800` (`l2_module.py`) | 🟡 形式对,系数 800 是拍的 |
| 面积(control:OGU/MCU/MTU/TAU/AGU/DMA) | 固定常数,**已标 `[calibration knob]`** | 🟡 明示占位 |
| 能量 | 部分固定(DAGC 0.8pJ),部分按架构因子缩放(OGU `0.25×_T_BUFFSIZE`、MCU `0.4×_T_OPCFG`) | 🟡 结构半对,乘子是拍的 |
| 静态功耗 | 固定圆整常数(12/18/8 μW) | ❌ 占位 |

**平台自认**:SPEC-005 v1.1 §A.2「全部 calibration knob,Phase 5 校准前为
占位估计」;review-v1.1-proposal §30 把「这会不会让结果不可信」列为公开待决。

## 4. 两个结构性缺口(不止是"没标定",是"模型缺项")

除了"系数没标定",有两处是**模型本身缺项**,更严重:

- **compute 面积对规模无感**(`test_area_model_sensitivity.py`,已 filed):
  MAC 阵列 32×32→64×64(4× PE)、VAU lanes×2、AVP vector_width×4 → **面积
  Δ=0**。这不是标定误差,是面积模型没有 size 项。→ 修复提案 SPEC-005 v1.1 §5。
- **MAC 时序对 shape 无感 vs estimate 对 shape 敏感**(README 实现期发现 #2):
  `_compute_cycles` 是常数,但 `estimate_latency` 按 `m·k·n` 缩放 —— 两个不
  一致的时序模型。是 reconcile 静态估 vs 实测 gap 的来源之一。

## 5. 披露一致性问题(本次审计新发现,已 filed)

`[calibration knob]` 标记在 **SPEC-007(control)/ SPEC-010 / SPEC-011(DRAM)**
模块的 `AreaModel.notes` 里**在代码中显式存在**(`grep` 可见),但
**SPEC-005 compute 模块(MAC/DSB/VAU/AVP/DAGC)的 capability 系数在代码里
没有这个标记** —— 只有 SPEC-005 v1.1 amendment 文档里声明。结果:**用户最
常看的正是 compute 器件,而这些器件的代码没有"这是占位值"的就地提示**。建议
把 provenance 标记补齐到 compute 模块(见 README v1.1 候选)。

## 6. 要让绝对数"变真"需要什么(Phase 5 校准路径)

1. **面积/功耗**:对每个模块按目标工艺(如 N5/N3)综合或查 PDK,得每
   capability 的面积/漏电,并落实 size 项(SPEC-005 v1.1 §5)。
2. **能量**:每 op 的 dynamic energy 用综合后 power 报告或 gate-level 仿真校准。
3. **时序绝对值**:时钟周期与关键路径由综合 STA 定;当前拍数机制可保留。
4. **锚点验证**:选 1–2 个已知 PPA 的真实 NPU 层(如某公开 MAC tile)做
   golden,校准后误差收敛到可接受带(如 ±20%,SPEC-005 §T.1 已埋 bound)。

在此之前,**把本平台当作"架构相对权衡 + 数据流/反压机制"仿真器用,不要引用
它的绝对 PPA 数字**。
