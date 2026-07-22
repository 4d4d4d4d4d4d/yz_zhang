# SPEC-012 Trace-Driven 激励(Trace-Driven Stimulus)

文档状态:**v0.1 Draft(实现 + 测试)**
最后更新:2026-07-21
Owners:架构组
派生自:SPEC-001(IModule)、SPEC-002(反压)、SPEC-003(DSL)、
`docs/QEMU-Benchmark-Analysis.md` §3.1
关联决策:借鉴 QEMU"喂真实 guest binary"的精神,把评估激励从合成 token
升级为**真实模型算子序列**。

## 0. 动机

`Producer` 只发合成 token(`for i in range(n_tokens)`,固定大小),评估的
workload = "多少个包、每个多大"。这是抽象流量,不是真实负载。

QEMU 的价值内核是**喂真实二进制**。对标到本平台:应能读一个**算子 trace**
(一串 `matmul(M,K,N); softmax(N); ...`),按真实模型层的算子序列 + shape
驱动仿真。评估对象从"抽象 token 流"升级为"跑 attention layer / MLP block
的真实负载"。

**这是评估可信度的质变**,也是让"全连线芯片"(usecase_chip_full_wired)
跑真实模型的入口。

## 1. TraceProducer 模块

### 1.1 身份 + capability
- `module_type()` = `"TraceProducer"`
- capabilities:`trace_replay`
- 新 IModule 子类(ADR-002):功能与 `Producer` 不同 —— 后者发同质
  token,前者按算子序列发异质 token(每 op 的 size / metadata 由算子 shape
  决定)。

### 1.2 端口
- `out`(OUTPUT, DATA):发出算子 token 流

### 1.3 trace 格式(内联在 config,保持 YAML-driven)

```yaml
config:
  ops:
    - { op_type: matmul,  m: 32, k: 32, n: 32, precision: int8 }
    - { op_type: softmax, n_elements: 256 }
    - { op_type: matmul,  m: 32, k: 32, n: 32, precision: int8 }
  send_rate_cycles_per_token: 1     # 可选,op 之间的最小间隔
  repeat: 1                          # 可选,整个序列重复几遍(模拟多 layer)
```

**为什么内联而非文件**:YAML-driven contract
(`assert_evaluation_is_yaml_driven`)要求评估全部来自 YAML config。内联
`ops` 列表让整个 trace 留在 YAML 里,契约 linter 继续生效;文件路径形式
留 v1.1(§5)。

### 1.4 每个 op → token 的映射
- **token size_bytes**:由算子输出规模推导
  - `matmul(m,k,n)` → 输出 `m × n × precision_bytes`
  - `softmax(n_elements)` / 逐元素 op → `n_elements × 4`(FP32)
  - 缺 shape 字段时回退到 `default_bytes=64`
- **token metadata**:携带 `op_type` / `op_index` / 完整 shape,让下游关心
  的模块(如 MAC 按 shape 估 cycle)能读取。
- **发送节奏**:每个 op token 之间等 `send_rate_cycles_per_token` 拍;
  下游 FIFO 满则阻塞(SPEC-002 反压)。

### 1.5 stage(逐拍可见)
`idle` / `replay_op` / `emit`

### 1.6 area / energy
激励源,不占真实硅面积。`estimate_area()` 返回
`AreaModel(um2=0.0, notes="virtual")`(SPEC-001 v1.1 §3.2.5.3 允许)。

## 2. 内置模型 trace 库(便于直接引用)

提供几个代表性算子序列作为 fixture,使用者可直接照抄:

| 模型层 | 算子序列 |
|---|---|
| **Attention block** | q_proj → k_proj → v_proj → scores(matmul)→ softmax → attn(matmul)→ out_proj |
| **MLP block** | fc1(matmul)→ gelu → fc2(matmul) |
| **Conv layer** | im2col_reshape → matmul → relu |

## 3. 评估口径

TraceProducer 引入后支持:

| 评估 | baseline | variant |
|---|---|---|
| 真实 attention 层 vs 合成流量 | Producer 合成 token | TraceProducer 播 attention 序列 |
| 层数扩展(1 layer vs 4 layer) | `repeat: 1` | `repeat: 4` |
| 精度对真实层的影响 | ops 全 int8 | ops 全 bf16 |

## 4. 测试要求
- Conformance:注册、port_specs、estimate_area=0
- Integration:
  - trace 按序播放,发出的 token 数 == `len(ops) × repeat`
  - 每个 token metadata 带正确的 `op_type` / `op_index`
  - matmul op 的 token size == m×n×precision_bytes
  - 把 TraceProducer 接进全连线芯片(替换 act_src),跑一个 attention
    序列,端到端 valid、sink 收齐所有 op
- YAML-driven contract 全程生效

## 5. v1.1 候选(本版之外)
- trace 文件路径形式(`ops_file: attention.trace`)+ ONNX 图导出器
- op 间依赖(DAG,非纯序列)
- 每 op 携带真实 tensor payload(联动 SPEC-004 functional 校验)
