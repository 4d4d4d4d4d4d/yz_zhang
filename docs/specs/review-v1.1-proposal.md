# v1.1 Spec 增订评审请求(review-v1.1-proposal)

文档状态：**Awaiting Review**
提交日期:2026-06-04
提交人:实现组(Claude)
范围:回应用户 2026-06-04 提出的硬件变化代价评估清单

## 1. 提交内容

| 文档 | 性质 | 大小 |
|---|---|---|
| `SPEC-001-v1.1-amendment.md` | 增订 v1.0(area + clock_domain) | ~3 KB |
| `SPEC-003-v1.1-amendment.md` | 增订 v1.0(`__relocate__`, `clock_domains`, `physical_dimension`) | ~3 KB |
| `SPEC-005-v1.1-amendment.md` | 增订 v0.1(area 系数 + UNPACK capability) | ~2 KB |
| `SPEC-007-Control-Transfer-Modules.md` | **新增**(MCU/OGU/TAU/DMA/MTU/AGU) | ~8 KB |

## 2. 评审通过标准 / 评审点

请按 SPEC v1.0 R1–R6 同样的方法 review,关注:

1. **契约不破坏**(critical):SPEC-001 v1.1 §3.2.5 是否纯增量?
   v1.0 已实现的 5 个模块(DAGC/DSB/MAC/VAU/AVP)能 deferred 实现
   `estimate_area()`(只 warn 不 fail)——是否同意这个渐进策略?
2. **ADR-002 应用是否到位**:SPEC-007 §6.5 给了 MTU 走"新子类"而非
   capability flag 的理由,SPEC-005 v1.1 §2.1 给了 UNPACK 走 capability
   flag 的理由——这两个判定是否合理?
3. **测量口径**:SPEC-007 §2.5(节省几个 MCU)和 §6.3.1(MTU overlap)
   的形式化定义是否能客观判定"通过/未通过",还是留了主观空间?
4. **calibration 兜底**:area 系数全部标 `[calibration knob]`,Phase 5
   再校准——这是否会让 v1.1 评估结果"不可信"?可接受程度。
5. **v1.0 不变量**:SPEC-002 §7 既有的 7+3 不变量本增订未触碰;新增
   SPEC-001 v1.1 §7.x area 守恒 invariant 是否需要写进 SPEC-002?

## 3. 实施路线(评审通过后)

1. 实现 SPEC-001 v1.1(AreaModel + estimate_area + clock_domain)
2. 实现 SPEC-003 v1.1(`__relocate__` + `clock_domains` + `physical_dimension`)
3. 给现存 5 个模块补 `estimate_area()`(SPEC-005 v1.1 §1 系数 + UNPACK capability)
4. 实现 SPEC-007 全部 6 个模块(MCU/OGU/TAU/DMA/MTU/AGU)
5. 写整套 use-case 测试(本提案各 §9 / §T / §5 已列出清单)

按用户偏好的"补 spec → 检视 → 开发 → 测试"流程,**步骤 1 不开始
直到本提案 Accepted**。

## 4. 不在本提案范围

- DVFS / thermal(留 v1.2)
- 多 floorplan 坐标(留 v1.2)
- OGU hit rate(留 SPEC-007 §8.1)
- MTU 多通道(留 SPEC-007 §8.2)
- 精度对账契约(留 SPEC-006 §8 candidate)
