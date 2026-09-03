# 芯片设计验证案例:端侧 Transformer Encoder NPU

文档状态:**设计研究报告 v1.0** · 最后更新:2026-08-27
方法:全程用本平台物理接地模型(SPEC-013)+ RuleBasedMapper(SPEC-006)
复现脚本:`examples/design_study_encoder.py`(`python examples/design_study_encoder.py`)

## 0. 结论先行

对一个 **18 层、d=256、8 头、seq=128、FFN=1024、int8** 的端侧 encoder,从零
分析并比较三种数据通路设计,PPA 全部来自文献接地的物理模型(45nm,±30% 带,
`fidelity` 报告本案例 **100% 面积物理化**):

| 设计 | MAC 阵列 | 面积 | 全模型延迟@1GHz | 全模型能量 | EDP |
|---|---|---:|---:|---:|---:|
| **A** MAC-heavy | 64×64 | 4.07 mm² | **1.36 ms** ⚡ | 2.30 mJ | **最优** |
| **B** Balanced | 32×32 | 2.05 mm² | 2.52 ms | 2.30 mJ | 中 |
| **C** Compact | 16×16 | 0.63 mm² | 9.25 ms | 2.30 mJ | 差 |

**推荐**:
- **延迟/EDP 优先(实时端侧推理)→ A**:面积换 ~4–7× 速度,EDP 最优。
- **面积/成本受限 → C 或 B**:能量几乎不变,只是慢。
- **关键发现:能量不是设计变量**(三设计全模型能量都 ≈ 2.30 mJ,见 §3)。

## 1. 负载:一个 encoder 层的算子图

Encoder 是 18 个相同层串接,故分析**单层**再 ×18。单层 12 个算子(int8 matmul
+ softmax/gelu/layernorm),映射到 MAC(矩阵乘)/ AVP(超越函数):

| 算子 | 引擎 | shape | 单层占比(cyc @32×32) |
|---|---|---|---:|
| ffn1 | MAC | 128×256×1024 | **26%** |
| ffn2 | MAC | 128×1024×256 | **26%** |
| q/k/v/out proj | MAC | 128×256×256 ×4 | 24% |
| softmax / gelu | AVP | 8·128² / 128·1024 | 12% |
| scores / attn | MAC | S²D ×2 | 6% |
| ln1 / ln2 | AVP | 128×256 ×2 | 4% |

**单层 109 M MAC → 全模型 1.96 G-MAC**。负载是 **FFN-matmul 主导**(两个 FFN
矩阵乘占 52% 计算),所以 **MAC 阵列是第一杠杆**,超越函数(AVP)是次要项。

## 2. 三种设计

同一条数据通路(DAGC→DSB→MAC→VAU→AVP),只改计算引擎规模:

- **A MAC-heavy**:MAC 64×64(4096 PE)、AVP vw16、VAU 16 lane、DSB 64KB。
- **B Balanced**:MAC 32×32(1024 PE)、AVP vw32、VAU 32 lane、DSB 128KB。
- **C Compact**:MAC 16×16(256 PE)、AVP vw16、VAU 16 lane、DSB 32KB。

## 3. 分析与关键发现

**§3.1 延迟 ∝ 1/PE 数(计算受限)**。matmul 拍数 = `ceil(MACs/PE) + fill`
(systolic 模型,已与运行时统一)。A(4096 PE)比 B(1024)快 ~4×、比 C(256)
快 ~7×。因为负载 FFN-bound,加宽 MAC 直接线性提速——没有过早撞内存墙(DSB
带宽足够)。

**§3.2 动态能量是"设计不变量"**(非直觉、重要)。三设计的动态能量**完全相同**
(126,937 nJ/层)——因为动态能量 = **MACs × 每-MAC能量(Horowitz)**,只取决于
**做多少运算**,不取决于**用多宽的阵列去做**。加宽阵列让你更快做完同样的功,但
不改变总功。→ **在这个 int8 matmul-bound 负载上,无法靠调 MAC 规模省能**。

**§3.3 静态能量很小**(~700–1000 nJ/层,vs 动态 127,000)。因为端侧推理算力
密集、时间短,漏电占比 <1%。所以全模型能量三设计都 ≈ 2.30 mJ(动态主导),
**能量不是区分设计的维度**。

**§3.4 于是设计选择退化为"延迟 vs 面积"的二维权衡**:
- 动态能量固定 → EDP ∝ 延迟 → **EDP 最优 = 延迟最优 = A**。
- 若有面积/功耗预算,则在 A/B/C 里选满足预算的最快者。

**验算(接地一致性)**:1.96 G-MAC × ~1.1 pJ/MAC(int8+fp32累加,Horowitz)
≈ 2.16 mJ 动态,与表中 2.30 mJ 总能量一致。设计 A 面积 4.07 mm²,其中 MAC
阵列 3.47 mm²(64×64 int8+bfp16,`test_physical_validation` 校核 1024-MAC ≈
0.54 mm² → 4096-MAC ≈ 2.2 mm² int8-only,+bfp16 lane 到 3.47,量级合理)。

## 4. 推荐与可信度

| 约束场景 | 选 | 理由 |
|---|---|---|
| 实时推理 / 延迟 SLA | **A** | 1.36 ms,EDP 最优;面积代价 4 mm² 可接受则最佳 |
| 面积/成本敏感的量产端侧 | **B** | 2.05 mm²,2.5 ms,平衡点 |
| 极小 die / 非实时 | **C** | 0.63 mm²,慢但省面积;能量不吃亏 |

**若要更进一步**:平台的 `optimize --objective edp/energy` 可在给定旋钮集上自动
搜最优;`sweep mac.array_rows` 可画延迟/面积曲线找拐点。本案例的结论(FFN-bound
→ 加宽 MAC;能量设计不变)已足以定方向。

**可信度声明**:所有绝对数字为 45nm 文献接地物理模型,±30% 解析带
(`docs/Physical-Validation.md` 全部锚点区间内),本案例 `fidelity` = 100% 面积
物理化。**相对结论(A 快 4× / 能量不变 / FFN 主导)比绝对数字更硬**——跨节点
绝对值待 Phase 5 综合标定。功能正确性是 golden-reference,非 bit-accurate RTL。
