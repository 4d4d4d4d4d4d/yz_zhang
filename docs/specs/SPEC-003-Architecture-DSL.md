# SPEC-003：架构描述 DSL 规范

文档状态：Draft v0.1
作者：架构组
目的：定义平台架构描述的声明式 DSL
依赖：SPEC-001 IModule 接口规范、SPEC-002 反压协议规范

## 1. 目的与范围

定义平台架构描述的声明式 DSL。**架构是数据，不是代码** —— 这是平台支持长期演进的关键。

DSL 必须支持：

- 当前 NPU 架构完整描述
- 架构 variant（增删改 capability、参数微调）
- 结构性变化（模块融合、拆分、新增、删除）
- 多 die / 多时钟域拓扑
- 版本管理与 diff

## 2. 设计决策

- **格式**：YAML（人类可读、易 diff、广泛工具支持）
- **语义**：声明式、纯数据，不嵌入逻辑（不用 Python DSL）
- **校验**：基于 JSON Schema + 自定义语义校验
- **复用**：base + overrides 模式，避免重复
- **扩展**：通过模块注册机制，新模块自动可用

## 3. DSL 总览

### 3.1 顶层结构

```yaml
# 一份架构描述的顶层结构
schema_version: "1.0"          # DSL 自身版本
name: "NPU v1 baseline"        # 架构名
description: "..."
metadata:
  author: "..."
  created: "2026-05-22"
  tags: ["baseline", "v1"]

# === 可选：继承自其他架构 ===
base: "npu_v1.yaml"            # 路径或 URI
overrides:                     # 见 §6
  ...

# === 必需：架构本体 ===
clock_domains: [...]           # 时钟域定义
modules: [...]                 # 模块实例
connections: [...]             # 模块间连接
topology: {...}                # 物理拓扑（die / chiplet）
constraints: [...]             # 全局约束（功耗预算、面积上限）
```

### 3.2 完整示例：NPU v1 Baseline

