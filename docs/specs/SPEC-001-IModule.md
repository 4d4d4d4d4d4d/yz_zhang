# SPEC-001：IModule 接口规范

文档状态：Draft v0.1
作者：架构组
目的：定义所有 NPU 宏模块必须实现的统一抽象接口
依赖：ADR-000 平台架构总览

## 1. 目的与范围

定义所有 NPU 宏模块（DAGC、MAC、DSB、VAU、AVP、AGU、TAU、MTU、DMA、OGU、OPSch、MCU 等）必须实现的统一抽象接口。

这是平台最重要的契约之一。所有当前与未来的模块都遵守此契约。Mapper、Architecture Elaborator、Report 等上层组件只通过此接口与模块交互，不依赖具体模块类型。

## 2. 设计原则

- **Liskov 替换**：任何 IModule 子类必须能在不破坏上层行为的前提下替换其他子类
- **自描述**：模块必须自己描述自己的能力、配置、状态，不依赖外部知识
- **无副作用查询**：所有查询方法（can_execute、estimate_latency 等）必须无副作用，可被 Mapper 多次调用
- **配置与状态分离**：configure() 设置静态参数，reset() 清状态，运行时不变配置
- **统一通过 EventBus / StatSink 上报**：模块不直接持有报告对象引用

## 3. 接口定义

### 3.1 核心接口

