# SPEC-004：Functional Simulation Interface 规范

文档状态：Draft v1.0
作者：架构组
目的：定义数值精度评估管线的接口与契约
依赖：SPEC-001 IModule 接口规范、ADR-001 关键技术决策、ADR-002 模块身份判定

## 1. 目的与范围

定义 NPU 仿真平台的 **functional simulation**（功能 / 数值仿真）子系统的接口与契约。

与 SPEC-002 描述的 **timing simulation**（时序仿真）正交：
- Timing sim 回答："这套架构跑这个 workload **多快、多少 stall、瓶颈在哪里**"
- Functional sim 回答："这套架构跑这个 workload **算得对不对，量化损失多少，是否需要 RNE 而不是 ROUND**"

两个仿真**共用模块身份描述**（IModule.module_type / capability / config），但**不共用执行引擎**：
- Timing sim 用 SystemC TLM-2.0 内核、ITransportPort、IClock
- Functional sim 用纯数值引擎、张量传递、无时钟

## 2. 设计原则

1. **解耦执行**：functional sim 不依赖 SystemC，不依赖 ITransportPort，不依赖 IClock；可独立运行于 Python notebook
2. **共用身份**：每个 `INumericalModel` 必须声明 `for_module_type()` 与某个 IModule 子类配对
3. **可参考可对照**：对每种计算必须能与 reference（如 PyTorch FP32 / NumPy float64）对比
4. **可分级精度**：同一 module type 可注册多个 `INumericalModel`（如 `golden` / `fast` / `bit_accurate`），实验时按需选
5. **配置一致**：functional sim 用与 timing sim 完全相同的 DSL 文件 elaborate 架构，只是切换 engine

## 3. 接口定义

### 3.1 核心接口

```python
# interfaces/numerical.py

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np

# ============================================================
# Tensor 抽象（与 timing sim 的 TransportToken 不同：纯数值）
# ============================================================

@dataclass(frozen=True)
class Tensor:
    """functional sim 内的数据单元。"""
    data: np.ndarray           # 实际数值（任意 numpy 支持的 dtype）
    dtype: "NumericDType"      # 显式类型（INT8 / BFP8 / BFP16 / FP16 / FP32...）
    shape: tuple[int, ...]
    scale: Optional[np.ndarray] = None       # BFP/INT 量化时的 scale
    zero_point: Optional[np.ndarray] = None  # INT 量化的 zero point
    metadata: dict = None                    # 透明传递（op_id, tile_id 等）

class NumericDType(Enum):
    INT4 = "int4"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    FP16 = "fp16"
    BF16 = "bf16"
    FP32 = "fp32"
    BFP8 = "bfp8"       # block float 8
    BFP16 = "bfp16"     # block float 16

# ============================================================
# INumericalModel：每个 IModule 类型的数值模型
# ============================================================

class INumericalModel(ABC):
    """模块的功能 / 数值模型。无副作用、无时序。"""

    # ============== 类级元信息 ==============

    @classmethod
    @abstractmethod
    def for_module_type(cls) -> str:
        """配对的 IModule.module_type() 值。"""
        ...

    @classmethod
    @abstractmethod
    def model_version(cls) -> str:
        """模型实现版本，semver。"""
        ...

    @classmethod
    @abstractmethod
    def fidelity_level(cls) -> "FidelityLevel":
        """精度级别（见 §3.2）。"""
        ...

    @classmethod
    @abstractmethod
    def supported_capabilities(cls) -> list[str]:
        """本数值模型实现了哪些 capability 的功能逻辑。
        必须是配对 IModule.declared_capabilities() 的子集。"""
        ...

    # ============== 生命周期 ==============

    @abstractmethod
    def configure(self, config: dict) -> None:
        """用与配对 IModule 完全相同的 config 初始化。
        必须先经过 IModule.config_schema() 校验。"""
        ...

    @abstractmethod
    def reset(self) -> None:
        """清状态。functional sim 通常无状态，但量化校准 / 累加器需要 reset。"""
        ...

    # ============== 执行（纯函数）==============

    @abstractmethod
    def execute(
        self,
        operation: "IOperation",
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        """执行算子，返回输出。
        约束：
        - 纯函数：相同 inputs 必须返回相同 outputs（除非配置含 stochastic flag）
        - 不能修改 inputs（in-place 操作禁用）
        - 不能持有跨调用状态（reset 之间无关联）"""
        ...

@dataclass(frozen=True)
class FidelityLevel:
    name: str          # "golden" | "bit_accurate" | "fast"
    description: str
    # 例：bit_accurate 复刻硬件 RTL 行为；golden 用 FP32 算后量化；fast 用近似
```

