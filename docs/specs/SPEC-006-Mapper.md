# SPEC-006 Rule-based Mapper 规范（Phase 4）

文档状态：**v0.1 Draft（implementation spec）**
最后更新：2026-06-01
Owners：架构组
派生自：SPEC-001 §3.2（Mapper-facing IModule API:`can_execute` /
`estimate_latency` / `estimate_energy`）、SPEC-003（elaborated
IArchitecture）、SPEC-004（functional 与 timing 一致性）

## 0. 范围

本规范定义 Phase 4 **Rule-based Mapper** 的接口与算法契约。Mapper 的职责是
**把算子图(op graph)映射到已 elaborate 的架构实例上**——对每个 IOperation,
在架构的模块实例集合中选出一个 `module_id` 来执行,并附带可解释的延迟/能耗
估算。

本规范只覆盖"规则化(rule-based)"映射器,即不做搜索/启发式优化,仅基于
SPEC-001 §3.2 暴露的纯函数估算做单步贪心选择。代价模型驱动的映射器(cost
model / ILP / RL)留待 v1.1。

## 1. 输入与输出

- **输入 A · 算子图**:`Sequence[IOperation]`(SPEC-001 §3.2)。v1.0 视作
  **有序扁平列表**,无显式依赖边——每个 op 独立映射,选择不互相影响。未来
  版本(v1.1+)可升级为 DAG。
- **输入 B · 架构**:已经 `ArchitectureElaborator.elaborate()` 之后的
  `IArchitecture`(SPEC-003 §4-5),提供 `arch.modules: dict[str, IModule]`。
  模块需已 `configure()`,以便 `active_capabilities()` / `can_execute()` /
  `estimate_latency()` / `estimate_energy()` 返回稳定值。
- **输出 · MappingPlan**:由若干 `MappingDecision` 组成的不可变记录,
  携带聚合指标(总延迟、总动态能耗等),以及可读的 `summary_text`。

## 2. IMapper 接口

```python
class IMapper(ABC):
    @abstractmethod
    def map(
        self,
        operations: Sequence[IOperation],
        architecture: IArchitecture,
    ) -> MappingPlan: ...
```

### 2.1 数据类(全部 frozen dataclass)

- `MappingDecision`:`op_index:int`、`op_type:str`、
  `module_id:str`、`latency:LatencyEstimate`、`energy:EnergyEstimate`、
  `alternatives:tuple[str,...]`(同样合规但被规则击败的候选 ids,按规则后顺序)、
  `rationale:str`(为何选中此模块的一句话)。
- `MappingPlan`:`decisions:tuple[MappingDecision,...]`、
  `total_typical_cycles:int`(所有 decision 的
  `latency.typical_cycles` 之和)、`total_dynamic_pj:float`、
  `unmapped:tuple[int,...]`(无候选的 op_index 列表;默认严格模式下为空)、
  `summary_text:str`。

### 2.2 纯函数与确定性

- `map()` 必须是**纯函数**:同一(operations, architecture)多次调用产生
  **逐字段相等**的 MappingPlan。
- Mapper 自身**不修改**架构或算子。

## 3. RuleBasedMapper 算法

### 3.1 候选筛选(per-op)

候选集 `C(op) = { mid | mid, mod ∈ arch.modules, mod.can_execute(op) }`。
`can_execute` 的具体定义见 SPEC-001 §3.1:**所有** `op.required_capabilities`
都在模块 `active_capabilities()` 中。

### 3.2 排序键

候选按以下复合键升序排序(越小越优):

1. `mod.estimate_latency(op).typical_cycles`
2. `mod.estimate_energy(op).dynamic_pj`
3. `module_id`(字典序;保证 tie-break 仍然**确定**)

得分相等时,排序仍由 §3.2.3 字典序唯一决定——Mapper 输出**不依赖 dict
插入顺序**。

### 3.3 选择

选择已排序候选集的**第一项**为 `module_id`,其余按排序顺序记为
`alternatives`。rationale 形如:`"chose <id>: typical 12 cyc, 8.4 pJ
(vs alt {...})"`。

### 3.4 无候选(unmapped)

构造器接受 `strict: bool`(默认 `True`):

- `strict=True`:遇到 `C(op) == ∅` 抛出 `NoMappingError`,消息包含
  `op_index`、`op_type`、`required_capabilities`、当前架构中各模块的
  `active_capabilities()`。
- `strict=False`:跳过该 op,把 `op_index` 加入 `MappingPlan.unmapped`,
  继续后续 op;聚合指标仅按已映射的 op 求和。

### 3.5 聚合

`total_typical_cycles = Σ decision.latency.typical_cycles`、
`total_dynamic_pj = Σ decision.energy.dynamic_pj`。**注意**:这只是
**理想流水线下界**(每个 op 独占其模块),不反映 SPEC-002 的反压实际耗时,
也不反映多 op 共用模块的串行化——这些属于运行时(SPEC-002 §6)而非
映射阶段。

## 4. 错误

- `NoMappingError(MappingError)`:`strict=True` 下无候选时。
- `MappingError`:基类,留给 v1.1 cost-model mapper 的更多错误使用。

