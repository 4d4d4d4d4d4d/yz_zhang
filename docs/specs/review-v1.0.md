# v1.0 评审报告

文档状态：Approved
作者：架构组(self-review)
日期：2026-05-22
范围：SPEC-001 / SPEC-002 / SPEC-003 / SPEC-004 / ADR-001 / ADR-002

## 1. 评审目的

v0.2 完成了 v0.1 review R6 修订及 D1/D2/D3 决议。v1.0 在此基础上补齐 SPEC-004 Functional Simulation Interface(原 R6#10,v0.2 推迟项),完成完整文档集。本次评审目标:

1. 确认 SPEC-004 自身一致、可执行、与现有 SPEC 无冲突
2. 完整文档集做最后一次交叉一致性扫描
3. 决定是否 promote 到 v1.0 (Accepted)

## 2. SPEC-004 自检

### 2.1 内部一致

| 检查项 | 结果 |
|---|---|
| `INumericalModel.for_module_type()` 与 `IModule.module_type()` 命名空间一致(均 PascalCase 且需通过 ADR-002 命名规范) | ✅ |
| `supported_capabilities` 必须是 `IModule.declared_capabilities` 子集 | ✅ §4.1 表格 + §7 测试 enforce |
| `configure(config)` 用相同 schema 校验 | ✅ §4.1 |
| Fidelity 多级别 (golden / bit_accurate / fast) 注册键含 fidelity | ✅ §3.3 NumericalModelRegistry |
| 优雅降级:`fast` 不存在时回退到 `golden` | ✅ §3.3 create() |
| 纯函数性:reset 间无关联、不 mutate inputs | ✅ §3.1 约束 + §7 测试 |

### 2.2 与 timing sim 的边界

明确不共用列表(§4.2):bind_services / input_ports / output_ports / estimate_* / snapshot_state / pipeline 内部对象。这与 SPEC-002 ITransportPort 和 SPEC-001 IClock 形成清晰边界。

明确共用列表(§4.1):module_type / version / config_schema / declared_capabilities / IOperation。这五项是模块"身份"层,与 ADR-002 模块身份定义自洽 —— 满足 ADR-002 触发条件 1/2/3/6 的变化会同时影响 timing 和 functional 两条线。

### 2.3 工作流强约束

§8 表格中"每次架构 variant 评估必须同时输出 functional + timing report,缺一标 INCOMPLETE" —— 这是平台契约级强约束,与 SPEC-002 §7 INV-* 不变量的 INVALID 机制并列,共同保证报告不被滥用。

## 3. 完整文档集交叉一致性

### 3.1 SPEC-004 与既有 SPEC

| 交叉点 | 检查 | 结论 |
|---|---|---|
| SPEC-001 §3.1.1 命名规范 | SPEC-004 引用 IModule.module_type 作为 functional model 配对键,继承同套规范 | ✅ |
| SPEC-001 §3.3 IClock | SPEC-004 明确不用 IClock,§4.2 列入"不共用" | ✅ |
| SPEC-002 ITransportPort | SPEC-004 明确不用 ITransportPort,无反压概念 | ✅ |
| SPEC-002 §7 不变量 | SPEC-004 §8 提出 functional + timing 缺一 INCOMPLETE,与 timing INVALID 互补 | ✅ |
| SPEC-003 DSL | SPEC-004 §6 示例直接复用 DSL variant,Engine 用同一 elaborate 结果 | ✅ |
| SPEC-003 §3.4 mapping_hints | SPEC-004 未涉及 mapping,functional sim 不做 op-to-module 路由(数值模型按 DAG 顺序执行),无冲突 | ✅ |
| ADR-001 SystemC | SPEC-004 不依赖 SystemC,纯 Python/NumPy,与 ADR-001 不冲突(ADR-001 仅约束 timing sim 内核) | ✅ |
| ADR-002 模块身份 | SPEC-004 §4.3 明确禁止 functional/timing 共享代码,与 ADR-002"代码身份与模块身份对齐"一致 | ✅ |

### 3.2 完整文档集结构

```
SPEC-001 (IModule) ──────┬── 命名规范 ──┬── SPEC-003 引用
                         │              └── SPEC-004 引用
                         │
                         ├── IClock ──── SPEC-002 §5.1 CDC 引用
                         │
                         ├── capability ─┬── SPEC-002 stall 上报含 CAPABILITY_MISSING
                         │               ├── SPEC-003 config_schema 校验
                         │               └── SPEC-004 supported_capabilities 子集约束
                         │
                         └── module_type ─ ADR-002 身份判定规则

SPEC-002 (Backpressure) ─┬── ITransportPort ── SPEC-003 connections 实例化
                         ├── StallChain ────── timing 报告主输出
                         ├── §5.1 CDC ──────── SPEC-003 多时钟域支持
                         └── §7 不变量 ─────── SPEC-004 §8 协同约束

SPEC-003 (DSL) ──────────┬── modules.type ──── SPEC-001 module_type 引用
                         ├── connections ───── SPEC-002 ITransportPort 实例化
                         ├── clock_domains ─── SPEC-001 IClock 实例化
                         ├── mapping_hints ─── 仅消歧(D2 约束)
                         └── overrides ─────── ADR-001.2 无链式继承

SPEC-004 (Functional) ───┬── INumericalModel ─ 与 IModule 配对(共用身份)
                         ├── NumericalEngine ─ 用 IArchitecture(SPEC-003 输出)
                         ├── Reference + Cmp ─ 平台特有,无外部依赖
                         └── §8 协同约束 ──── 必须与 timing report 同时产出

ADR-001 ─ 6 条决策(SystemC / YAML / Rule-based Mapper / Blocking Transport / caused_by / 版本锁)
ADR-002 ─ 模块身份判定 6 条触发规则
```

### 3.3 残余不一致项

扫描结果:

1. **DSL 现有 yaml 示例命名违反 ADR-002 (实施前已知项)**
   - SPEC-003 §3.6 用 `type: MTU_Fused`,带下划线
   - SPEC-001 §3.1.1 末尾注已标明:实现期统一改为 `MtuFused`
   - 不阻塞 v1.0 promote,实现阶段批量替换

2. **MAC 劈裂场景的身份归属未决**
   - SPEC-003 §3.5 当前 `split_mode` 是 config flag
   - ADR-002 触发条件 2 (新增 reduction network = 新内部状态机) 暗示应为新 type
   - ADR-002 末尾已标注"Phase 1 实现 spike 后再定"
   - 不阻塞 v1.0 promote

3. **SPEC-004 随机性 / 并发 / 分布式留到 v1.1**
   - §9 明确声明
   - 不属于 v1.0 范围,不阻塞

### 3.4 风险复查

v0.1 review R3 列出的 3 个风险:

| 风险 | v1.0 状态 |
|---|---|
| R3.1 SystemC 性能不达标 | 未消除,留到 Phase 1 micro-benchmark 验证 |
| R3.2 base+overrides 演变为补丁堆 | 通过 ADR-001.2 v0.2 增补的"禁链式继承 + 生命周期 tag"缓解 |
| R3.3 模块绕过 caused_by | 通过 SPEC-002 §3.5 record_stall 合法性表 + CI lint 缓解 |

R3.1 是实现期才能验证的风险,文档层面已尽职。

## 4. 评审决议

**通过,promote 到 v1.0 (Accepted)。**

理由:
- 全部 6 份文档(SPEC-001/002/003/004 + ADR-001/002)交叉一致
- v0.1 review R6 全部 10 项已处理(SPEC-004 v1.0 完成,R6#10 关闭)
- 3 个开放问题(D1/D2/D3) 已落地
- 残余项均为"实现期解决"或"v1.1 范围",不影响 spec-driven 实现启动

后续:进入 spec-driven 实现阶段,以 v1.0 spec 集为依据写第一版骨架代码。任何与 spec 不符的实现都视为 bug。

## 5. v1.1 候选

- 随机算子 / stochastic rounding (SPEC-004 §9)
- 多 die / 多 chip functional sim 通信精度建模 (SPEC-004 §9)
- MAC 劈裂场景按 ADR-002 重新判定身份 (SPEC-003 §3.5 留项)
- 模块 spec 文档模板加 ADR-002 触发条件标注栏
- DSL 中 `MTU_Fused` 重命名为 `MtuFused`,所有 example yaml 同步

---

**评审人**:架构组(self-review)
**日期**:2026-05-22
**结论**:Approved → v1.0
