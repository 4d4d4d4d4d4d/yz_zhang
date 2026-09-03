# 对标分析:npu_sim vs QEMU(及正确的对标物)

文档状态:**分析报告 v1.0**
最后更新:2026-07-20
Owners:架构组
关联:ADR-001.1(Python 运行时是 SystemC stand-in)、SPEC-002(反压协议)、
SPEC-004(functional 接口)

## 0. 结论先行

**npu_sim 与 QEMU 不属于同一类模拟器,不能直接对标。**
QEMU 是 ISA 级功能模拟器(跑真实二进制,时间是可选副产品);npu_sim 是
微架构性能模拟器(跑 token 流,cycle-accurate 时间是第一产品)。正确的
对标物是 **gem5 / SystemC TLM-2.0 / Timeloop** 这一档。

但 QEMU 的四个工程机制值得借鉴,构成本平台的核心改进空间(§3)。

## 1. 定位对照

| 维度 | QEMU | gem5 | npu_sim(本平台) |
|---|---|---|---|
| 模拟对象 | ISA(x86/ARM/RISC-V 指令) | CPU 微架构 + 内存层次 | NPU 数据通路微架构 |
| 驱动输入 | 真实 guest binary / OS | 真实 binary(SE/FS 模式) | 合成 token 流 + YAML 配置 |
| 核心目的 | 功能正确(能跑 Linux) | 性能研究(IPC/cache) | PPA 评估(drain/area/energy/stall) |
| 时间模型 | 默认无时序;icount 近似 | event-driven cycle 级 | cycle-step 协程,每拍推进 |
| 执行速度 | JIT (TCG) ~数百 MIPS | ~100 k–1 M inst/s | **实测 107 k cycles/s**(26 模块) |
| 正确性基准 | 指令语义 bit-accurate | 微架构行为 | golden functional(非 bit-accurate) |
| 状态保存 | savevm/loadvm 快照 | m5 checkpoint | **无** |
| 可复现性 | record/replay 全确定 | 确定 | 基本确定(见 §3.3 隐患) |

一句话:**QEMU 关心"跑得对",npu_sim 关心"跑多快/多大/多耗电"。**
QEMU 用 icount 模式也只能给粗略时间;npu_sim 的每一拍都是有语义的。

## 2. 实测基线(2026-07-20,本仓库 HEAD)

| 指标 | 数值 |
|---|---|
| 架构规模 | 26 硬件模块(usecase_npu_v4_full_stack.yaml) |
| 仿真吞吐 | **107,550 cycles/s** |
| 20,000 拍墙钟 | 186 ms |
| 推算 1,000,000 拍 | **9.3 s** |
| 全测试套(549 tests) | ~5 s |

调度成本结构:`SimpleScheduler.run()` 每拍对每个活模块调一次
`next()` → 26 模块 × 100 万拍 = **2600 万次 Python 协程切换**。这是当前
吞吐上限的直接原因(纯解释器开销,QEMU 用 TCG JIT 消掉的正是这类开销)。

## 3. 借鉴 QEMU 的四个改进空间

### 3.1 Trace/program-driven 激励 ⭐ 优先级最高

**现状**:`Producer` 只发合成 token(`for i in range(n_tokens)`),
workload 表达力 = "多少个包、每个多大"。
**QEMU 对应物**:直接喂真实 guest binary。
**改进**:`TraceReplayProducer` — 读算子 trace 文件(ONNX 图导出 /
`matmul(M,K,N); relu; softmax; ...` 序列),按真实模型的算子序列 + shape
驱动仿真。评估对象从"抽象流量"升级为"ResNet50 / GPT layer 真实负载"。
**这是可信度的质变**,建议立项 SPEC-012。

### 3.2 Checkpoint / restore

**现状**:零 checkpoint 能力(grep 确认无 pickle/save_state),每次评估
从 cycle 0 全量重跑。
**QEMU 对应物**:savevm/loadvm。
**改进**:序列化 modules 状态 + FIFO 内容 + clock;支持"warmup 完成点存
档,N 个 variant 都从 checkpoint 起跑"。配合 §3.1 的长 trace 是刚需。
**实测修正见 §5.2** —— 二进制 loadvm 被生成器帧结构性阻断,留给 Phase 5;
savevm 的数据视图(只读全片快照)与"确定性重放即 restore"已落地。

### 3.3 确定性收口(record/replay)

**现状**:调度本身确定,但 `L2` / `MMU` 内部用 `random.Random(固定 seed)`
决定 hit/miss。seed 是硬编码的,不在 YAML 里;模块间执行顺序变化会改变
RNG 消费序列,导致跨版本结果漂移。
**QEMU 对应物**:record/replay 全链路确定。
**改进**(低成本):把 seed 提为 YAML config 字段;或改用确定性
access-pattern(每第 k 次访问 miss)。评估结果应当 bit-for-bit 可复现。

### 3.4 执行加速:event-driven 跳步(对应 QEMU 的 TCG 思想)

**现状**:模块大量时间在 `for _ in range(N): yield` 里空转
(MC 的 row_miss=40 拍、SFU 的 div=14 拍都是纯等待)。
**QEMU 对应物**:TCG 把热路径 JIT 成 native,消掉解释开销。
**gem5 对应物**(更贴切):event queue —— 不逐拍轮询,直接把"下一个
事件在第 T 拍"入堆,时间跳跃推进。
**改进**:SPEC-002 增订一个 `WAIT(n)` 原语(`yield n` 代替 n 次
`yield`),调度器聚合各模块的下一唤醒拍,直接跳到 min。空转段占比高的
workload 预计 10–100× 提速,语义完全等价(反压唤醒点不变)。
**注意**:这是 ADR-001.1 的敏感区 —— 必须保证跳步语义与逐拍语义在全部
549 测试上 bit-exact,否则破坏"SystemC 语义等价"承诺。