```python
# interfaces/module.py

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from enum import Enum

# ============================================================
# 辅助类型定义
# ============================================================

@dataclass(frozen=True)
class Capability:
    """模块的一项能力声明。"""
    name: str                    # 唯一标识，如 "bfp16_unpack"
    description: str             # 人类可读描述
    area_cost_um2: float         # 面积代价（平方微米）
    static_power_uw: float       # 静态功耗（微瓦）
    dynamic_energy_pj: float     # 每次激活的动态能耗（皮焦）
    depends_on: list[str] = None # 依赖的其他 capability

@dataclass(frozen=True)
class PortSpec:
    """端口规格。"""
    name: str
    direction: "PortDirection"   # INPUT / OUTPUT
    data_type: "DataType"        # COMMAND / DATA / RESPONSE / CONTROL
    width_bits: int
    fifo_depth: int              # 模块端口侧的 FIFO 深度

class PortDirection(Enum):
    INPUT = "in"
    OUTPUT = "out"

class DataType(Enum):
    COMMAND = "cmd"      # 控制命令
    DATA = "data"        # 数据流
    RESPONSE = "resp"    # 响应
    CONTROL = "ctrl"     # 时序/控制信号

@dataclass(frozen=True)
class ModuleState:
    """模块运行时状态快照（只读，用于 debug/可视化）。"""
    busy: bool
    current_op: Optional[str]
    pipeline_occupancy: dict[str, float]  # 各 pipeline stage 占用率
    internal_fifo_levels: dict[str, int]
    last_stall_reason: Optional[str]

# ============================================================
# 主接口
# ============================================================

class IModule(ABC):
    """所有 NPU 宏模块的抽象基类。"""

    # ============== 类级元信息（不需要实例化）==============

    @classmethod
    @abstractmethod
    def module_type(cls) -> str:
        """模块类型的唯一名称，如 "DAGC"、"MatVecArray"。
        用于 ModuleRegistry 注册和架构描述文件引用。
        约定：PascalCase，全平台唯一。"""
        ...

    @classmethod
    @abstractmethod
    def module_version(cls) -> str:
        """模块实现版本，semver 格式（如 "1.2.3"）。
        重大变更时升 major，新功能升 minor，bug fix 升 patch。
        架构文件可以声明 require_version 强制版本匹配。"""
        ...

    @classmethod
    @abstractmethod
    def config_schema(cls) -> dict:
        """JSON Schema 格式描述本模块的所有配置项。
        包括：
        - 所有 capability flag（boolean）
        - 数值参数（带 min/max/default）
        - 枚举参数（带 enum）
        - 参数间依赖（用 JSON Schema 的 dependencies / allOf）

        示例返回值见 §5。"""
        ...

    @classmethod
    @abstractmethod
    def declared_capabilities(cls) -> list[Capability]:
        """声明本模块支持的所有 capability。
        实际激活哪些由 configure() 决定（基于 config flag）。
        Area/power 报告基于已激活 capability 聚合。"""
        ...

    @classmethod
    @abstractmethod
    def port_specs(cls) -> list[PortSpec]:
        """声明本模块的所有端口。
        Architecture Elaborator 用此校验连接是否合法（端口存在、方向匹配、宽度兼容）。"""
        ...

    # ============== 生命周期 ==============

    @abstractmethod
    def configure(self, config: dict) -> None:
        """从配置字典初始化模块。
        必须先经过 config_schema() 校验。
        实现要点：
        1. 设置 capability flag
        2. 设置数值参数
        3. 实例化内部组件（pipeline、FIFO、状态机）
        4. 注册端口到 transport 层
        5. 注册到 EventBus / StatSink

        configure() 只调用一次。重新配置需要先 destroy() 再创建实例。
        """
        ...

    @abstractmethod
    def bind_services(
        self,
        event_bus: "IEventBus",
        stat_sink: "IStatSink",
        clock: "IClock"
    ) -> None:
        """绑定平台服务。configure() 之前调用。"""
        ...

    @abstractmethod
    def reset(self) -> None:
        """复位运行时状态。pipeline 清空、FIFO 清空、计数器归零。
        配置参数保留。"""
        ...

    @abstractmethod
    def destroy(self) -> None:
        """释放资源。析构前调用。"""
        ...

    # ============== 端口访问 ==============

    @abstractmethod
    def input_ports(self) -> dict[str, "ITransportPort"]:
        """返回所有 INPUT 端口，按名字索引。
        在 configure() 之后可用。"""
        ...

    @abstractmethod
    def output_ports(self) -> dict[str, "ITransportPort"]:
        """返回所有 OUTPUT 端口，按名字索引。"""
        ...

    # ============== 能力查询（Mapper 接口）==============

    @abstractmethod
    def active_capabilities(self) -> list[str]:
        """当前配置下实际激活的 capability 名称列表。
        Mapper 用此判断模块当前能干什么。"""
        ...

    @abstractmethod
    def can_execute(self, operation: "IOperation") -> bool:
        """本模块当前配置下是否能执行某操作。
        无副作用，可重复调用。
        典型实现：检查 operation.required_capabilities 是否都在 active_capabilities 内，
        以及 operation 的 shape/precision 是否在本模块支持范围。"""
        ...

    @abstractmethod
    def estimate_latency(self, operation: "IOperation") -> "LatencyEstimate":
        """估算执行某操作的延迟（不含反压、不含外部等待）。
        返回 LatencyEstimate { min, typical, max, confidence }。
        Mapper 用此做候选模块的初步排序。
        无副作用。"""
        ...

    @abstractmethod
    def estimate_energy(self, operation: "IOperation") -> "EnergyEstimate":
        """估算执行某操作的能耗。无副作用。"""
        ...

    # ============== 运行时状态（debug / 可视化）==============

    @abstractmethod
    def snapshot_state(self) -> ModuleState:
        """返回当前状态快照。只读，不影响运行。
        用于 debug、可视化、checkpoint。"""
        ...

    # ============== 面积 / 功耗 报告 ==============

    def total_area_um2(self) -> float:
        """聚合所有激活 capability 的面积。
        默认实现：sum(cap.area_cost_um2 for cap in active capabilities)。
        子类可覆盖以提供更精确模型（比如 capability 间共享逻辑）。"""
        active = set(self.active_capabilities())
        return sum(
            cap.area_cost_um2
            for cap in self.declared_capabilities()
            if cap.name in active
        )

    def static_power_uw(self) -> float:
        """聚合所有激活 capability 的静态功耗。子类可覆盖。"""
        active = set(self.active_capabilities())
        return sum(
            cap.static_power_uw
            for cap in self.declared_capabilities()
            if cap.name in active
        )
```

### 3.2 辅助接口

```python
@dataclass(frozen=True)
class LatencyEstimate:
    min_cycles: int
    typical_cycles: int
    max_cycles: int
    confidence: float  # 0.0 ~ 1.0

@dataclass(frozen=True)
class EnergyEstimate:
    dynamic_pj: float
    static_pj_per_cycle: float
    confidence: float

class IOperation(ABC):
    """算子描述符。Mapper 把模型解析为 IOperation 列表。"""

    @property
    @abstractmethod
    def op_type(self) -> str: ...

    @property
    @abstractmethod
    def required_capabilities(self) -> list[str]:
        """执行此 op 所需的 capability 名称列表。
        是 Mapper 与 Module 之间的契约语言。"""
        ...

    @property
    @abstractmethod
    def shape_info(self) -> dict: ...

    @property
    @abstractmethod
    def precision(self) -> "Precision": ...
```

## 4. 模块注册机制