```yaml
schema_version: "1.0"
name: "NPU v1 baseline"
description: "当前流片设计基线"

clock_domains:
  - id: main_clk
    period_ps: 1000          # 1.0 GHz
    skew_ps: 50

  - id: ctrl_clk
    period_ps: 2000          # 0.5 GHz (MCU 子系统)
    skew_ps: 100

  - id: ddr_clk
    period_ps: 833           # 1.2 GHz (DDR I/F)
    skew_ps: 30

# ============================================================
# 模块实例
# ============================================================
modules:

  # ---- 控制子系统 ----
  - id: mcu
    type: MCU
    clock: ctrl_clk
    config:
      core: "rv32imc"
      icache_kb: 16
      dcache_kb: 16
      max_outstanding_msgs: 4

  - id: gfu
    type: GFU
    clock: ctrl_clk
    config:
      operation_queue_depth: 8

  - id: msgq
    type: MsgQueue
    clock: ctrl_clk
    config:
      depth: 32
      arbitration: "round_robin"

  # ---- 算子调度 ----
  - id: opsch
    type: OpScheduler
    clock: main_clk
    config:
      max_pending_ops: 16
      dispatch_width: 2

  - id: ogu
    type: OGU
    clock: main_clk
    config:
      buffsize_calc_throughput: 1
      bd_gen_pipeline_depth: 4
      op_config_throughput: 1
      loop_merge_supported: true   # capability flag

  # ---- 数据搬运 ----
  - id: dma
    type: DMA
    clock: main_clk
    config:
      channels: 4
      outstanding_per_channel: 8
      max_burst_bytes: 4096

  - id: mtu
    type: MTU
    clock: main_clk
    config:
      reshape_patterns: ["transpose", "tile_split", "concat"]
      throughput_bytes_per_cycle: 64

  - id: tau
    type: TAU
    clock: main_clk
    config:
      bitmap_extraction: true
      independent_mode: false      # FDD SPF 7% 代价的开关

  # ---- 存储层级 ----
  - id: l1d
    type: L1Data
    clock: main_clk
    config:
      capacity_kb: 64
      line_bytes: 64
      assoc: 4
      banks: 4

  - id: dsb
    type: DSB
    clock: main_clk
    config:
      capacity_kb: 1024
      banks: 8
      read_ports: 4
      write_ports: 2
      has_avp_data_buf: true       # capability flag
      direct_forwarding: true

  - id: l2
    type: L2Cache
    clock: main_clk
    config:
      capacity_mb: 4
      line_bytes: 128
      assoc: 8
      banks: 16

  - id: ddr
    type: DDRController
    clock: ddr_clk
    config:
      channels: 2
      banks_per_channel: 16
      page_kb: 2
      tCK_ps: 833
      tRCD: 14
      tCL: 14
      tRP: 14

  # ---- 计算阵列 ----
  - id: dagc
    type: DAGC
    clock: main_clk
    config:
      bfp8_unpack_throughput: 2
      bfp16_unpack_throughput: 1
      bfp_ratio: "2:1"
      support_4bit_reorder: true
      support_mixed_bfp8_bfp16: true
      join_fifo_depth: 16

  - id: mac
    type: MatVecArray
    clock: main_clk
    config:
      rows: 128
      cols: 128
      precision_modes: [INT8, FP16, BFP8, BFP16, MIXED_BFP8_BFP16]
      accumulator_width: 32
      split_mode: "single"         # single / 4x64x64 / 16x32x32 (劈裂)

  - id: vau
    type: VAU
    clock: main_clk
    config:
      lanes: 32
      ops: [add, mul, exp, log, sqrt, rsqrt, max, min, reduce]
      lut_exp: false                # 暂未启用
      reduce_tree_depth: 5
      hyper_threading: false        # VFU-HT

  - id: avp
    type: AVP
    clock: main_clk
    config:
      exp_unit: true
      rsqrt_unit: true
      lut_size_bytes: 4096
      pipeline_depth: 6

  - id: agu_r
    type: AGU
    clock: main_clk
    config:
      direction: "read"
      throughput_addr_per_cycle: 2
      pattern_support: ["stride", "gather", "nested_loop"]
      max_dim: 6

  - id: agu_w
    type: AGU
    clock: main_clk
    config:
      direction: "write"
      throughput_addr_per_cycle: 1   # 已经是 baseline 的 W 端配置
      pattern_support: ["stride", "scatter"]
      max_dim: 6

  - id: poe
    type: POE
    clock: main_clk
    config:
      arbitration: "priority"
      max_outstanding: 16

# ============================================================
# 连接
# ============================================================
connections:

  # 控制路径
  - { from: mcu.out_msg,    to: msgq.in,       fifo_depth: 8,  latency_cycles: 2 }
  - { from: msgq.out,       to: opsch.in_msg,  fifo_depth: 8,  latency_cycles: 2 }
  - { from: opsch.out_cfg,  to: ogu.in,        fifo_depth: 4,  latency_cycles: 1 }
  - { from: ogu.out_op,     to: mac.in_cmd,    fifo_depth: 4,  latency_cycles: 1 }
  - { from: ogu.out_bd,     to: dma.in_cmd,    fifo_depth: 4,  latency_cycles: 1 }
  - { from: ogu.out_bd,     to: mtu.in_cmd,    fifo_depth: 4,  latency_cycles: 1 }

  # 地址生成
  - { from: agu_r.out_addr, to: dsb.in_raddr,  fifo_depth: 8,  latency_cycles: 1 }
  - { from: agu_w.out_addr, to: dsb.in_waddr,  fifo_depth: 8,  latency_cycles: 1 }

  # 主数据通路 (DDR -> DSB -> DAGC -> MAC -> DSB -> ...)
  - { from: ddr.out_data,   to: l2.in_fill,    fifo_depth: 16, latency_cycles: 4, bandwidth_gbps: 100 }
  - { from: l2.out_data,    to: dsb.in_fill,   fifo_depth: 8,  latency_cycles: 2, bandwidth_gbps: 256 }
  - { from: dsb.out_read,   to: dagc.in_packed,fifo_depth: 8,  latency_cycles: 1 }
  - { from: dagc.out_unpacked, to: mac.in_a,   fifo_depth: 16, latency_cycles: 2 }
  - { from: dsb.out_read,   to: mac.in_b,     fifo_depth: 16, latency_cycles: 2 }
  - { from: mac.out_result, to: dsb.in_write,  fifo_depth: 32, latency_cycles: 1 }

  # 向量 / 激活通路
  - { from: dsb.out_read,   to: vau.in_data,   fifo_depth: 8,  latency_cycles: 1 }
  - { from: vau.out_result, to: avp.in_data,   fifo_depth: 8,  latency_cycles: 1 }
  - { from: avp.out_result, to: dsb.in_write,  fifo_depth: 8,  latency_cycles: 1 }

  # 搬移通路
  - { from: mtu.out_data,   to: dsb.in_write,  fifo_depth: 16, latency_cycles: 1 }
  - { from: tau.out_data,   to: dsb.in_write,  fifo_depth: 16, latency_cycles: 1 }

  # 仲裁
  - { from: dsb.out_req,    to: poe.in,        fifo_depth: 4,  latency_cycles: 1 }
  - { from: poe.out,        to: l2.in_req,     fifo_depth: 4,  latency_cycles: 1 }

# ============================================================
# 拓扑（单 die）
# ============================================================
topology:
  type: "single_die"
  dies:
    - id: die_0
      process_node: "5nm"
      modules: [mcu, gfu, msgq, opsch, ogu, dma, mtu, tau,
                l1d, dsb, l2, dagc, mac, vau, avp, agu_r, agu_w, poe]
    - id: die_ddr
      process_node: "external"
      modules: [ddr]
  inter_die:
    - { from_die: die_0, to_die: die_ddr, latency_cycles: 20, bandwidth_gbps: 200 }

# ============================================================
# 全局约束（用于报告生成时核对）
# ============================================================
constraints:
  total_area_mm2: { max: 200.0 }
  total_static_power_w: { max: 5.0 }
  peak_dynamic_power_w: { max: 25.0 }
  thermal_design_power_w: { max: 15.0 }
```

