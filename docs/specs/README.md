# NPU 仿真平台核心 Spec 文档集

文档状态：Draft v0.1
最后更新：2026-05-22
Owners：架构组

## 目录

| 文档 | 范围 | 状态 |
|---|---|---|
| [SPEC-001 IModule 接口规范](./SPEC-001-IModule.md) | 所有 NPU 宏模块必须实现的统一抽象接口 | Draft v0.1 |
| [SPEC-002 反压协议规范](./SPEC-002-Backpressure.md) | 模块间数据传输的反压协议、stall 上报、反压链追溯 | Draft v0.1 |
| [SPEC-003 架构描述 DSL 规范](./SPEC-003-Architecture-DSL.md) | 平台架构描述的声明式 YAML DSL | Draft v0.1 |
| [ADR-001 关键技术决策记录](./ADR-001-Key-Decisions.md) | 6 条核心决策（仿真内核 / DSL / Mapper / 反压 / 归因 / 版本锁定） | Accepted |
| [整体 Review v0.1](./review-v0.1.md) | 交叉一致性审查 + 10 条 R6 修订建议 + R7 行动计划 | Draft v0.1 |

## 依赖关系

```
SPEC-001 (IModule)
   ↑
   ├── SPEC-002 (Backpressure)  → 依赖 IModule.input_ports/output_ports 返回 ITransportPort
   │
   ├── SPEC-003 (Architecture DSL) → 依赖 IModule.module_type / config_schema / port_specs
   │
   └── ADR-001 (Key Decisions) → 解释为什么这样设计
```

## 后续计划

### 待修订（v0.2 目标，来自 Review R6）

- [ ] R6#1（高）：SPEC-001 §3.1 增加 `module_type()` 命名规范
- [ ] R6#2（高）：SPEC-002 §3.3 增加"多生产者反压归因"小节
- [ ] R6#3（高）：SPEC-002 增加 Cross-Domain Transport (CDC) 小节
- [ ] R6#4（高）：SPEC-003 §6 列表 override 语义 + `__append__`/`__remove__`
- [ ] R6#5（中）：SPEC-002 §3.3 明确 BackpressureTracer 实时 vs 离线模式
- [ ] R6#6（中）：SPEC-002 增加 simulation invariant check
- [ ] R6#7（中）：ADR-001.2 补充禁止 variant 链式继承
- [ ] R6#8（中）：SPEC-001 补充 IClock 接口细节
- [ ] R6#9（低）：SPEC-003 §5 Elaborator 增加配置一致性 warning
- [ ] R6#10（低）：新文档 SPEC-004 Functional Simulation Interface（Phase 2）

### 待解决的开放问题（Review 未直接回应）

1. **MTU_Fused 何时新写 IModule 子类 vs. 只在 DSL 层做参数化**
   - SPEC-003 §3.6 用了 `type: MTU_Fused`，意味着新写一个 IModule 子类
   - 但理论上也可在 MTU 上加 capability flag `dma_integrated` 实现
   - 需要明确"新 type" 的判定标准（端口拓扑变 / capability 集合根本变 / 内部状态机变）

2. **`mapping_hints` 自由格式与"无外部知识"原则的张力**
   - SPEC-001 设计原则：模块自描述，不依赖外部知识
   - SPEC-003 `mapping_hints` 是 Mapper 与架构 variant 的契约层，schema 是 free-form
   - 风险：variant 通过 hints 隐式注入 mapping 知识，模块行为不再完全自描述
   - 需要明确 hints 的边界：只允许指定"使用哪个模块"还是可以指定"使用哪个 capability"

3. **override 引用已 `remove_modules` 模块端口的处理**
   - SPEC-003 §5 Elaborator Phase 3 语义校验是否覆盖此场景
   - 建议：在 `_apply_overrides` 后立即扫描 connections，剔除引用已删模块的连线 + 报 warning，而不是延迟到 Phase 3 才报 PortNotFoundError

这三点建议在 v0.2 修订前先讨论清楚，避免修订完又要返工。