## 5. 报告 / 摘要

`MappingPlan.summary_text` 必须包含:

- 每条 decision 的一行(op_index, op_type → module_id, typical_cycles, pJ)
- 聚合行(total typical cycles / total dynamic pJ / unmapped count)

格式由实现决定,但内容必须**机器可解析且人类可读**,以便后续供
`reporting.markdown` 渲染(v1.1 候选)。

## 6. 实现期一致性(与已有 spec 的对接)

- §3.2 排序键依赖 `LatencyEstimate.typical_cycles` 与
  `EnergyEstimate.dynamic_pj`(SPEC-001 §3.2 已定义)——任何 IModule 实现
  必须保证两者在 op 不变时**多次调用相等**(SPEC-001 §3.2 纯函数约束)。
  否则 Mapper 的确定性失效——视为 IModule 实现 bug。
- 若 IOperation 的 `required_capabilities` 包含 `active_capabilities` 集合
  中**不存在**的能力名,`can_execute` 必须返回 False(SPEC-001 §3.1)。

## 7. 测试要求

- **§7.1 接口契约**:`IMapper.map` 不修改入参;同输入产出逐字段相等 plan。
- **§7.2 候选筛选**:仅 `can_execute(op)` 为 True 的模块入选;无候选时
  `strict=True` 抛 `NoMappingError`,`strict=False` 加入 `unmapped`。
- **§7.3 排序与 tie-break**:同 latency 同 energy → 按 module_id 字典序;
  打乱架构 dict 顺序后结果不变。
- **§7.4 alternatives 完整性**:被选中的模块不出现在 alternatives;
  alternatives 顺序与排序键一致。
- **§7.5 聚合指标**:`total_typical_cycles` 与 `total_dynamic_pj`
  =Σ 各 decision 对应字段。
- **§7.6 端到端**:用 SPEC-005 的真实模块(MAC/VAU/AVP 等)对一小串
  op 跑通映射,断言能跑出非空 plan、模块归属合理(如 matmul → MAC)。

## 8. v1.1 候选

- 算子图升级为 DAG(支持 dependency edges、partial pipeline mapping)。
- Cost-model mapper:加入 throughput、area pressure、共享模块串行化代价。
  ✅ **共享模块串行化已落地**:`MappingPlan` 除 `total_typical_cycles`
  (op-serial 求和)外,新增 `bottleneck_cycles` / `bottleneck_module` /
  `per_module_cycles` —— 路由到同一模块的算子在该模块串行,busiest 模块的
  串行总量是比"求和"更紧的吞吐下界,且建模了跨模块 overlap。实测 MLP
  (3 matmul→MAC=315,3 relu→VAU=48):bottleneck 315 < op-serial 363,
  因 relu 与 matmul 在不同模块可并行(`test_bottleneck_estimate.py`)。
  `reconcile` 同时报告两个估算 vs 实测。v1.1 进一步:throughput / area
  pressure 权重。
- 多模块算子(一个 op 跨多个模块)、空间映射(systolic tile sharding)。
- ✅ `reporting.markdown` 增加 MappingPlan 渲染(`render_mapping_report`,
  CLI `estimate` 子命令)。
- mapping_hints(SPEC-003 §3.4)消歧:用户指定首选 module_id 时优先采纳。
- **估算 vs 实测对账(精度)** — ✅ **一级对账已落地**:
  `npu_sim.evaluation.reconcile(ops, arch, measured_drain_ps, clock_period_ps)`
  把 Mapper 静态估的 `total_typical_cycles` 与仿真实测 drain(cycles)join,
  产出 `ReconcileReport`(estimate / measured / ratio / abs_error)。实测
  attention trace:静态估 665 cycles(op-serial,无 overlap/反压),实测 4232,
  ratio 6.36×;`test_estimate_vs_measured.py` 断言"静态估是实测的下界
  (ratio ≥ 1)"。
  同时修复了一个 Mapper bug:候选过滤原用各模块松散实现的 `can_execute()`
  (激励/基础设施模块无脑返回 True),导致算子被误映射到 TraceProducer;
  现改用 SPEC-001 §3.1 权威判据 `required_capabilities ⊆ active_capabilities`。
  ✅ **逐算子对账已落地**:`reconcile_per_op(ops, arch, arrivals, period)` +
  `sink_op_arrivals(arch, sink_id)` 利用 SPEC-012 trace token 携带的
  `op_index`(穿过整条通路被各模块 `{**metadata}` 保留)在 sink 还原每个
  算子的到达拍,把 Mapper 逐 op 估算与 sink 到达间隔 join。实测 attention:
  matmul 估 105 拍 / 稳态实测 512 拍(ratio 4.88×),softmax 估 35 拍 / 实测
  512 拍(14.6×)—— 揭示核心 gap:**pipeline 稳态吞吐由最慢 stage 决定,
  不是各 op 独立 latency**,`test_per_op_reconcile.py` 断言稳态到达间隔一致。
  v1.1 进一步:把这个观察规范成 cost-model(§8 顶部第 2 条),让 Mapper 估算
  考虑 pipeline throughput 而非纯 op-serial。