### 3.3 Variant 示例：AGU-W 带宽减半

```yaml
schema_version: "1.0"
name: "NPU v1 - AGU-W bandwidth half"
description: "评估 AGU-W 带宽从 1 减到 0.5 的影响"

base: "npu_v1.yaml"

overrides:
  modules:
    agu_w:
      config:
        throughput_addr_per_cycle: 0.5
```

### 3.4 Variant 示例：VAU+AVP 融合做 softmax

```yaml
schema_version: "1.0"
name: "NPU v1 - VAU/AVP softmax fusion"
description: "softmax 中 exp 下沉到 VAU 查表实现，AVP 阉割为只剩 rsqrt"

base: "npu_v1.yaml"

overrides:
  modules:
    vau:
      config:
        lut_exp: true                # 新增查表 exp 能力
        lut_exp_size_bytes: 2048

    avp:
      config:
        exp_unit: false              # 删除 exp 单元
        # rsqrt_unit 保持 true
        lut_size_bytes: 1024         # 缩小 LUT（不再需要 exp 表）

  add_connections:
    - { from: vau.out_lut_exp, to: dsb.in_write, fifo_depth: 8, latency_cycles: 1 }

  # mapping_hints 在 mapper 规则中读取
  mapping_hints:
    softmax:
      exp_stage_module: vau
      reduce_stage_module: vau
      div_stage_modules: [avp, vau]   # rsqrt on avp, mul on vau
```

### 3.5 Variant 示例：MAC 劈裂

```yaml
schema_version: "1.0"
name: "NPU v1 - MAC split 4x64x64"

base: "npu_v1.yaml"

overrides:
  # 修改：原 mac 不再是单个大阵列
  modules:
    mac:
      config:
        split_mode: "4x64x64"
        # rows/cols 自动 derived 为 64
        reduction_network_latency: 3

  # 注：split_mode 在模块内部分裂，对外接口不变
  # 因此 connections 不需要改
```

### 3.6 Variant 示例：MTU 融合 DMA+TAU

