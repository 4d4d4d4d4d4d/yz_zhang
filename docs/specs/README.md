# NPU 仿真平台核心 Spec 文档集

文档状态：Draft v0.2
最后更新：2026-05-22
Owners：架构组

## 目录

| 文档 | 范围 | 状态 |
|---|---|---|
| [SPEC-001 IModule 接口规范](./SPEC-001-IModule.md) | 所有 NPU 宏模块必须实现的统一抽象接口 | Draft v0.2 |
| [SPEC-002 反压协议规范](./SPEC-002-Backpressure.md) | 模块间数据传输的反压协议、stall 上报、反压链追溯 | Draft v0.2 |
| [SPEC-003 架构描述 DSL 规范](./SPEC-003-Architecture-DSL.md) | 平台架构描述的声明式 YAML DSL | Draft v0.2 |
| [ADR-001 关键技术决策记录](./ADR-001-Key-Decisions.md) | 6 条核心决策 | Accepted (v0.2 微调) |
| [ADR-002 模块身份判定标准](./ADR-002-Module-Identity.md) | 新 IModule 子类 vs. capability flag 化的判定规则 | Accepted |
| [整体 Review v0.1](./review-v0.1.md) | v0.1 交叉一致性审查 + 10 条 R6 修订建议 | 历史 |

## 依赖关系

```
SPEC-001 (IModule)
   ↑
   ├── SPEC-002 (Backpressure)  → 依赖 IModule.input_ports/output_ports 返回 ITransportPort
   │
   ├── SPEC-003 (Architecture DSL) → 依赖 IModule.module_type / config_schema / port_specs
   │
   ├── ADR-001 (Key Decisions) → 解释为什么这样设计
   │
   └── ADR-002 (Module Identity) → 决定何时新写 IModule 子类
```

## v0.2 变更摘要

### Review R6 修订（已完成）

| # | 严重度 | 位置 | 状态 |
|---|---|---|---|
| 1 | 高 | SPEC-001 §3.1 / 3.1.1 | ✅ 加 `module_type()` 命名规范 + 正则约束 |
| 2 | 高 | SPEC-002 §3.4 | ✅ 加多生产者反压归因（含 trace_multi_producer_contention API） |
| 3 | 高 | SPEC-002 §5.1 | ✅ 加 Cross-Domain Transport（CdcConnectionSpec、跨域延迟、跨域 stall 归因、Elaborator 校验） |
| 4 | 高 | SPEC-003 §6 | ✅ 列表 override `__append__` / `__remove__` 语义 |
| 5 | 中 | SPEC-002 §3.3.1 | ✅ Tracer Realtime vs Offline 双模式 |
| 6 | 中 | SPEC-002 §7 | ✅ 7 条必查不变量 + 3 条 warn 不变量 + InvariantReport API |
| 7 | 中 | ADR-001.2 Constraints | ✅ 禁止 variant 链式继承 + variant 生命周期标记 |
| 8 | 中 | SPEC-001 §3.3 | ✅ IClock 接口定义（时间查询 / 推进 / 跨域协作） |
| 9 | 低 | SPEC-003 §5 Phase 3.5 | ✅ Elaborator 配置一致性 warning |
| 10 | 低 | 新文档 | ⏳ SPEC-004 Functional Simulation（推迟到 Phase 2） |

### 开放问题决议（已落地）

| ID | 决议 | 落地位置 |
|---|---|---|
| D1 | 新 type vs flag 化判定标准 | 新文档 ADR-002 |
| D2 | `mapping_hints` 仅消歧、不赋能、窄 schema | SPEC-003 §3.4 + §4 |
| D3 | `remove_modules` 自动 prune 悬空连线（warn）；`add_connections` 引用无效模块时 error | SPEC-003 §5 + §6 |

## 后续计划

### v0.3 候选项

- [ ] SPEC-004 Functional Simulation Interface（数值精度评估管线）
- [ ] MAC 劈裂场景按 ADR-002 重新评估（v0.1 用 flag 写的 split_mode 可能要升级为新 type）
- [ ] 模块 spec 文档模板的"功能定位"章节增加 ADR-002 触发条件标注

### 实现路径

按 SPEC-001 § R7 的节奏：

1. Phase 0 detailed design（SystemC kernel + pybind11 binding）
2. Phase 1 实现骨架（ModuleRegistry + dummy module + send/stall 链路）
3. Phase 1 起 3 个模块 spec：DAGC / DSB / MAC（包含校准记录）
4. 第一个 Use Case spec：AGU-W 带宽减半评估
