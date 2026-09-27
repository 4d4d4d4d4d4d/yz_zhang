# SPEC-011 DRAM 子系统 + 专用计算扩展(DRAM & Specialized Compute)

文档状态：**v0.1 Draft (一次性 6 §§ 全交付)**
最后更新：2026-06-23
Owners：架构组

## 0. 范围

对照 Ascend / NVDLA / Ethos / TPU / GraphCore / Tenstorrent,补齐剩余 6
类模块。本版一次实现 + 测试。

| § | 模块 | 角色 |
|---|---|---|
| §1 | **MC**(Memory Controller / HBM controller) | DRAM 多 bank/channel 仲裁、refresh、row-buffer hit |
| §2 | **L2**(Last-Level Cache) | DSB ↔ DRAM 中间层,几 MB SRAM |
| §3 | **SE**(Sparse Engine) | 稀疏 tensor 跳零计算 |
| §4 | **TLU**(Tensor Lookup / Embedding) | LLM token embedding,推荐系统 |
| §5 | **CMDQ**(Command Queue) | Host ↔ MCU 命令缓冲 |
| §6 | **MMU**(Memory Management Unit) | 虚拟→物理地址翻译,TLB |

通用约定同 SPEC-008/009/010(命名正则、v1.0.0、`behavior()`、area 模型、
stage 命名、YAML-driven contract)。

---

## §1 MC(Memory Controller / HBM)

### 1.1 capability + 身份
- `module_type()` = `"MC"`
- caps:`dram_read`、`dram_write`、`refresh`、`row_buffer_hit_track`
- 新 IModule 子类:bank/channel 级并行,功能与 DMA 不同(DMA 是用户)

### 1.2 端口
- `req_in`(INPUT, COMMAND)、`data_out`(OUTPUT, DATA)、`writeback_in`(INPUT, DATA)

### 1.3 行为 / latency
- row-buffer hit:`row_hit_cycles=4` 默认 `[calibration knob]`
- row-buffer miss:`row_miss_cycles=40`
- refresh:每 `refresh_period_cycles=7800` 一次,刷新期间 stall(stall reason `mc_refresh`)
- bank 数:`n_banks=8` 默认,bank 并行减小冲突

### 1.4 area / energy
- `AreaModel(um2 = 50_000 + n_banks × 8_000)` `[calibration knob]`
- dynamic = `5 pJ/byte_read + 8 pJ/byte_write`(off-chip 贵)

### 1.5 stage
`idle` / `row_open` / `column_access` / `precharge` / `refresh` / `emit_data`

### 1.6 评估
| 评估 | baseline | variant |
|---|---|---|
| bank 数 | `n_banks=4` | `=16` |
| refresh 影响 | `refresh_period=10000` | `=2000`(高频) |
| row-buffer 命中模式 | 顺序访问 | 随机访问 |

---

## §2 L2(Last-Level Cache)

### 2.1 capability + 身份
- `module_type()` = `"L2"`
- caps:`cache_read`、`cache_write`、`writeback_dirty`,`prefetch_stride`(可选)
- 新 IModule 子类:介于 DSB(L1) 和 MC(DRAM) 之间

### 2.2 端口
- `req_in`(INPUT, COMMAND)、`data_in`(INPUT, DATA)、`data_out`(OUTPUT, DATA)、`mc_pass_through`(OUTPUT, COMMAND)

### 2.3 行为 / latency
- hit:`hit_cycles=8` `[calibration knob]`
- miss:`miss_cycles=12`(+ MC latency 自下游)
- 容量:`capacity_kb=512` 默认
- 简化:LRU,逐 token 模拟,hit rate 通过 `hit_rate` config 静态设定(随后用于决策每 op 走 hit 还是 miss 路径)

### 2.4 area / energy
- `AreaModel(um2 = capacity_kb × 800)`(L2 比 WB 密度高一点) `[calibration knob]`
- dynamic = `1.2 pJ/byte_access`

### 2.5 stage
`idle` / `lookup` / `hit_serve` / `miss_pass` / `writeback`

### 2.6 评估
| 评估 | baseline | variant |
|---|---|---|
| 容量 | `capacity_kb=256` | `=2048` |
| hit_rate | `0.5` | `0.9` |
| prefetch | `enable_prefetch=false` | `=true` |

---

## §3 SE(Sparse Engine)

### 3.1 capability + 身份
- `module_type()` = `"SE"`
- caps:`sparse_skip_zero`、`sparse_index_decode`、`structured_pruning_support`(可选)
- 新 IModule 子类:跳零导致非常 data-dependent 的 latency

### 3.2 端口
- `sparse_in`(INPUT, DATA,带 mask metadata)、`dense_out`(OUTPUT, DATA)、`cmd_in`(INPUT, COMMAND)