```yaml
schema_version: "1.0"
name: "NPU v1 - MTU fused (DMA+TAU)"

base: "npu_v1.yaml"

overrides:
  # 删除原 dma 和 tau
  remove_modules: [dma, tau]

  # 新增融合后的 mtu_fused
  add_modules:
    - id: mtu_fused
      type: MTU_Fused
      clock: main_clk
      config:
        dma_channels: 4
        reshape_patterns: ["transpose", "tile_split", "concat", "bitmap_extract"]
        shared_buffer_kb: 32
        throughput_bytes_per_cycle: 64

  # 重新连线（替换原 dma/tau 的所有连接）
  remove_connections:
    - { from: ogu.out_bd,   to: dma.in_cmd }
    - { from: ogu.out_bd,   to: mtu.in_cmd }
    - { from: mtu.out_data, to: dsb.in_write }
    - { from: tau.out_data, to: dsb.in_write }

  add_connections:
    - { from: ogu.out_bd,        to: mtu_fused.in_cmd,  fifo_depth: 4, latency_cycles: 1 }
    - { from: mtu_fused.out_data, to: dsb.in_write,     fifo_depth: 16, latency_cycles: 1 }
```

## 4. DSL 完整 Schema（JSON Schema）

```yaml
# schemas/architecture_dsl.schema.yaml
$schema: "http://json-schema.org/draft-07/schema#"
type: object
required: [schema_version, name]
properties:

  schema_version:
    type: string
    pattern: "^[0-9]+\\.[0-9]+$"

  name:
    type: string
    minLength: 1

  description:
    type: string

  metadata:
    type: object
    properties:
      author: { type: string }
      created: { type: string, format: date }
      tags: { type: array, items: { type: string } }

  base:
    type: string
    description: "继承基础架构文件路径"

  overrides:
    $ref: "#/definitions/Overrides"

  clock_domains:
    type: array
    items: { $ref: "#/definitions/ClockDomain" }

  modules:
    type: array
    items: { $ref: "#/definitions/ModuleInstance" }
    uniqueItems: true   # by id

  connections:
    type: array
    items: { $ref: "#/definitions/Connection" }

  topology:
    $ref: "#/definitions/Topology"

  constraints:
    $ref: "#/definitions/Constraints"

# === 互斥规则 ===
oneOf:
  # 要么是完整定义
  - required: [modules, connections]
  # 要么是继承+覆盖
  - required: [base]

definitions:

  ClockDomain:
    type: object
    required: [id, period_ps]
    properties:
      id: { type: string }
      period_ps: { type: integer, minimum: 1 }
      skew_ps: { type: integer, default: 0 }

  ModuleInstance:
    type: object
    required: [id, type]
    properties:
      id:
        type: string
        pattern: "^[a-z][a-z0-9_]*$"
      type:
        type: string  # 必须是 ModuleRegistry 中注册的类型
      clock:
        type: string  # 必须是 clock_domains 中的某个 id
      config:
        type: object  # 由具体模块的 config_schema 校验

  Connection:
    type: object
    required: [from, to]
    properties:
      from:
        type: string
        pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"   # module.port
      to:
        type: string
        pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"
      fifo_depth: { type: integer, minimum: 1, default: 1 }
      latency_cycles: { type: integer, minimum: 0, default: 1 }
      bandwidth_gbps: { type: number, minimum: 0 }

  Overrides:
    type: object
    properties:
      modules:
        type: object
        # key 是 module id，value 是 partial config
        additionalProperties:
          type: object
          properties:
            config: { type: object }
            clock: { type: string }
      add_modules:
        type: array
        items: { $ref: "#/definitions/ModuleInstance" }
      remove_modules:
        type: array
        items: { type: string }
      add_connections:
        type: array
        items: { $ref: "#/definitions/Connection" }
      remove_connections:
        type: array
        items: { $ref: "#/definitions/Connection" }
      mapping_hints:
        type: object  # 自由格式，由 Mapper 解释

  Topology:
    type: object
    required: [type]
    properties:
      type:
        enum: ["single_die", "multi_die_2d", "multi_die_3d"]
      dies:
        type: array
        items:
          type: object
          required: [id, modules]
          properties:
            id: { type: string }
            process_node: { type: string }
            modules: { type: array, items: { type: string } }
      inter_die:
        type: array
        items:
          type: object
          properties:
            from_die: { type: string }
            to_die: { type: string }
            type: { enum: ["wire", "tsv", "microbump"] }
            latency_cycles: { type: integer }
            bandwidth_gbps: { type: number }

  Constraints:
    type: object
    properties:
      total_area_mm2:
        type: object
        properties:
          min: { type: number }
          max: { type: number }
      total_static_power_w:
        type: object
        properties:
          min: { type: number }
          max: { type: number }
      peak_dynamic_power_w:
        type: object
        properties:
          min: { type: number }
          max: { type: number }
```

