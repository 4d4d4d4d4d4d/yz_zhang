# SPEC-009 工作负载形变 + 互连模块族(Workload-Shape & Interconnect)

文档状态：**v0.1 Draft(implementation spec — full review)**
最后更新：2026-06-23
Owners：架构组
派生自：SPEC-001/002/005/007/008、ADR-002

## 0. 范围与方法

补齐 Tier 2:工作负载形变 + 多 tile 互连 + 带宽优化。5 个 § 全部本版交付。

| § | 模块 | 角色 |
|---|---|---|
| §1 | **IM2COL** | conv→GEMM tensor 重排 |
| §2 | **RDC**(Reduction Unit) | 跨 PE 行/列规约(attention/softmax) |
| §3 | **NoC**(Network-on-Chip / XBAR) | 多 tile NPU 内部路由 |
| §4 | **CDE**(Compression / Decompression Engine) | 片外带宽压缩 |
| §5 | **TRANSPOSE** | tensor 形状变换(layout flip) |

通用约定:同 SPEC-008(命名正则、 v1.0.0 版本、`behavior()` 生成器、area 维度、stage 命名、YAML-driven contract)。

---

## §1 IM2COL

### 1.1 capability + 身份
- `module_type()` = `"IM2COL"`
- capabilities:`conv2col_reorder`(必有),`stride_dilation`(可选)
- 新 IModule 子类:port 拓扑独特(act tile + kernel shape descriptor → unrolled tile),functional 是 shape 变换不是 unpack

### 1.2 端口
- `act_in`(INPUT, DATA),`kernel_desc_in`(INPUT, COMMAND),`im2col_out`(OUTPUT, DATA)

### 1.3 行为 / latency
- 每输入 act tile 周期 = `kernel_h × kernel_w × stride_overhead`,`stride_overhead=1` 默认 `[calibration knob]`
- 输出 token 大小 = `act.size_bytes × kernel_h × kernel_w / stride²`

### 1.4 area / energy
- `AreaModel(um2 = 18_000 + (enable_stride_dilation ? 4_000 : 0))` `[calibration knob]`
- dynamic = `0.3 pJ/output_byte`

### 1.5 stage
`idle` / `load_act` / `unroll` / `emit`

### 1.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| 大 kernel 代价 | `kernel_h=1,kernel_w=1`(1×1 conv) | `=3,=3`(3×3) |
| stride/dilation 支持 | `enable_stride_dilation=false` | `=true` |
| 与 DSB-only baseline 对比 | 直接 DSB→MAC | DSB→IM2COL→MAC |

---

## §2 RDC(Reduction Unit)

### 2.1 capability + 身份
- `module_type()` = `"RDC"`
- capabilities:`row_reduce_sum`、`row_reduce_max`、`tree_reduction`
- 新 IModule 子类:functional 是规约(N→1),与 VAU 的逐元素不同

### 2.2 端口
- `vec_in`(INPUT, DATA),`reduced_out`(OUTPUT, DATA),`cmd_in`(INPUT, COMMAND)

### 2.3 行为 / latency
- tree-reduce log2(N) cycles + 1 emit
- N = `vec_in.size_bytes / element_bytes`,默认 `element_bytes=4`

### 2.4 area / energy
- `AreaModel(um2 = 12_000 × tree_width)`,`tree_width=8` 默认 `[calibration knob]`
- dynamic = `0.4 pJ/reduce_op`

### 2.5 stage
`idle` / `load_vec` / `reduce_log2` / `emit`

### 2.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| tree_width 影响 | `tree_width=4` | `=16` |
| 规约模式 | `mode=sum` | `mode=max` |
| 大向量 vs 小向量 | 8 elem | 128 elem |

---

## §3 NoC(Network-on-Chip / Crossbar)

### 3.1 capability + 身份
- `module_type()` = `"NoC"`
- capabilities:`xbar_route`,`multicast`(可选),`packet_arbitration`
- 新 IModule 子类:N×N 路由,port 数动态(`n_ports` config)