```python
# core/module_registry.py

class ModuleRegistry:
    """全局模块工厂。所有 IModule 子类必须注册到此。"""

    _registry: dict[str, type[IModule]] = {}

    @classmethod
    def register(cls, module_class: type[IModule]) -> type[IModule]:
        """装饰器形式注册。"""
        key = module_class.module_type()
        if key in cls._registry:
            existing = cls._registry[key]
            if existing is not module_class:
                raise DuplicateModuleTypeError(
                    f"Module type '{key}' already registered by {existing}"
                )
        cls._registry[key] = module_class
        return module_class

    @classmethod
    def create(cls, module_type: str, config: dict) -> IModule:
        if module_type not in cls._registry:
            raise UnknownModuleTypeError(module_type)

        module_class = cls._registry[module_type]

        # 配置校验
        schema = module_class.config_schema()
        jsonschema.validate(config, schema)

        instance = module_class()
        return instance

    @classmethod
    def list_modules(cls) -> list[str]:
        return list(cls._registry.keys())

# 使用示例
@ModuleRegistry.register
class DAGC(IModule):
    @classmethod
    def module_type(cls) -> str:
        return "DAGC"
    # ...
```

DIP 关键点：

- Architecture Elaborator 永远调用 `ModuleRegistry.create(type_name, config)`
- Elaborator 不 import 任何具体模块类
- 新增模块只需要写一个新的 IModule 子类并加 `@ModuleRegistry.register` 装饰器
- 删除模块同理，不影响 Elaborator

## 5. 完整示例：DAGC 模块

```python
@ModuleRegistry.register
class DAGC(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "DAGC"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "bfp8_unpack_throughput": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 2,
                    "description": "BFP8 解包通路吞吐（元素/cycle）"
                },
                "bfp16_unpack_throughput": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "default": 1
                },
                "bfp_ratio": {
                    "type": "string",
                    "enum": ["2:1", "3:1", "4:1"],
                    "default": "2:1",
                    "description": "BFP8:BFP16 流量配比"
                },
                "support_4bit_reorder": {
                    "type": "boolean",
                    "default": True
                },
                "support_mixed_bfp8_bfp16": {
                    "type": "boolean",
                    "default": True,
                    "description": "支持 BFP8 × BFP16 混合精度乘法的对齐"
                },
                "join_fifo_depth": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 64,
                    "default": 16
                }
            },
            "required": ["bfp8_unpack_throughput", "bfp16_unpack_throughput"]
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="bfp8_unpack",
                description="BFP8 格式解包",
                area_cost_um2=3500.0,
                static_power_uw=12.0,
                dynamic_energy_pj=0.8,
            ),
            Capability(
                name="bfp16_unpack",
                description="BFP16 格式解包",
                area_cost_um2=6200.0,
                static_power_uw=18.0,
                dynamic_energy_pj=1.5,
            ),
            Capability(
                name="bfp8_bfp16_mix",
                description="BFP8 × BFP16 混合精度对齐",
                area_cost_um2=4100.0,
                static_power_uw=8.0,
                dynamic_energy_pj=1.2,
                depends_on=["bfp8_unpack", "bfp16_unpack"]
            ),
            Capability(
                name="int4_reorder",
                description="INT4 数据换序",
                area_cost_um2=2300.0,
                static_power_uw=6.0,
                dynamic_energy_pj=0.5,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="in_packed",
                direction=PortDirection.INPUT,
                data_type=DataType.DATA,
                width_bits=128,
                fifo_depth=8
            ),
            PortSpec(
                name="in_cmd",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4
            ),
            PortSpec(
                name="out_unpacked",
                direction=PortDirection.OUTPUT,
                data_type=DataType.DATA,
                width_bits=256,
                fifo_depth=16
            ),
        ]

    def configure(self, config: dict) -> None:
        self._bfp8_tp = config["bfp8_unpack_throughput"]
        self._bfp16_tp = config["bfp16_unpack_throughput"]
        self._bfp_ratio = self._parse_ratio(config["bfp_ratio"])
        self._support_4bit = config.get("support_4bit_reorder", True)
        self._support_mix = config.get("support_mixed_bfp8_bfp16", True)
        self._join_fifo_depth = config.get("join_fifo_depth", 16)

        # 计算激活的 capability
        self._active_caps = ["bfp8_unpack", "bfp16_unpack"]
        if self._support_mix:
            self._active_caps.append("bfp8_bfp16_mix")
        if self._support_4bit:
            self._active_caps.append("int4_reorder")

        # 实例化内部组件
        self._bfp8_pipe = UnpackPipeline(throughput=self._bfp8_tp)
        self._bfp16_pipe = UnpackPipeline(throughput=self._bfp16_tp)
        self._join_fifo = Fifo(depth=self._join_fifo_depth)

        # 创建端口
        self._ports = self._create_ports()

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        required = set(operation.required_capabilities)
        return required.issubset(set(self._active_caps))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # 基于 shape 和 precision 的简单估算
        n_elements = operation.shape_info["n_elements"]
        if operation.precision.is_bfp8():
            cycles = n_elements // self._bfp8_tp
        elif operation.precision.is_bfp16():
            cycles = n_elements // self._bfp16_tp
        elif operation.precision.is_mixed_bfp8_bfp16():
            # 混合模式：瓶颈在慢的那条通路
            bfp16_part = n_elements * self._bfp_ratio.bfp16_share
            cycles = int(bfp16_part / self._bfp16_tp)
        else:
            cycles = 0  # 不支持

        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=int(cycles * 1.1),  # 经验加 10% 反压
            max_cycles=int(cycles * 1.5),
            confidence=0.7
        )

    # ... 其他方法
```