## 5. Elaboration 算法

```python
# architecture/elaborator.py

class ArchitectureElaborator:
    """把 DSL 描述翻译成可执行的 SystemC 仿真模型。"""

    def __init__(self, registry: ModuleRegistry):
        self._registry = registry

    def elaborate(self, dsl_path: str) -> IArchitecture:
        # ============== Phase 1: 加载与合并 ==============
        raw = self._load_yaml(dsl_path)
        if "base" in raw:
            base = self._load_yaml(raw["base"])
            merged = self._apply_overrides(base, raw.get("overrides", {}))
        else:
            merged = raw

        # ============== Phase 2: Schema 校验 ==============
        self._validate_against_schema(merged)

        # ============== Phase 3: 语义校验 ==============
        self._semantic_validate(merged)
        # - module type 都已注册
        # - clock 引用都存在
        # - 连接的端口都存在且方向匹配
        # - capability 依赖自洽
        # - topology 中所有 module 都已定义

        # ============== Phase 4: 实例化时钟 ==============
        clocks = {
            cd["id"]: SystemCClock(period_ps=cd["period_ps"])
            for cd in merged["clock_domains"]
        }

        # ============== Phase 5: 实例化模块 ==============
        modules: dict[str, IModule] = {}
        for inst in merged["modules"]:
            module = self._registry.create(inst["type"], inst.get("config", {}))
            module.bind_services(
                event_bus=self._event_bus,
                stat_sink=self._stat_sink,
                clock=clocks[inst.get("clock", "main_clk")]
            )
            modules[inst["id"]] = module

        # ============== Phase 6: 建立连接 ==============
        connections: list[IConnection] = []
        for conn_spec in merged["connections"]:
            src_module_id, src_port_name = conn_spec["from"].split(".")
            dst_module_id, dst_port_name = conn_spec["to"].split(".")

            src_port = modules[src_module_id].output_ports()[src_port_name]
            dst_port = modules[dst_module_id].input_ports()[dst_port_name]

            # 校验端口规格兼容
            self._validate_port_compat(src_port, dst_port)

            conn = TlmConnection(
                source=src_port,
                sink=dst_port,
                fifo_depth=conn_spec.get("fifo_depth", 1),
                latency_cycles=conn_spec.get("latency_cycles", 1),
            )
            connections.append(conn)

        # ============== Phase 7: 构建拓扑 ==============
        topology = self._build_topology(merged["topology"], modules)

        # ============== Phase 8: 校验约束 ==============
        self._validate_constraints(modules, merged.get("constraints", {}))

        # ============== Phase 9: 返回 IArchitecture ==============
        return Architecture(
            modules=modules,
            connections=connections,
            topology=topology,
            clocks=clocks,
            metadata=merged.get("metadata", {})
        )

    def _apply_overrides(self, base: dict, overrides: dict) -> dict:
        """合并 base 和 overrides。

        规则：
        - modules[id].config: shallow merge
        - add_modules: 追加
        - remove_modules: 删除
        - add_connections: 追加
        - remove_connections: 按 from+to 匹配删除
        """
        result = deepcopy(base)

        # 处理 modules 覆盖
        if "modules" in overrides:
            for mod_id, override in overrides["modules"].items():
                existing = next((m for m in result["modules"] if m["id"] == mod_id), None)
                if existing is None:
                    raise OverrideError(f"Cannot override non-existent module: {mod_id}")
                if "config" in override:
                    existing.setdefault("config", {}).update(override["config"])
                if "clock" in override:
                    existing["clock"] = override["clock"]

        # 处理 add/remove modules
        if "remove_modules" in overrides:
            result["modules"] = [
                m for m in result["modules"]
                if m["id"] not in overrides["remove_modules"]
            ]
        if "add_modules" in overrides:
            result["modules"].extend(overrides["add_modules"])

        # 处理 connections（add/remove）
        if "remove_connections" in overrides:
            for to_remove in overrides["remove_connections"]:
                result["connections"] = [
                    c for c in result["connections"]
                    if not (c["from"] == to_remove["from"] and c["to"] == to_remove["to"])
                ]
        if "add_connections" in overrides:
            result["connections"].extend(overrides["add_connections"])

        # mapping_hints 透传
        if "mapping_hints" in overrides:
            result["mapping_hints"] = overrides["mapping_hints"]

        return result
```

