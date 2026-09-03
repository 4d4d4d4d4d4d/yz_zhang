# 物理模型验证:绝对数字是否可信(vs 公开参考)

文档状态:**验证报告 v1.0** · 最后更新:2026-08-25
关联:`npu_sim/physical.py`、SPEC-013、`tests/unit/test_physical_validation.py`

## 目的

回答"这些绝对 PPA 数字到底靠不靠谱"的最硬证据:把 `physical.py` 的输出与
**公开文献/硅数据**(45nm)对照。全部做**区间**校核(不是精确值)——模型是
±30% 解析估计,关键是它落在真实硅的正确量级里,而不是拍脑袋。

## 校核结果(全部通过,`test_physical_validation.py` 锁定)

| 量 | 模型输出 | 公开参考(45nm) | 结论 |
|---|---|---|---|
| 每 MAC 能量(int8) | 1.1 pJ | Horowitz ISSCC'14:0.2(mult)+0.9(fp32 add) | ✅ 直接引用 |
| SRAM 读能量 | 1.25 pJ/byte | Horowitz:32b SRAM read ~5 pJ | ✅ |
| SRAM 密度 | 2926 µm²/KB | foundry 45nm 6T macro ~2.5–4.0k µm²/KB | ✅ 区间内 |
| int8 MAC PE 门数 | 664 门 | 教科书 int8 MAC ~500–1000 门 | ✅ |
| 单 MAC 面积 | 531 µm²/MAC | 45nm MAC cell ~500–1000 µm² | ✅ |
| 1024-MAC 阵列 | 0.54 mm² | ~0.5–1.0 mm² @45nm | ✅ |
| FP32 乘法器门数 | 3496 门 | 教科书 FP32 mult ~3–5k 门 | ✅ |
| eDRAM vs SRAM 密度比 | 3.7× | eDRAM(1T1C)比 6T SRAM 密 ~3–5× | ✅ |

**结论**:所有物理化模块的绝对面积/能量都落在公开参考区间内。这是"真实模拟"
的硬证据——数字不是经验拍的,而是文献引用 + 物理正确形式,且经外部锚点校核。

## 边界(诚实声明)

- **参考节点 45nm**;跨节点缩放留 Phase 5(用公开 scaling 因子,不臆造)。
- **±30% 解析带**:门计数面积是解析估计;Phase 5 用综合/PDK 替换单位成本收窄。
- **控制面 FSM(~10% 面积)未验证**:其门数需 RTL 综合,仍 `[calibration
  knob]`(SPEC-013 §5.1),不在本验证范围。
- 用 `python -m npu_sim fidelity <arch>` 查任意芯片的物理化占比(v4 全栈 90.7%)。
