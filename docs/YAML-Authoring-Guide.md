# 架构 YAML 编写指南(Architecture YAML Authoring Guide)

文档状态:**使用手册 v1.0**
最后更新:2026-07-21
适用:SPEC-003 架构描述 DSL(含 v1.1 增订)
关联:`npu_sim/architecture/dsl_schema.py`(权威 schema)、
`docs/EVALUATION_REPORT.md`(评估示例)

> 一句话:**评估 = 写一对 YAML(baseline / variant)→ `python -m npu_sim
> compare base.yaml variant.yaml`**。本指南教你从零写这对 YAML。

---

## 0. 五分钟上手

一个最小可跑的架构 = **时钟 + 模块 + 连接**。存成 `my_chip.yaml`:

```yaml
schema_version: "1.0"          # 固定写 "1.0"
name: "我的第一个芯片"          # 任意名字,会出现在报告里

clock_domains:                 # 至少一个时钟域
  - id: main_clk
    period_ps: 1000            # 周期 1000 ps = 1 GHz

modules:                       # 模块列表
  - id: prod                   # 实例名(小写,自己起)
    type: Producer             # 模块类型(见 §4 清单)
    clock: main_clk            # 挂到哪个时钟
    config:                    # 该模块的参数(见 §4)
      n_tokens: 8
      payload_size_bytes: 8
  - id: mac
    type: MAC
    clock: main_clk
    config: { array_rows: 32, array_cols: 32 }
  - id: cons
    type: Consumer
    clock: main_clk
    config: { receive_rate_cycles_per_token: 1 }

connections:                   # 谁连谁(源.端口 → 汇.端口)
  - { from: prod.out,     to: mac.in_act,  fifo_depth: 4, latency_cycles: 1 }
  - { from: mac.out_psum, to: cons.in,     fifo_depth: 4, latency_cycles: 1 }
```

跑一次:

```bash
python -m npu_sim simulate my_chip.yaml       # 出仿真报告
python -m npu_sim trace    my_chip.yaml        # 出逐拍波形图
```

---

## 1. 文件骨架:五个顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | ✅ | 固定 `"1.0"` |
| `name` | ✅ | 架构名(报告里显示) |
| `clock_domains` | ✅* | 时钟域列表;`base` 继承时可省 |
| `modules` | ✅* | 模块实例列表 |
| `connections` | ✅* | 连接列表 |
| `base` | ⭕ | 继承另一个 YAML(见 §3),此时上面三个可只写差异 |
| `description` | ⭕ | 多行说明,建议写清楚这个 fixture 评估什么 |
| `metadata` | ⭕ | `{ tags: [...] }` 之类的标签 |

`*` = 要么直接写,要么通过 `base` 继承。

---

## 2. 三个核心块

### 2.1 `clock_domains` — 时钟域

```yaml
clock_domains:
  - id: main_clk
    period_ps: 1000        # 1 GHz
  - id: fast_clk
    period_ps: 500         # 2 GHz(提频实验用)
```

- 单位是 **ps(皮秒)**,`period_ps: 500` = 2 GHz。
- 想做"提频"评估:baseline 用 1000,variant 用 500,drain_time 减半。
- 多个域 + 模块挂不同域 → 自动触发 SPEC-002 §5.1 跨时钟域(CDC)处理。

### 2.2 `modules` — 模块实例

```yaml
modules:
  - id: mac_0              # 实例名:小写字母开头,[a-z0-9_]
    type: MAC             # 类型:见 §4 清单(大小写敏感)
    clock: main_clk       # 必须是上面声明过的域 id
    config:               # 该类型支持的参数(见 §4);不写则全用默认
      array_rows: 64
      array_cols: 64
      support_bfp16: true
```

规则:
- `id` 唯一、小写、下划线风格(`mac_0`、`wb_left`)。
- `type` 必须是注册过的模块类型;拼错会在 elaborate 阶段报
  `UnknownModuleTypeError` 并列出所有可用类型。
- `config` 里的 key 必须在该模块 schema 内;每个字段都有默认值,
  只写你要改的即可。

### 2.3 `connections` — 连接