### 3.2 Fidelity Level 规范

| Level | 含义 | 用途 | 性能 |
|---|---|---|---|
| `golden` | 高精度参考实现（FP64 / FP32） | 作为 reference 校准其他级别 | 慢 |
| `bit_accurate` | 与硬件 RTL bit 级一致 | RTL co-sim 之前的最后一关 | 中等 |
| `fast` | 数学近似（如 Taylor 展开 exp） | 大规模实验、快速 sweep | 快 |

同一 `for_module_type()` 可以注册多个 `INumericalModel`，按 `fidelity_level` 区分。Engine 启动时选定一个 level。

### 3.3 数值模型注册机制

```python
# core/numerical_registry.py

class NumericalModelRegistry:
    """functional sim 的数值模型工厂。"""

    _registry: dict[tuple[str, str], type[INumericalModel]] = {}
    # key = (module_type, fidelity_level)

    @classmethod
    def register(cls, model_class: type[INumericalModel]) -> type[INumericalModel]:
        key = (model_class.for_module_type(), model_class.fidelity_level().name)
        if key in cls._registry:
            raise DuplicateNumericalModelError(
                f"Numerical model for {key} already registered"
            )
        cls._registry[key] = model_class
        return model_class

    @classmethod
    def create(
        cls,
        module_type: str,
        fidelity: str,
        config: dict,
    ) -> INumericalModel:
        key = (module_type, fidelity)
        if key not in cls._registry:
            # 优雅降级：fast 不存在时回退到 golden
            if fidelity != "golden" and (module_type, "golden") in cls._registry:
                key = (module_type, "golden")
            else:
                raise UnknownNumericalModelError(key)
        model = cls._registry[key]()
        model.configure(config)
        return model

    @classmethod
    def list_for(cls, module_type: str) -> list[str]:
        """该 module_type 已注册的所有 fidelity_level。"""
        return [fid for (mt, fid) in cls._registry if mt == module_type]
```

### 3.4 Functional Engine

```python
# core/numerical_engine.py

class INumericalEngine(ABC):
    """functional sim 的执行驱动。"""

    @abstractmethod
    def load_architecture(
        self,
        arch: "IArchitecture",
        fidelity: str = "golden",
    ) -> None:
        """从 elaborate 后的架构加载所有模块的数值模型。
        引擎复用同一 DSL，但只实例化 INumericalModel，不实例化 ITransportPort。"""
        ...

    @abstractmethod
    def execute_graph(
        self,
        operations: list["IOperation"],
        initial_tensors: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        """按 op DAG 执行，返回所有输出 tensor。
        engine 内部维护中间 tensor 的传递，无 FIFO、无 backpressure。"""
        ...

    @abstractmethod
    def reset(self) -> None:
        """所有模块 reset。"""
        ...
```

Engine 行为约束：

- 拓扑顺序执行 op DAG（functional sim 是数据流，无 scheduling）
- tensor 传递是直接的 Python 对象引用 + 显式 copy（不可变性靠 dtype 约束保证）
- 不需要 SystemC，不需要 thread，纯单线程执行
- 性能优化在 NumPy / JAX 层做，不在 engine 层

## 4. 与 IModule 的衔接

### 4.1 共用什么

| 项 | 共用方式 |
|---|---|
| `module_type()` | 直接复用，`INumericalModel.for_module_type()` 引用 |
| `module_version()` | functional model 应声明能配合的 IModule version 范围 |
| `config_schema()` | 直接复用，functional model 用同一 schema 校验 |
| `declared_capabilities()` | functional model 的 `supported_capabilities()` 必须是其子集 |
| `IOperation` | 共用，同一 op 既能 timing-execute 也能 numerically-execute |

### 4.2 不共用什么

| 项 | 原因 |
|---|---|
| `IModule.bind_services` | functional sim 无 EventBus / StatSink / Clock |
| `IModule.input_ports` / `output_ports` | functional sim 无 ITransportPort |
| `IModule.estimate_latency` / `estimate_energy` | functional sim 不关心时间 / 能耗 |
| `IModule.snapshot_state` | functional sim 不维护时序状态 |
| `IModule.configure` 中实例化的 pipeline / FIFO 对象 | functional sim 不需要 |

