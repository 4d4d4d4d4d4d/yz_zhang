# SPEC-001 v1.1 增订 — Area 维度 + Clock Domain

文档状态：**v1.1 Draft（amendment to SPEC-001 v1.0 Accepted — Review pending）**
最后更新：2026-06-04
Owners：架构组
派生自：SPEC-001 v1.0 §3
背景:用户 2026-06-04 评估需求(UNPACK 面积优化 / 提频 / DAGC 外置 10%
代价)无法在 v1.0 契约下表达,本增订**只新增、不破坏**v1.0 已 Accepted 的
任何接口。

## 1. 动机

v1.0 IModule `estimate_*` 接口只有:

```python
estimate_latency(op) -> LatencyModel
estimate_energy(op)  -> EnergyModel
```

下列评估问题无法回答:

| 评估问题 | v1.0 缺什么 |
|---|---|
| "UNPACK 格式面积优化省多少 mm²?" | 没有 area 维度 |
| "DAGC 外置 10% 代价"——10% 是指 area 还是 power 还是两者? | 同上 |
| "提频对能效的影响" | 每个模块没有独立 clock_domain,SimpleClock 是全局的 |
| "MCU/OGU 分别多少面积?" | SPEC-007 §1.4 强制要求,但没有契约支撑 |

## 2. 增订内容

### §3.2.5(新增)`estimate_area() -> AreaModel`

```python
@dataclass(frozen=True)
class AreaModel:
    um2: float                          # 总面积,平方微米
    breakdown: Mapping[str, float] = MappingProxyType({})
                                        # 可选:logic/sram/io 等分项
    notes: str = ""                     # 例如 "[calibration knob]"

class IModule(ABC):
    ...
    @abstractmethod
    def estimate_area(self) -> AreaModel:
        """Return the static silicon area estimate for this module.

        Unlike estimate_latency/energy, area does not depend on op — it is
        a property of the configured module instance. Returning an
        AreaModel with um2=0.0 is allowed only for purely virtual modules
        (e.g., probe modules in tests).
        """
```

- **§3.2.5.1** Area 是 **per-instance** 属性,不依赖 op。
- **§3.2.5.2** `evaluation.SimulationResult` 新增 `total_area_um2` 字段
  (Σ over instantiated modules);`compare()` 报告中加入
  `area_delta_um2` / `area_delta_pct`。
- **§3.2.5.3** 测试 fixture / probe 模块允许返回 `um2=0.0`,但必须显式
  标 `notes="virtual"`。
- **§3.2.5.4 兼容性** 已存在的 v1.0 模块若未实现 `estimate_area()`,平台
  应提供默认实现 raise `NotImplementedError`,**并在 elaborator 发
  warning(不 fail)**——这是为了让 v1.1 渐进落地,不阻塞现存代码。

### §3.1.x(新增)`clock_domain` 配置字段

`IModule.configure(config)` 的 config 字典新增**可选**字段:

```yaml
modules:
  mac_0:
    type: MAC
    config:
      clock_domain: "compute_high"   # 默认 "global"
```

- **§3.1.x.1** Elaborator(SPEC-003 §5 Phase 2)读到 `clock_domain` 时,
  在 ServiceBus 上为该 domain 注入一个 `IClock` 实例;模块通过
  `bind_services(services)` 取到的 clock 即是其 domain clock。
- **§3.1.x.2** SPEC-003 §3 新增可选顶层节 `clock_domains:`(见 SPEC-003
  v1.1 增订),按 domain 配置频率;未声明的 domain 退化到 `global`。
- **§3.1.x.3** Cross-Domain transport 仍走 SPEC-002 §5.1 CDC 既有契约,
  本增订不动 CDC 规则。
- **§3.1.x.4** `estimate_energy(op)` 实现应使用**模块自己 domain 的频率**
  计算能耗(`energy = active_cycles × power_W / freq_hz`),否则提频
  评估失真。

## 3. 不变量补充

- **§7.x(SPEC-002 不变量补充)** 仿真结束时:
  `Σ module.estimate_area().um2 == arch.total_area_um2`,
  否则视为 elaborator bug。

## 4. 影响面

| 文件 / 模块 | 改动 |
|---|---|
| `npu_sim/interfaces/imodule.py` | 加 `AreaModel`、`estimate_area()` abstract,带默认 NotImpl |
| `npu_sim/architecture/elaborator.py` | Phase 2 注入 per-domain clock;Phase 9 汇总 total_area |
| `npu_sim/evaluation/runner.py` | `SimulationResult.total_area_um2` |
| `npu_sim/evaluation/comparator.py` | `area_delta_um2/pct` |
| 所有现存模块(DAGC/DSB/MAC/VAU/AVP/dummy/probe) | 实现 `estimate_area()`,probe 返回 `um2=0.0, notes="virtual"` |
| SPEC-005 | v1.1 增订加 area 系数(见 SPEC-005-v1.1-amendment.md) |

## 5. v1.1 候选(本增订之外)

- 多电压域(DVFS)模型 → v1.2。
- Thermal model → v1.2(area 已有,thermal 需要 floorplan)。