```yaml
connections:
  - { from: dagc.out_unpacked, to: dsb.in_data, fifo_depth: 4, latency_cycles: 1 }
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `from` | ✅ | `源实例.输出端口`(端口名见 §4) |
| `to` | ✅ | `汇实例.输入端口` |
| `fifo_depth` | ⭕ | 连接 FIFO 深度(默认 1);越小越容易反压 |
| `latency_cycles` | ⭕ | 传输延迟拍数(默认 1) |
| `bandwidth_gbps` | ⭕ | 带宽(默认 0 = 不限) |

关键约束(写错会在 elaborate 阶段报 `PortNotFoundError`):
- `from` 端口必须是源模块的 **OUTPUT** 端口。
- `to` 端口必须是汇模块的 **INPUT** 端口。
- 端口名严格来自 §4 的清单,不能自己编。

---

## 3. base + overrides:写"变体"的正确姿势 ⭐

评估的本质是"同一架构改一个 knob"。**不要复制整个 baseline 再改**,而是用
`base` 继承 + `overrides` 只写差异。这也是仓库里所有 `usecase_*` 的写法。

**baseline**(`usecase_wb_small.yaml`):

```yaml
schema_version: "1.0"
name: "WB 64KB baseline"
clock_domains:
  - { id: main_clk, period_ps: 1000 }
modules:
  - { id: prod, type: Producer, clock: main_clk, config: { n_tokens: 8, payload_size_bytes: 1024 } }
  - { id: wb,   type: WB,       clock: main_clk, config: { capacity_kb: 64 } }
  - { id: cons, type: Consumer, clock: main_clk, config: { receive_rate_cycles_per_token: 1 } }
connections:
  - { from: prod.out,     to: wb.weight_in,  fifo_depth: 8, latency_cycles: 1 }
  - { from: wb.weight_out, to: cons.in,       fifo_depth: 8, latency_cycles: 1 }
```

**variant**(`usecase_wb_large.yaml`)—— 只改 WB 容量:

```yaml
schema_version: "1.0"
name: "WB 256KB variant"
base: usecase_wb_small.yaml     # ← 继承 baseline

overrides:
  modules:
    wb:                          # 按实例 id 定位
      config:
        capacity_kb: 256         # ← 唯一的改动
```

`overrides` 支持的操作:

| 操作 | 写法 | 作用 |
|---|---|---|
| 改模块 config | `modules: { <id>: { config: {...} } }` | 覆写字段 |
| 改模块时钟 | `modules: { <id>: { clock: fast_clk } }` | 换时钟域 |
| 加模块 | `add_modules: [ {...} ]` | 追加实例 |
| 删模块 | `remove_modules: [ <id> ]` | 删除(自动清理悬空连接) |
| 加连接 | `add_connections: [ {...} ]` | 追加连接 |
| 删连接 | `remove_connections: [ {from,to} ]` | 删除 |
| **跨 die 外置** | `modules: { <id>: { __relocate__: {...} } }` | 见 §5.1 |

**加模块 + 加连接**的例子(给 MCU 配一个 OGU):

```yaml
base: usecase_mcu_baseline.yaml
overrides:
  modules:
    mcu_0: { config: { has_ogu_peer: true, ogu_peer_id: ogu_0 } }
  add_modules:
    - { id: ogu_0, type: OGU, clock: main_clk, config: { mcu_peer_id: mcu_0 } }
  add_connections:
    - { from: mcu_0.ogu_req,  to: ogu_0.req_in,   fifo_depth: 4, latency_cycles: 1 }
    - { from: ogu_0.resp_out, to: mcu_0.ogu_resp, fifo_depth: 4, latency_cycles: 1 }