### 3.2 端口
- `port_<i>_in`/`port_<i>_out`(i=0..n_ports-1,DATA)

注:port_specs 在 IModule 的 classmethod 必须静态;NoC 不能动态加 port。**简化**:固定 4 port(in0..in3, out0..out3),足以做小规模 multi-tile 评估。完整 N×N 留 v1.1。

### 3.3 行为 / latency
- 每包路由 = `route_cycles`,默认 2 `[calibration knob]`
- arbitration:多包同一 out → 串行,每包额外 +1 cycle 仲裁
- multicast:1→N copies,N 个 out 同步发,每 out +1 cycle

### 3.4 area / energy
- `AreaModel(um2 = n_ports² × 8_000)` 4×4 = 128_000
- dynamic = `0.8 pJ/routed_packet`

### 3.5 stage
`idle` / `route_in_<i>` / `arbitrate` / `emit_out_<j>`

### 3.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| 单 tile vs 4 tile | 1 NoC port 用 | 4 port 全用 |
| route_cycles 调整 | =1 | =4 |
| multicast 收益 | 4 个单播 | 1 multicast |

---

## §4 CDE(Compression / Decompression Engine)

### 4.1 capability + 身份
- `module_type()` = `"CDE"`
- capabilities:`compress_rle`(必有),`compress_zlib`(可选),`decompress_*`
- 新 IModule 子类:tradeoff = 计算延迟 vs 带宽节省

### 4.2 端口
- `data_in`(INPUT, DATA),`data_out`(OUTPUT, DATA),`cmd_in`(INPUT, COMMAND)

### 4.3 行为 / latency
- 压缩比 `compression_ratio` 配置(默认 0.5,即输出 = 输入 50%)
- 每 byte 延迟 = 0.5 cycles `[calibration knob]`(简化)
- 输出 size = `input.size_bytes × compression_ratio`(压缩);`/ ratio`(解压)

### 4.4 area / energy
- `AreaModel(um2 = 20_000 + (enable_zlib ? 30_000 : 0))` `[calibration knob]`

### 4.5 stage
`idle` / `encode` / `decode` / `emit`

### 4.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| 压缩比影响 | `ratio=0.5` | `=0.25` |
| zlib vs rle | `enable_zlib=false` | `=true` |
| 端到端 DRAM 节省 | 无 CDE | CDE 接 DMA |

---

## §5 TRANSPOSE

### 5.1 capability + 身份
- `module_type()` = `"Transpose"`
- capabilities:`layout_transform_2d`,`layout_transform_3d`(可选)
- 新 IModule 子类:数据搬移(在 buffer 中物理重排)

### 5.2 端口
- `data_in`(INPUT, DATA),`data_out`(OUTPUT, DATA),`cmd_in`(INPUT, COMMAND)

### 5.3 行为 / latency
- 每 element 周期 = 1(管线化)
- token size 不变,只是元素顺序换

### 5.4 area / energy
- `AreaModel(um2 = 10_000 + (enable_3d ? 5_000 : 0))` `[calibration knob]`
- dynamic = `0.1 pJ/element`

### 5.5 stage
`idle` / `read_in` / `transpose` / `emit`

### 5.6 评估口径

| 评估 | baseline | variant |
|---|---|---|
| 2D vs 3D 支持 | `enable_3d=false` | `=true` |
| Transpose 必要性 | 无 Transpose | 插入 Transpose |
| 与 DSB 重写对比 | 用 DSB 重读 | 用 Transpose 在线 |

---

## 全规范实施路线

5 个 § 一次实现,各 3 对 YAML use case,各 1 个测试文件。Step 6 全系统集成:
SPEC-005 + SPEC-007 + SPEC-008 + SPEC-009 全部 17 个模块 同 YAML。

## 评审通过标准

按 SPEC v1.0 R1-R6 review,关注:
1. NoC 固定 4 port 简化是否可接受?(v1.1 提 N×N)
2. CDE 压缩 ratio 数值模型(只算延迟+输出 size,不算实际数据)够不够?
3. 各模块身份判定 OK?
