# ADR-002：模块身份判定标准

文档状态：Accepted
作者：架构组
日期：2026-05-22
依赖：SPEC-001 IModule 接口规范、SPEC-003 架构描述 DSL 规范
关联讨论：v0.1 Review 开放问题 D1

## Status

Accepted

## Context

当架构演进出现"模块融合 / 拆分 / 增能"时，存在两条实现路径，选择标准不明会带来长期维护负担：

- **路径 A：新写一个 IModule 子类**（新 `module_type()`，新代码，新 capability 清单，新 port specs）
- **路径 B：在原模块上加 capability flag**（DSL 改 config，模块内部条件化激活）

举例：DMA + TAU 融合为 MTU_Fused
- 路径 A：注册新 type `MtuFused`，独立的 IModule 子类
- 路径 B：在 `MTU` 上加 `dma_integrated: bool` 与 `bitmap_extract: bool` capability flag

两条路代价完全不同：
- 路径 A：代码量大，但接口干净、estimate 模型可独立校准、port 拓扑清晰
- 路径 B：DSL 改动小，但模块会变成"什么都能干"的瑞士军刀，port 数量随 flag 组合爆炸，estimate 分支多

没有判定标准时，每次决策都要重新争论，团队对"模块"的理解会发散。

## Decision

按以下硬规则判定。**任一条触发即必须走新 type**：

| # | 触发条件 | 路线 | 理由 |
|---|---|---|---|
| 1 | 端口拓扑变化（新增 / 删除 port，或同名 port 宽度变） | **新 type** | port_specs() 是模块身份的一部分，变了就是新模块 |
| 2 | 内部状态机本质改变（新增独立 pipeline / 仲裁器 / FIFO 拓扑变） | **新 type** | snapshot_state() 结构变，影响 debug 与可视化兼容性 |
| 3 | 估算模型差异 > 30%（同一 op 在新旧实现下 estimate_latency 差异） | **新 type** | 共享 estimate 代码不能正确表达两种实现 |
| 4 | capability 集合是父集合的纯子集 / 超集 | **flag 化** | 用 `support_xxx: bool` 表达即可 |
| 5 | 仅参数微调（throughput / depth / 单位时间多少元素） | **flag 化** | config 数值即可表达 |
| 6 | 跨子系统融合（如计算阵列 + 搬运单元） | **新 type** | 跨越原有职责边界，原模块的 spec 文档已无法描述 |

### 决策流程

```
是否触发条件 1/2/3/6？
├─ 是 → 新 IModule 子类，新 module_type()，新 spec 文档
└─ 否 → 是否仅触发 4/5？
        ├─ 是 → 加 capability flag / 调 config 即可
        └─ 否（混合）→ 默认走新 type，作为新的"显式建模"
```

### 例子

| 场景 | 触发条件 | 决定 |
|---|---|---|
| DMA + TAU 融合为 MtuFused | 1（吞掉 TAU 的 bitmap_extract 端口）+ 2（共享 buffer 仲裁器）+ 6 | **新 type** |
| VAU 增加 lut_exp | 4（新增 capability，原集合的超集） | **flag 化** |
| AGU-W throughput 1 → 0.5 | 5（参数微调） | **flag 化** |
| MAC 单阵列 → 4×64×64 劈裂 | 2（新增 reduction network） | **新 type**（但 SPEC-003 §3.5 当前写法是 flag，需要在 v0.3 重新评估）|
| DAGC 新增 INT4 reorder | 4 | **flag 化** |
| 把 VAU 拆成"算术 VAU"+"reduce VAU" | 1（port 数变） + 2（独立 pipeline） | **新 type** |

## Rationale

### 为什么把"端口拓扑变化"作为最强触发条件？

- SPEC-001 `port_specs()` 是 IModule 类级元信息，模块身份的核心
- 端口变化意味着上下游连线变化，DSL `connections` 必须改动
- 上下游模块需要重新校验兼容性 —— 这本来就是新模块该走的流程

### 为什么不让 flag 路线无限扩展？

flag 路线的危险在于**隐性复杂度**：
- 模块代码出现大量 `if self._dma_integrated: ... else: ...`
- estimate_latency 分支爆炸，校准困难
- snapshot_state 的字段集合不再稳定
- spec 文档要描述"在这些 flag 组合下行为如何"，组合数 2^n

新 type 把复杂度外显到 ModuleRegistry 层面，每个 type 独立维护、独立校准、独立写 spec。

### 为什么 MAC 劈裂临时归为 flag？

SPEC-003 §3.5 现状是 `split_mode: "4x64x64"` 作为 config，触发条件 2 说应走新 type。这是 v0.1 残留，因为劈裂场景需要先做实现 spike 才能确定 reduction network 的复杂度。Phase 1 实现时重新评估：若 reduction network 真的引入独立 pipeline 阶段，则升级为新 type `MatVecArraySplit4x64x64` 或抽象为 `SplitMatVecArray`。

## Consequences

正面：

- 每次"是否新 type"决策有客观依据，不靠经验拍板
- 模块身份与代码身份对齐，跨团队协作时引用准确
- 估算模型与 spec 文档边界清晰

负面：

- 新 type 比 flag 化工作量大（写代码、写 spec、跑校准）
- 短期实验更慢

缓解措施：

- 提供 `IModule` 基类的模板生成器（脚手架），新 type 起步成本降低
- "实验阶段"允许临时走 flag，但 DSL `metadata.tags` 必须标 `experimental`，6 周内必须 review 是否提升为新 type

## 与现有文档的同步

需要在以下位置补充对本 ADR 的引用：

- [x] SPEC-001 头部依赖列表已添加 ADR-002
- [x] SPEC-003 §3.6 (MTU_Fused 例) 决策依据可引用本 ADR
- [ ] 各模块 spec 文档模板的"功能定位"小节，注明该模块是否触发了本 ADR 的条件 1/2/3/6