```

---

## 4. 模块参考清单(config 字段 + 端口)

> 端口名照抄,`config` 只列可调字段(= 号后是默认值)。完整口径见对应 SPEC。

### SPEC-005 数据通路

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **DAGC** | in_packed, in_cmd | out_unpacked | bfp8_unpack_throughput=2, bfp16_unpack_throughput=1, bfp_ratio="2:1", enable_compact_unpack=false |
| **DSB** | in_data, in_cmd | out_data | buffer_kb=64, read_throughput=4, enable_double_buffer=true, broadcast_factor=1 |
| **MAC** | in_act, in_weight, in_cmd | out_psum | array_rows=32, array_cols=32, support_bfp16=true, support_fp16=false, psums_per_tile=1 |
| **VAU** | in_a, in_b, in_cmd | out | lanes=16, support_max=true, support_relu=true |
| **AVP** | in_data, in_cmd | out_data | vector_width=16, support_softmax=true, support_layernorm=true, lut_entries=256 |

### SPEC-007 控制 / 传输

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **MCU** | cmd_in, ogu_resp | op_out, ogu_req | has_ogu_peer=false, threads=1, ogu_peer_id |
| **OGU** | req_in | resp_out, cfg_broadcast_out | mcu_peer_id(**必填**) |
| **TAU** | descriptor_in | addr_stream_out | addr_fifo_depth=16 |
| **DMA** | addr_stream_in | data_out | dram_burst_latency=40, bus_width_bytes=32 |
| **MTU** | descriptor_in | data_out | dram_burst_latency=40, bus_width_bytes=32, overlap_factor=0.8 |
| **AGU** | op_in, tick_in | inner_addr_out | client_module_id(**必填**), agu_pipeline_depth=3 |

### SPEC-008 内存 / 精度

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **WB** | weight_in, prefetch_cmd_in, cmd_in | weight_out | capacity_kb=256, read_bw_bytes_per_cycle=64, enable_prefetch=false |
| **OB** | psum_in, cmd_in | acc_out | tile_kb=16, max_in_flight_tiles=2, accumulate_depth=1, support_fp32_acc=true |
| **Quant** | data_in, scale_in, cmd_in | data_out | direction="quant"/"dequant", bits_in=32, bits_out=8, enable_per_channel=false |
| **SFU** | req_in, operand_in | result_out | enable_trig=false, default_op="exp"(exp/log/rsqrt/div/sin/cos) |

### SPEC-009 形变 / 互连

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **IM2COL** | act_in, kernel_desc_in | im2col_out | kernel_h=3, kernel_w=3, stride=1 |
| **RDC** | vec_in, cmd_in | reduced_out | tree_width=8, mode="sum"/"max", element_bytes=4 |
| **NoC** | port_0_in..port_3_in | port_0_out..port_3_out | route_cycles=2, enable_multicast=false |
| **CDE** | data_in, cmd_in | data_out | direction="compress"/"decompress", compression_ratio=0.5, enable_zlib=false |
| **Transpose** | data_in, cmd_in | data_out | enable_3d=false, element_bytes=4 |

### SPEC-010 系统基础

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **PMU** | event_in | report_out | n_counters=3, report_period_cycles=100 |
| **SYNC** | arrive_in | release_out | n_participants=2, barrier_overhead_cycles=2 |

### SPEC-011 DRAM / 专用

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **MC** | req_in, writeback_in | data_out | n_banks=8, row_hit_cycles=4, row_miss_cycles=40, refresh_period_cycles=7800 |
| **L2** | req_in, data_in | data_out, mc_pass_through | capacity_kb=512, hit_rate=0.8, hit_cycles=8, miss_cycles=12 |
| **SE** | sparse_in, cmd_in | dense_out | sparsity_ratio=0.5, enable_structured_pruning=false |
| **TLU** | index_in, table_load | embedding_out | table_size_kb=2048, enable_scatter=false, embedding_dim_bytes=256 |
| **CMDQ** | host_in | mcu_out | queue_depth=64, enable_priority=false |
| **MMU** | vaddr_in, pt_walk_resp | paddr_out, pt_walk_req | tlb_entries=64, tlb_hit_rate=0.95, pt_walk_cycles=20 |

### probe / 激励(写测试链常用)

| 模块 | 输入端口 | 输出端口 | 主要 config |
|---|---|---|---|
| **Producer** | — | out | n_tokens=16, send_rate_cycles_per_token=1, payload_size_bytes=8 |
| **Consumer** | in | — | receive_rate_cycles_per_token=1, max_to_accept=-1, never_consume=false |
| **Passthrough** | in | out | forward_rate_cycles_per_token=1 |
| **Merger** | in0, in1 | out | forward_rate_cycles_per_token=1 |

> **提示**:`Producer` 是合成激励源(发 N 个固定大小的 token),`Consumer` 是
> 汇。做瓶颈/反压评估时,用慢 `Consumer`(`receive_rate_cycles_per_token: 20`)
> 制造下游拥堵。

---

## 5. v1.1 高级 override

### 5.1 `__relocate__` — 模块外置(3D / 跨 die)

给某模块的所有出向连接加延迟/能耗/面积惩罚,不改拓扑:

```yaml
overrides:
  modules:
    dagc:
      __relocate__:
        from_die: 0
        to_die: 1
        latency_penalty_pct: 10     # 出向连接 +10% 传输延迟
        energy_penalty_pct: 10
        area_penalty_pct: 0
```

约束:`from_die != to_die`,penalty ≥ 0。

### 5.2 提频

不需要特殊语法 —— 直接在 variant 里重声明 `clock_domains` 改 `period_ps`:

```yaml
# variant:提频到 2 GHz
clock_domains:
  - { id: main_clk, period_ps: 500 }
# ... 其余同 baseline
```

---

## 6. 怎么跑 / 怎么看结果

```bash
# 单跑:出 Markdown 仿真报告(drain_time / area / stall / 不变量)
python -m npu_sim simulate my_chip.yaml