## 6. 测试用例规范

每个 IModule 子类必须配套以下测试：

```python
# tests/unit/test_dagc.py

class TestDAGC:

    def test_module_type_unique(self):
        """module_type 全平台唯一。"""
        assert DAGC.module_type() == "DAGC"

    def test_config_schema_valid(self):
        """config_schema 本身是合法的 JSON Schema。"""
        jsonschema.Draft7Validator.check_schema(DAGC.config_schema())

    def test_default_config_validates(self):
        """默认配置能通过 schema 校验。"""
        # 从 schema 中提取默认值
        default_config = extract_defaults(DAGC.config_schema())
        jsonschema.validate(default_config, DAGC.config_schema())

    def test_invalid_config_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            invalid = {"bfp8_unpack_throughput": 99}  # 超出 max
            jsonschema.validate(invalid, DAGC.config_schema())

    def test_capability_dependencies(self):
        """声明的 capability 依赖关系自洽。"""
        caps = DAGC.declared_capabilities()
        names = {c.name for c in caps}
        for c in caps:
            if c.depends_on:
                for dep in c.depends_on:
                    assert dep in names

    def test_can_execute_consistency(self):
        """can_execute 与 active_capabilities 一致。"""
        m = DAGC()
        m.configure(default_config())
        op = MockOperation(required_caps=["bfp8_unpack"])
        assert m.can_execute(op) == (
            set(op.required_capabilities).issubset(set(m.active_capabilities()))
        )

    def test_area_aggregation(self):
        """面积报告等于激活 capability 的面积之和。"""
        m = DAGC()
        m.configure(default_config())
        expected = sum(
            cap.area_cost_um2 for cap in DAGC.declared_capabilities()
            if cap.name in m.active_capabilities()
        )
        assert m.total_area_um2() == expected

    def test_estimate_latency_no_side_effect(self):
        """estimate_latency 多次调用结果一致。"""
        m = DAGC()
        m.configure(default_config())
        op = make_test_op()
        e1 = m.estimate_latency(op)
        e2 = m.estimate_latency(op)
        assert e1 == e2

    # ... 端口测试、反压测试、状态机测试见 SPEC-002
```

## 7. 模块 spec 文档模板

每个具体模块都要写一份 `docs/module_specs/<module>.md`，结构如下：

```markdown
# Module Spec: <ModuleName>

## 1. 功能定位
本模块在 NPU 数据流中的角色、与上下游的关系。

## 2. Capability 清单
表格列出所有 declared_capabilities，每项包括：
- name / description
- area / power
- 影响哪些算子 / 哪些场景需要
- 删除影响（如果删了会怎样）

## 3. 配置项
表格列出 config_schema 的所有项，每项包括：
- 类型 / 取值范围 / 默认值
- 含义 / 影响
- 与其他配置项的依赖

## 4. 端口
表格列出所有端口的规格和典型连接。

## 5. 内部状态机
画状态转换图，描述每个状态的语义。

## 6. 流水线时序
画 pipeline 图，标出各 stage 的 latency。

## 7. 反压行为
- 上游端口何时反压
- 下游反压时本模块如何响应
- 内部资源冲突的处理

## 8. 已知限制 / 假设
仿真模型的简化和未建模的细节。

## 9. 校准记录
与硬件实测的对比数据。
```