## 4. 不建议借鉴的部分

| QEMU 机制 | 不适用原因 |
|---|---|
| TCG 动态二进制翻译本体 | 我们没有 ISA;没有"指令"可翻译 |
| virtio / 设备直通 | 评估平台不需要 host I/O 虚拟化 |
| KVM 硬件加速 | 同上,无 guest CPU |
| 全系统 OS boot | SPEC-004 定位是数据流评估,非软件栈验证 |

## 5. 路线建议(按 ROI 排序)

| # | 改进 | 价值 | 工作量 | 状态 |
|---|---|---|---|---|
| 1 | SPEC-012 Trace-driven 激励(§3.1) | 评估可信度质变 | 中 | ✅ **已落地**(SPEC-012 + TraceProducer,跑真实 attention 层) |
| 2 | 调度加速(§3.4) | 大 max_cycles 4–336× | 中 | ✅ **部分落地**:见下方修正 |
| 3 | RNG 确定性收口(§3.3) | 可复现性 | 低 | ✅ **已落地**(L2/MMU 改确定性 miss-credit,零 random,`test_determinism.py` 锁 bit-identical) |
| 4 | Checkpoint/restore(§3.2) | 长 trace 评估提效 | 中 | ✅ **部分落地**:见 §5.2(savevm 数据视图 + 重放式 restore 落地;二进制 loadvm → Phase 5) |

## 5.1 §3.4 调度加速的实测修正(重要)

原设想的"WAIT(n) 跳步调度"(把 `for _ in range(N): yield` 换成 `yield N`,
跳过纯延迟拍)**经实测在本平台是 no-op**:

> 实测:4000 拍中 3999 拍至少有一个模块 busy;即使"全 idle"的那 1 拍,
> Producer/Consumer 仍在 `yield None` 逐拍轮询输入。只要有一个轮询进程,
> 调度器每拍都得步进它 → 无法跳步。

真正的 event-skip 需要**端口级事件通知**(sensitivity list:token 入队时
唤醒下游、空输入时休眠),这要改写所有模块的 idle 路径 + 端口 + 调度器,
风险极高,且当前无长 workload 痛点 —— **应留给 Phase 5 SystemC**
(ADR-001.1),SystemC 内核天然是 event-driven。

**但**发现并落地了一个安全的等价加速:**quiescence 早退**。调度器会跑满
`max_cycles` 即使 sim 早已排空(实测某 fixture 在 cycle 4232 排空却被要求
跑 100000 拍,96% 是排空后的空轮询)。`run_simulation(stop_at_quiescence=
True)`(默认开)在"无模块 busy + 所有 FIFO 空 + 无存活激励源"时提前停。
所有指标在排空点已定型 → 结果与跑满 bit-identical(592 测试全绿即证明),
实测加速 **4.6×–336×**(取决于 max_cycles 相对排空点的余量)。

## 5.2 §3.2 Checkpoint/restore 的实测修正(重要)

原设想的"二进制 checkpoint/restore"(序列化全片状态,N 个 variant 从存档
点起跑)**在本平台的 Python 运行时被结构性阻断**:

> 每个模块的在途时序状态活在其 `behavior()` **生成器帧**里 —— 例如 MAC 的
> `for _ in range(fill_n): yield` 倒计数,以及 `act` / `total` 等帧内局部
> 变量。`snapshot_state()`(SPEC-001 §3.1 ModuleState)**不暴露**这些;而
> 运行的 Python 生成器**不可 pickle**。要做真正的 loadvm,必须把每个
> `behavior()` 重写成把倒计数外化到实例属性的显式状态机 —— 这是 Phase 5
> 级别的改写,ADR-001.1 已把它交给 SystemC 内核(天然可 checkpoint)。
> `test_state_snapshot.py::TestBinaryCheckpointBlocker` 锁死该发现。

**但**落地了 savevm 的**可行子集**与一个零成本的等价 restore:

1. **只读全片快照(savevm 数据视图)**:`capture_state(arch, cycle)` /
   `snapshot_at_cycle(arch, at_cycle)` 冻结每个模块的 `snapshot_state()` +
   每条连接的 FIFO 占用 + clock,产出可逐字段比较的 `StateSnapshot`。CLI
   `snapshot <arch> --at-cycle N`。这是调试 / 跨版本同拍对比的实用工具,
   不需要 pickle 生成器。
2. **确定性重放即 restore**:因为运行时现已完全确定(§3.3 移除 RNG),
   "restore 到第 N 拍"= 从 cycle 0 确定性重放到 N —— 两次独立重放到同一拍
   产出**逐字段相同**的 `StateSnapshot`(`test_state_snapshot.py::
   TestRestoreIsDeterministicReplay` 证明)。重放到 warmup 点仅需
   ~微秒/拍(实测 107k 拍/s),所以在本平台上重放是二进制 checkpoint 的
   诚实、零风险替代品 —— 后者只多省墙钟,不多给正确性。

## 6. 与既有决策的一致性

- ADR-001.1 已声明 Python 运行时是 SystemC stand-in、Phase 5 换内核。
  §3.4 的跳步调度**不与此冲突**(SystemC 本身就是 event-driven),反而是
  向 SystemC 语义靠拢的一步。
- SPEC-004 的 golden functional 定位不变;§3.1 的 trace 驱动是**时序**
  激励升级,不承诺 bit-accurate 数值。
- 全部改进保持"改 YAML → 仿真出结果"的评估契约
  (`assert_evaluation_is_yaml_driven` 继续生效)。