### 3.3 行为 / latency
- 每 token 周期 = `dense_elements × sparsity_ratio`,默认 `sparsity_ratio=0.5`(50% 稀疏)`[calibration knob]`
- `enable_structured_pruning=true` → 跳零更高效,latency × 0.7

### 3.4 area / energy
- `AreaModel(um2 = 22_000 + (enable_structured_pruning ? 8_000 : 0))`
- dynamic = `0.2 pJ/non_zero_element`

### 3.5 stage
`idle` / `decode_mask` / `skip_zero` / `emit_dense`

### 3.6 评估
| 评估 | baseline | variant |
|---|---|---|
| sparsity ratio | `0.3`(30% 稀疏) | `0.8` |
| structured on/off | `false` | `true` |
| 端到端 + MAC | dense MAC | SE + MAC |

---

## §4 TLU(Tensor Lookup Unit / Embedding)

### 4.1 capability + 身份
- `module_type()` = `"TLU"`
- caps:`embedding_lookup`、`gather_op`、`scatter_op`(可选)
- 新 IModule 子类:随机访问 embedding table(LLM token / 推荐系统)

### 4.2 端口
- `index_in`(INPUT, COMMAND,batch indices)、`embedding_out`(OUTPUT, DATA)、`table_load`(INPUT, DATA)

### 4.3 行为 / latency
- 每次 lookup = `1 + log2(table_size_kb)`(BST or hash 模型,简化)
- 容量:`table_size_kb=2048` 默认(大 embedding 表)

### 4.4 area / energy
- `AreaModel(um2 = table_size_kb × 600)`(embedding 表密度比 L2 大)
- dynamic = `0.5 pJ/lookup`

### 4.5 stage
`idle` / `decode_index` / `table_read` / `emit_embedding`

### 4.6 评估
| 评估 | baseline | variant |
|---|---|---|
| table 大小 | `table_size_kb=512` | `=8192` |
| gather vs scatter | gather only | + scatter |
| 与 DSB-only 对比 | 用 DSB+MAC 模拟 lookup | TLU 专用 |

---

## §5 CMDQ(Command Queue)

### 5.1 capability + 身份
- `module_type()` = `"CMDQ"`
- caps:`fifo_queue`、`priority_queue`(可选)
- 新 IModule 子类:host→MCU 缓冲,完全 throughput 模型

### 5.2 端口
- `host_in`(INPUT, COMMAND)、`mcu_out`(OUTPUT, COMMAND)

### 5.3 行为 / latency
- depth `queue_depth=64` 默认
- enqueue/dequeue 各 1 cycle
- 满则反压 host

### 5.4 area / energy
- `AreaModel(um2 = queue_depth × 200 + (enable_priority ? 5_000 : 0))`
- dynamic = `0.05 pJ/cmd`

### 5.5 stage
`idle` / `enqueue` / `dequeue`

### 5.6 评估
| 评估 | baseline | variant |
|---|---|---|
| depth 影响 | `=16` | `=256` |
| priority on/off | false | true |
| 反压 host(满队) | host 慢 | host 快 |

---

## §6 MMU(Memory Management Unit)

### 6.1 capability + 身份
- `module_type()` = `"MMU"`
- caps:`virtual_address_translate`、`tlb_lookup`、`page_table_walk`
- 新 IModule 子类:translation 路径,TLB 命中/失败大幅影响延迟

### 6.2 端口
- `vaddr_in`(INPUT, COMMAND)、`paddr_out`(OUTPUT, COMMAND)、`pt_walk_req`(OUTPUT, COMMAND)、`pt_walk_resp`(INPUT, COMMAND)

### 6.3 行为 / latency
- TLB hit:1 cycle
- TLB miss → page table walk:`pt_walk_cycles=20` `[calibration knob]`
- `tlb_entries=64` 默认,LRU

### 6.4 area / energy
- `AreaModel(um2 = tlb_entries × 200 + 8_000)` (CAM 贵)
- dynamic = `0.1 pJ/translate`

### 6.5 stage
`idle` / `tlb_lookup` / `tlb_hit` / `tlb_miss_walk` / `emit_paddr`

### 6.6 评估
| 评估 | baseline | variant |
|---|---|---|
| TLB size | `=16` | `=256` |
| miss rate | `tlb_hit_rate=0.95` | `=0.5` |
| 与 no-MMU 对比 | 无 MMU,直 paddr | 加 MMU |

---

## 实施 + Step 8 全系统集成

6 个 § 一次实现,各 1-2 对 YAML use case,各 1 个测试。
Step 8:NPU v4 全栈 fixture 把 SPEC-005+007+008+009+010+011 全部 **26 个模块**
塞入同 YAML。
