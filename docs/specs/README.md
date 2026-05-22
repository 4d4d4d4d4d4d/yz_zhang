# NPU 仿真平台核心 Spec 文档集

文档状态：**v1.0 Accepted**
最后更新：2026-05-22
Owners：架构组

## 目录

| 文档 | 范围 | 状态 |
|---|---|---|
| [SPEC-001 IModule 接口规范](./SPEC-001-IModule.md) | 所有 NPU 宏模块必须实现的统一抽象接口 | v1.0 Accepted |
| [SPEC-002 反压协议规范](./SPEC-002-Backpressure.md) | 模块间数据传输的反压协议、stall 上报、反压链追溯 | v1.0 Accepted |
| [SPEC-003 架构描述 DSL 规范](./SPEC-003-Architecture-DSL.md) | 平台架构描述的声明式 YAML DSL | v1.0 Accepted |
| [SPEC-004 Functional Simulation Interface](./SPEC-004-Functional-Simulation.md) | 数值精度评估管线的接口与契约 | v1.0 Accepted |
| [ADR-001 关键技术决策记录](./ADR-001-Key-Decisions.md) | 6 条核心决策 | Accepted |
| [ADR-002 模块身份判定标准](./ADR-002-Module-Identity.md) | 新 IModule 子类 vs. capability flag 化的判定规则 | Accepted |
| [Review v0.1](./review-v0.1.md) | v0.1 交叉一致性审查（历史） | 历史 |
| [Review v1.0](./review-v1.0.md) | v1.0 最终评审，决议 Approved | Accepted |

## 依赖关系

```
SPEC-001 (IModule) ──┬── SPEC-002 (Backpressure)
                     ├── SPEC-003 (DSL)
                     ├── SPEC-004 (Functional)
                     └── ADR-002 (Module Identity)

ADR-001 (Key Decisions) → 解释 SPEC-001/002/003 的设计取舍
ADR-002 (Module Identity) → 决定何时新写 IModule 子类
```

## v1.0 状态

### Review R6 修订（10/10 完成）

| # | 严重度 | 位置 | 状态 |
|---|---|---|---|
| 1 | 高 | SPEC-001 §3.1 / 3.1.1 | ✅ `module_type()` 命名规范 + 正则 |
| 2 | 高 | SPEC-002 §3.4 | ✅ 多生产者反压归因 |
| 3 | 高 | SPEC-002 §5.1 | ✅ Cross-Domain Transport (CDC) |
| 4 | 高 | SPEC-003 §6 | ✅ 列表 override `__append__` / `__remove__` |
| 5 | 中 | SPEC-002 §3.3.1 | ✅ Tracer Realtime vs Offline |
| 6 | 中 | SPEC-002 §7 | ✅ 7+3 条仿真不变量 |
| 7 | 中 | ADR-001.2 Constraints | ✅ 禁链式继承 + 生命周期 tag |
| 8 | 中 | SPEC-001 §3.3 | ✅ IClock 接口完整定义 |
| 9 | 低 | SPEC-003 §5 Phase 3.5 | ✅ 配置一致性 warning |
| 10 | 低 | SPEC-004 | ✅ Functional Simulation Interface |

### 开放问题决议（全部落地）

| ID | 决议 | 落地位置 |
|---|---|---|
| D1 | 模块身份判定 6 条硬规则 | ADR-002 |
| D2 | mapping_hints 仅消歧、窄 schema | SPEC-003 §3.4 + §4 |
| D3 | remove_modules 自动 prune（warn）+ add_connections 引用检查（error） | SPEC-003 §5 + §6 |

## 后续:Spec-Driven 实现

v1.0 已 Accepted,以此为契约启动实现。任何与 spec 不符的实现视为 bug,通过修订 spec 或修订代码来恢复一致(spec 修订需重新走 review)。

### 实现 Phase

| Phase | 范围 | 主要交付 |
|---|---|---|
| Phase 0 | 详细设计 | SystemC kernel + pybind11 binding 设计文档、IClock 实现细节、SPEC-004 NumericalEngine 实现路径 |
| Phase 1 | Python 骨架 | interfaces/ + core/ 抽象类、ModuleRegistry、NumericalModelRegistry、Dummy 模块、端到端最小链路测试 |
| Phase 2 | 模块库 | DAGC / DSB / MAC / VAU / AVP 等真实模块的 timing + functional 实现 |
| Phase 3 | 架构描述与 Elaborator | YAML 加载、Schema 校验、Override 合并、9 阶段 elaboration |
| Phase 4 | Mapper 与报告 | Rule-based Mapper、反压链追溯、不变量检查、报告生成 |
| Phase 5 | 校准与 Use Case | DAGC/DSB/MAC 校准记录、AGU-W 减半 use case 端到端跑通 |

### v1.1 候选项

- 随机算子 / stochastic rounding（SPEC-004 §9）
- 多 die / 多 chip functional sim 精度建模（SPEC-004 §9）
- MAC 劈裂按 ADR-002 重新判定身份
- 模块 spec 模板加 ADR-002 触发条件标注栏
- 实现层批量改名 `MTU_Fused → MtuFused`,同步 DSL 例