### 4.3 实现建议

绝大多数模块的 functional 行为简洁（一个 numpy 运算就够），不需要分离两套代码。推荐做法：

- 简单算子模块（如 DAGC 解包、VAU 算术）：functional sim 直接写 numpy 代码，与 timing sim 完全独立
- 复杂模块（如 MAC 阵列）：functional sim 用 numpy.einsum 或 torch.matmul，timing sim 用 SystemC pipeline，**不共享代码**
- 量化敏感模块（如 MU、AVP 的 LUT）：必须有 `bit_accurate` fidelity，复刻硬件查表 / 舍入逻辑

代码共享是反模式，因为：
- timing sim 的 cycle 推进会污染 functional 的纯函数性
- functional sim 的张量整批操作会污染 timing 的逐元素时序
- 两套互相校验的存在本身就是平台价值的一部分

## 5. Reference Model 与比较框架

functional sim 的核心价值在于"与什么比"。

### 5.1 IReferenceModel

```python
class IReferenceModel(ABC):
    """高精度参考实现，通常是 PyTorch FP32 或 NumPy FP64。"""

    @abstractmethod
    def name(self) -> str:
        """如 "pytorch_fp32", "numpy_fp64"."""
        ...

    @abstractmethod
    def execute(
        self,
        operation: IOperation,
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        ...
```

### 5.2 比较器与容忍度

```python
@dataclass(frozen=True)
class Tolerance:
    """单个 tensor 输出的容忍度规范。"""
    rtol: float = 1e-5         # relative tolerance
    atol: float = 1e-8         # absolute tolerance
    max_abs_error: Optional[float] = None
    max_rel_error: Optional[float] = None
    min_cosine_sim: Optional[float] = None       # 用于 embedding / attention
    max_outliers_pct: float = 0.0                # 允许 N% 元素超容忍度

@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    metrics: dict[str, float]                    # 实测的各项 metric
    violations: list["ToleranceViolation"]
    sample_diff: Optional[np.ndarray]            # 抽样 diff，用于 debug

class IComparator(ABC):
    @abstractmethod
    def compare(
        self,
        actual: Tensor,
        reference: Tensor,
        tolerance: Tolerance,
    ) -> ComparisonResult:
        ...
```

### 5.3 Functional Test 流程

```python
def run_functional_test(
    arch: IArchitecture,
    workload: list[IOperation],
    inputs: dict[str, Tensor],
    tolerance: dict[str, Tolerance],   # per output tensor
    reference: IReferenceModel,
    fidelity: str = "bit_accurate",
) -> FunctionalTestReport:

    # 1. NPU functional sim
    npu_engine = NumericalEngine()
    npu_engine.load_architecture(arch, fidelity=fidelity)
    npu_outputs = npu_engine.execute_graph(workload, inputs)

    # 2. Reference
    ref_outputs = {}
    for op in workload:
        ref_outputs.update(reference.execute(op, {**inputs, **ref_outputs}))

    # 3. Compare
    results = {}
    for tensor_name in npu_outputs:
        if tensor_name in tolerance:
            results[tensor_name] = comparator.compare(
                npu_outputs[tensor_name],
                ref_outputs[tensor_name],
                tolerance[tensor_name],
            )

    return FunctionalTestReport(
        arch_name=arch.metadata["name"],
        fidelity=fidelity,
        results=results,
        overall_passed=all(r.passed for r in results.values()),
    )
```

## 6. 使用场景示例

### 6.1 MU 量化：ROUND vs RNE

问题：MU 量化是否需要 RNE 模式？ROUND（truncate）便宜但精度差，RNE 精度好但面积增加。

```yaml
# variants/mu_round.yaml
base: npu_v1.yaml
overrides:
  modules:
    mu:
      config:
        round_mode: ROUND        # vs RNE
```

```python
# 跑 BERT 评估
arch_round = elaborator.elaborate("variants/mu_round.yaml")
arch_rne   = elaborator.elaborate("variants/mu_rne.yaml")

report_round = run_functional_test(arch_round, bert_workload, inputs,
                                    tolerance=bert_tolerance,
                                    reference=pytorch_fp32,
                                    fidelity="bit_accurate")
report_rne   = run_functional_test(arch_rne, bert_workload, inputs,
                                    tolerance=bert_tolerance,
                                    reference=pytorch_fp32,
                                    fidelity="bit_accurate")

# 决策依据：
# - 如果 round 通过容忍度 → 不需要 RNE，节省面积
# - 如果 round 失败、rne 通过 → 需要 RNE
# - 如果都失败 → 量化方案本身有问题，不只是舍入方式
```