# 对比:baseline vs variant,出 delta 报告 ← 评估主入口
python -m npu_sim compare base.yaml variant.yaml

# 波形:逐拍状态机 + FIFO 占用 + 反压归因(见每个模块在干什么)
python -m npu_sim trace my_chip.yaml --show-cycles 160

# 列出所有可用模块类型
python -m npu_sim list-modules
```

Python 里(写自动化评估时):

```python
from npu_sim.evaluation import elaborate_and_run, compare
base = elaborate_and_run("base.yaml", max_cycles=5000)
var  = elaborate_and_run("variant.yaml", max_cycles=5000)
print(compare(base, var).summary_text)
```

报告里看什么:

| 指标 | 含义 |
|---|---|
| `drain_time_ps` | 最后一个 token 到达时间 = 端到端延迟 |
| `total_area_um2` | 全模块面积和 |
| `total_stall_ps` | 反压总停顿 |
| `bottleneck_module` | 反压链根因模块(SPEC-002 §3.3) |
| 不变量 VALID/INVALID | 仿真是否自洽 |

---

## 7. 常见坑

| 症状 | 原因 | 解决 |
|---|---|---|
| `UnknownModuleTypeError` | `type` 拼错/大小写错 | 照抄 §4 清单;`list-modules` 核对 |
| `PortNotFoundError: ... not declared` | 端口名编错 | 端口名严格照 §4;别自己造 |
| `... must be an OUTPUT/INPUT port` | from/to 接反了 | `from`=输出口,`to`=输入口 |
| `ConfigurationError: requires xxx_peer_id` | OGU/AGU 少了必填配对 id | 补 `mcu_peer_id`/`client_module_id` |
| variant 结果和 baseline 一模一样 | override 没生效(实例 id 写错) | `overrides.modules` 的 key 必须是 baseline 里真实的 `id` |
| drain 不变但确实改了下游模块 | 改的模块不在关键路径上 | 看 `stall_delta` 和 `bottleneck`,影响可能表现为反压 |
| token 卡住不完成 | 下游 Consumer 太慢或 FIFO 太浅 | 调大 `fifo_depth` 或 Consumer 速率 |

---

## 8. 一个完整的评估配方(照抄改,已实测)

目标:评估"把 MAC 阵列做大,能否把 MAC 从瓶颈上解放出来"。

> ⚠️ **一个真实的坑**:MAC 运行时每 token 的计算拍数 =
> `array_cols // array_rows + 1`。所以 **方阵放大不改延迟**(32×32 和
> 64×64 都是 2 拍)。要让 MAC 成为可观察的瓶颈,得用"小且瘦"的阵列
> (如 8×16 → 3 拍/token),再对比放大后的方阵。下面是实测有效的一对。

**`mac_slow.yaml`**(baseline,MAC 是瓶颈):
```yaml
schema_version: "1.0"
name: "MAC 8x16 (bottleneck)"
clock_domains: [ { id: main_clk, period_ps: 1000 } ]
modules:
  - { id: prod, type: Producer, clock: main_clk, config: { n_tokens: 16, send_rate_cycles_per_token: 2, payload_size_bytes: 8 } }
  - { id: mac,  type: MAC,      clock: main_clk, config: { array_rows: 8, array_cols: 16 } }
  - { id: cons, type: Consumer, clock: main_clk, config: { receive_rate_cycles_per_token: 1 } }
connections:
  - { from: prod.out,     to: mac.in_act,  fifo_depth: 4, latency_cycles: 1 }
  - { from: mac.out_psum, to: cons.in,     fifo_depth: 4, latency_cycles: 1 }
```

**`mac_fast.yaml`**(variant,阵列放大):
```yaml
schema_version: "1.0"
name: "MAC 32x32 (relieved)"
base: mac_slow.yaml
overrides:
  modules:
    mac: { config: { array_rows: 32, array_cols: 32 } }
```

跑:
```bash
python -m npu_sim compare mac_slow.yaml mac_fast.yaml
```

**实测结果**:`drain_time 50,000 → 34,000 ps(-32%)`,
`bottleneck: mac → None` —— 更大阵列把 MAC 从瓶颈上解放出来,反压消失。
这就是一个"改一个 config 字段 → 仿真出可信 delta"的完整评估。

---

## 附:去哪找更多例子

`tests/fixtures/architectures/usecase_*.yaml` 有 40+ 个现成 baseline/variant
对,覆盖本仓库全部评估场景。`docs/EVALUATION_REPORT.md` 是它们的实测结果表,
`scripts/run_all_evaluations.py` 是一键重跑脚本。