## 6. Override 合并语义详解

| Override 操作 | 语义 | 示例 |
|---|---|---|
| `modules.<id>.config.<key>` | shallow merge：覆盖该 key，保留其他 | 改一个参数 |
| `modules.<id>.clock` | 替换 clock 引用 | 改时钟域 |
| `add_modules` | 追加新模块 | 加 SAU |
| `remove_modules` | 按 id 删除模块 | 删 TAU |
| `add_connections` | 追加新连接 | 新模块的连线 |
| `remove_connections` | 按 from+to 删除连接 | 删除旧连接 |
| `mapping_hints` | 替换 hints 块 | Mapper 行为提示 |

重要约束：

- override 中不能修改连接的属性（要修改先 remove 再 add）
- override 中不能修改模块 type（type 变化等于换模块，应 remove + add）
- override 不递归继承（base 不能再 base 别人，避免链式继承复杂度）

## 7. 测试规范

```python
# tests/integration/test_elaborator.py

class TestArchitectureElaborator:

    def test_baseline_loads(self):
        arch = elaborator.elaborate("architectures/npu_v1.yaml")
        assert len(arch.modules) > 10
        assert "mac" in arch.modules

    def test_variant_inherits_baseline(self):
        baseline = elaborator.elaborate("architectures/npu_v1.yaml")
        variant = elaborator.elaborate("architectures/npu_v1_agu_w_half.yaml")

        # 大部分模块应该相同配置
        for mod_id in baseline.modules:
            if mod_id == "agu_w":
                continue
            # 比较 config（不比较运行时状态）
            assert get_config(baseline.modules[mod_id]) == get_config(variant.modules[mod_id])

        # AGU_W 不同
        assert variant.modules["agu_w"]._throughput == 0.5

    def test_invalid_module_type_rejected(self):
        with pytest.raises(UnknownModuleTypeError):
            elaborator.elaborate("tests/fixtures/bad_module_type.yaml")

    def test_port_mismatch_rejected(self):
        # 连接的源 port 不存在
        with pytest.raises(PortNotFoundError):
            elaborator.elaborate("tests/fixtures/bad_connection.yaml")

    def test_circular_clock_rejected(self):
        # 时钟域引用环
        with pytest.raises(CircularReferenceError):
            elaborator.elaborate("tests/fixtures/circular_clock.yaml")

    def test_add_module_works(self):
        arch = elaborator.elaborate("architectures/npu_v1_with_sau.yaml")
        assert "sau" in arch.modules

    def test_remove_module_works(self):
        arch = elaborator.elaborate("architectures/npu_v1_no_tau.yaml")
        assert "tau" not in arch.modules
        # 相关连接也应该被删除（如果用了 remove_connections）

    def test_module_fusion_works(self):
        """MTU = DMA + TAU 融合场景"""
        arch = elaborator.elaborate("architectures/npu_v1_mtu_fused.yaml")
        assert "dma" not in arch.modules
        assert "tau" not in arch.modules
        assert "mtu_fused" in arch.modules
```