### 6.2 BFP8 vs BFP16 精度损失曲线

跑同一 workload 在不同 BFP 配比下：
- `bfp_ratio: 1:0`（全 BFP16）
- `bfp_ratio: 2:1`
- `bfp_ratio: 4:1`
- `bfp_ratio: 1:0`（全 BFP8）

测各自的 task accuracy（如 BERT GLUE 分数），与 FP32 reference 对比，画出精度-性能曲线。Timing sim 给"快多少"，functional sim 给"准多少"，两者结合做决策。

### 6.3 VAU 查表 exp 的精度边界

```python
arch_lut = elaborator.elaborate("variants/vau_lut_exp.yaml")
# config:
#   vau:
#     lut_exp: true
#     lut_exp_size_bytes: 2048    # 2048 个表项

# 测 softmax 输出与 reference 的最大相对误差
report = run_functional_test(arch_lut, softmax_workload, inputs,
                              tolerance={"softmax_out": Tolerance(max_rel_error=1e-3)},
                              reference=pytorch_fp32,
                              fidelity="bit_accurate")
# 失败 → LUT 太小，增加到 4096 再试
```

## 7. 测试规范

每个 `INumericalModel` 子类必须配套以下测试：

```python
class TestDAGCNumerical:

    def test_pairs_with_module_type(self):
        """与 IModule 的 module_type 对应。"""
        assert DAGCGoldenModel.for_module_type() == DAGC.module_type()

    def test_supported_capabilities_is_subset(self):
        """supported_capabilities 是 IModule.declared_capabilities 的子集。"""
        declared = {c.name for c in DAGC.declared_capabilities()}
        supported = set(DAGCGoldenModel.supported_capabilities())
        assert supported.issubset(declared)

    def test_pure_function(self):
        """相同 inputs 多次执行返回相同 outputs。"""
        model = DAGCGoldenModel()
        model.configure(default_config())
        out1 = model.execute(op, inputs)
        out2 = model.execute(op, inputs)
        np.testing.assert_array_equal(out1["out_unpacked"].data,
                                       out2["out_unpacked"].data)

    def test_does_not_mutate_inputs(self):
        """不修改 inputs。"""
        model = DAGCGoldenModel()
        model.configure(default_config())
        inputs_copy = deepcopy(inputs)
        _ = model.execute(op, inputs)
        assert_dicts_equal(inputs, inputs_copy)

    def test_matches_reference_within_tolerance(self):
        """与 reference 对比，在容忍度内。"""
        model = DAGCGoldenModel()
        model.configure(default_config())
        reference = NumpyReferenceModel()

        npu_out = model.execute(op, inputs)
        ref_out = reference.execute(op, inputs)

        result = comparator.compare(
            npu_out["out_unpacked"], ref_out["out_unpacked"],
            tolerance=Tolerance(rtol=1e-6),
        )
        assert result.passed
```

## 8. 与 Timing Simulation 的协同

| 阶段 | Functional | Timing | 目的 |
|---|---|---|---|
| 早期 spike | ✅ 跑 | ❌ | 验证算法可行性、量化方案 |
| 架构 variant 评估 | ✅ 跑 | ✅ 跑 | 同时拿到"准多少"和"快多少" |
| Mapping 调优 | ⚠️ 抽测 | ✅ 跑 | 主要看 timing，functional 用于回归校验 |
| RTL co-sim | ✅ bit_accurate | ✅ AT mode | functional 作为 RTL 的 golden |

**关键约定**：每次架构 variant 评估必须同时输出 functional report + timing report，二者缺一不算完整评估。报告生成时 enforce 这点（缺一则报告标记 INCOMPLETE）。

## 9. 已知限制与未覆盖范围

- **随机性**：本 spec 假设确定性执行。dropout / stochastic rounding 等随机算子需要 seed 控制，写入 v1.1
- **并发**：functional sim 是单线程数据流，不模拟硬件并行造成的非确定性（如 reduce 树不同顺序导致的浮点 nonassociativity）。需要时启用 `fidelity: bit_accurate` 并显式模拟硬件 reduce 顺序
- **分布式**：多 chip / 多 die 的 functional sim 假设网络无损，不模拟通信精度。多 die 训练场景的精度评估留到 v1.1
