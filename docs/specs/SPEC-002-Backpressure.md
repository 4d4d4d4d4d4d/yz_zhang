# SPEC-002：反压协议规范

文档状态：Draft v0.2
作者：架构组
目的：定义模块间数据传输的反压协议、stall 上报机制、反压链追溯算法
依赖：SPEC-001 IModule 接口规范

v0.2 变更：
- §3.3 增加 BackpressureTracer 实时/离线模式说明（R6#5）
- 新增 §3.4 多生产者反压归因（R6#2）
- 新增 §5.1 跨时钟域传输（CDC，R6#3）
- 新增 §7 仿真不变量检查（R6#6）

## 1. 目的与范围

定义模块间数据传输的反压协议、stall 上报机制、反压链追溯算法。

这是平台的核心机制。反压保真度决定了仿真器评估"砍某模块带宽"这类决策的可信度。本 spec 必须严格执行，任何模块开发者都不能绕过。

## 2. 设计原则

1. **反压自动传播**：模块开发者不写显式反压逻辑，通过正确使用 ITransportPort 自然产生
2. **反压可追溯**：任何 stall 必须能回溯到根本原因模块
3. **零数据丢失**：反压时数据必须等待，不能丢弃（除非显式声明的 lossy port）
4. **时间精确**：反压传播延迟必须 cycle 精确，不能用粗粒度近似
5. **可观测**：所有反压事件自动统计，不需要模块开发者手动埋点

## 3. ITransportPort 语义

### 3.1 接口定义

```python
# interfaces/transport.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable

class TransportStatus(Enum):
    OK = "ok"
    BACKPRESSURE = "backpressure"  # 下游满，需要等待
    ERROR = "error"
    TIMEOUT = "timeout"

@dataclass(frozen=True)
class TransportToken:
    """传输单元。承载实际数据 / 命令。"""
    payload: bytes | dict        # 数据 or 命令
    size_bytes: int              # 用于带宽统计
    metadata: dict               # 透明传递的元数据（op_id, tile_id 等）
    timestamp_ps: int            # 产生时间，用于追溯
    source_module: str           # 谁产生的，用于追溯

@dataclass(frozen=True)
class TransportResult:
    status: TransportStatus
    accepted_at_ps: Optional[int] = None   # 被接收时刻
    stall_duration_ps: int = 0             # 等待了多久
    stall_cause_module: Optional[str] = None  # 谁让我等的

class ITransportPort(ABC):
    """模块端口。所有模块间通信都通过此接口。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def direction(self) -> "PortDirection": ...

    @property
    @abstractmethod
    def owner_module(self) -> str:
        """归属哪个模块。用于反压追溯。"""
        ...

    # ============== OUTPUT port 使用的方法 ==============

    @abstractmethod
    def send(self, token: TransportToken) -> TransportResult:
        """阻塞发送。等待下游 ready，返回时表示已被接收。
        反压在此处自动产生：
        - 检查下游 input FIFO 是否有空间
        - 没有空间时挂起当前模块，等待下游 notify
        - 被唤醒后再次尝试，直到成功
        - 自动调用 IStatSink.record_stall() 上报 stall

        使用模式：output port 在模块内部 pipeline 完成时调用。
        """
        ...

    @abstractmethod
    def try_send(self, token: TransportToken) -> TransportResult:
        """非阻塞发送。下游忙立即返回 BACKPRESSURE，不等待。
        模块可基于此实现自己的重试/丢弃策略。"""
        ...

    @abstractmethod
    def ready_to_send(self) -> bool:
        """查询下游当前是否能接收。无副作用。"""
        ...

    # ============== INPUT port 使用的方法 ==============

    @abstractmethod
    def on_receive(
        self,
        handler: Callable[[TransportToken], "ReceiveResult"]
    ) -> None:
        """注册接收回调。
        handler 必须返回 ReceiveResult，表示：
        - ACCEPTED：本周期接受
        - DEFERRED(n_cycles)：本周期忙，n cycle 后再来
        - REJECTED：永久拒绝（罕见，仅用于格式错误）"""
        ...

    @abstractmethod
    def fifo_level(self) -> int:
        """当前 input FIFO 占用量。"""
        ...

    @abstractmethod
    def fifo_capacity(self) -> int:
        """input FIFO 总容量。"""
        ...

@dataclass(frozen=True)
class ReceiveResult:
    decision: "ReceiveDecision"
    defer_cycles: int = 0
    reject_reason: str = ""

class ReceiveDecision(Enum):
    ACCEPTED = "accepted"
    DEFERRED = "deferred"
    REJECTED = "rejected"
```

### 3.2 send() 的语义详解

```
send() 调用流程：

  Module A                  Port (out)              Port (in)            Module B
    |                          |                       |                    |
    | send(token) ----------> |                       |                    |
    |                          | -- check ready ----> |                    |
    |                          |                       | -- fifo full? -- |
    |                          |                       |                    |
    |         CASE 1: FIFO has space                                       |
    |                          |  <-- READY -------- |                    |
    |                          | -- enqueue -------> |                    |
    |                          | <-- ACK ----------- |                    |
    |  <- OK, 0 stall -------- |                       |                    |
    |                                                                       |
    |         CASE 2: FIFO full                                            |
    |                          | <-- BACKPRESSURE -- |                    |
    | (A 挂起，等待 notify)                                                  |
    |                          |   ...等待...           |                    |
    |                          |                       | (B 消费一个 token)|
    |                          | <-- READY notify --- |                    |
    |                          | -- enqueue -------> |                    |
    |                          | <-- ACK ----------- |                    |
    |  <- OK, stall_ps=N ----- |                       |                    |
    |  (stall 自动上报到 StatSink)                                          |
```

实现要点：

- `send()` 在反压时不消耗 cycle，调用模块挂起，仿真时间不前进
- 反压结束时，调用模块在下一个有效 cycle 被唤醒
- `stall_duration_ps` = 唤醒时间 - 挂起时间
- `stall_cause_module` = 下游模块（造成 FIFO 满的人）

### 3.3 反压追溯（最关键的部分）

```python
# core/services/backpressure_tracer.py

class BackpressureTracer:
    """反压链追溯器。订阅所有 stall 事件，构建因果图。"""

    def __init__(self, event_bus: IEventBus):
        self._stall_events: list[StallEvent] = []
        event_bus.subscribe("stall.*", self._on_stall)

    def _on_stall(self, event: dict) -> None:
        self._stall_events.append(StallEvent(
            time_ps=event["time_ps"],
            stalled_module=event["module"],
            reason=event["reason"],
            duration_ps=event["duration_ps"],
            caused_by_module=event.get("caused_by"),
        ))

    def trace_chain(self, end_module: str, time_window_ps: tuple[int, int]) -> "StallChain":
        """从某模块某时间段的 stall 出发，回溯反压链。

        算法：
        1. 找到 end_module 在时间窗口内的所有 stall 事件
        2. 对每个 stall，沿 caused_by 链向上追溯
        3. 在追溯链上聚合 stall duration
        4. 返回 DAG 结构的反压链

        终止条件：
        - 找到根源（caused_by 为 None，即模块内部资源冲突）
        - 链长度超过 max_depth（防止环路）
        - 时间超出窗口
        """
        ...

@dataclass
class StallChain:
    """反压链 DAG。"""
    root_causes: list["StallCause"]       # 根源模块
    chain_links: list["ChainLink"]        # 链上每一跳
    total_stall_time_ps: int
    bottleneck_module: str                # 总贡献最大的模块

@dataclass
class StallCause:
    module: str
    reason: str                            # "internal_resource" | "fifo_overflow_propagation"
    contribution_ps: int                   # 在 chain 总 stall 中的贡献
    percentage: float
```

反压链示例：

```
MAC stall 1000 cycles
  ├─ caused_by: DSB (read_port busy)
  │   DSB stall 800 cycles
  │     ├─ caused_by: DAGC (output FIFO full propagation)
  │     │   DAGC stall 800 cycles
  │     │     └─ caused_by: <internal>  (bfp16_pipe throughput limit)  [ROOT CAUSE]
  │     │         contribution: 800 ps (80%)
  │     └─ caused_by: <internal> (bank conflict)
  │         contribution: 200 ps (20%)
  └─ caused_by: <internal> (none, MAC waiting for both operands)
```

这告诉用户：真正的瓶颈是 DAGC 的 bfp16 通路，不是 MAC 也不是 DSB。这正是评估"AGU-W 减半"、"BFP 4:1"这类决策需要的信息。

### 3.3.1 Tracer 运行模式

BackpressureTracer 支持两种模式，由构造参数决定，运行时不可切换：

| 模式 | 数据源 | 触发时机 | 典型用途 |
|---|---|---|---|
| **Realtime** | 订阅 EventBus `stall.*` topic | 仿真过程中实时增量更新 | 长时间仿真早期发现瓶颈、可视化面板 |
| **Offline** | 扫描 IStatSink 持久化历史记录 | 仿真结束后批量分析 | 报告生成、回归对比、CI 校验 |

```python
class BackpressureTracer:
    def __init__(self, mode: TracerMode, source: Union[IEventBus, IStatSink]):
        self._mode = mode
        if mode == TracerMode.REALTIME:
            assert isinstance(source, IEventBus)
            source.subscribe("stall.*", self._on_stall)
        else:  # OFFLINE
            assert isinstance(source, IStatSink)
            self._stall_events = source.load_stall_history()
```

约束：
- Realtime 模式下 `trace_chain()` 反映"截至当前仿真时间"的状态，可能在仿真进行中
- Offline 模式下 `trace_chain()` 反映完整仿真结果，不会变化
- 两种模式必须对同一组事件返回相同的 StallChain（这是测试要点）

### 3.4 多生产者反压归因

当多个 producer 向同一 sink 写入（典型场景：vau / mac / mtu / tau 都往 dsb 写），单点 `caused_by` 字段不足以揭示真相：

```
A ──┐
B ──┼─→ S   S 的 internal_resource_conflict
C ──┘
```

A、B、C 各自看到的 `caused_by = S`，但真正的瓶颈可能是"A 和 C 同时申请同一 bank"。需要从 sink 侧反向追溯所有 contender。

```python
@dataclass
class MultiProducerContention:
    """sink 侧的 producer 竞争记录。"""
    sink_module: str
    time_window_ps: tuple[int, int]
    producers: list["ProducerActivity"]
    bottleneck_resource: str           # 如 "bank_3"
    total_contention_ps: int

@dataclass
class ProducerActivity:
    producer_module: str
    n_requests: int
    accepted_count: int
    rejected_count: int
    stall_ps_contributed: int          # 此 producer 给 sink 带来的 stall 时间

class BackpressureTracer:
    def trace_multi_producer_contention(
        self,
        sink_module: str,
        time_window_ps: tuple[int, int],
    ) -> list[MultiProducerContention]:
        """从 sink 侧反向追溯多 producer 竞争。

        算法：
        1. 找到 sink_module 在窗口内所有 INTERNAL_RESOURCE_CONFLICT stall
        2. 对每个 stall，查询 details.conflict_resource（bank / port / 信道）
        3. 沿事件流反查同时间窗口内向该资源发起请求的所有 producer
        4. 按 producer 聚合，计算各自贡献的 stall 时间
        """
        ...
```

归因递归规则（写入 BackpressureTracer 标准行为）：

- 若 `caused_by` 模块自身有 `INTERNAL_RESOURCE_CONFLICT`，自动调用 `trace_multi_producer_contention` 展开
- 展开结果作为 StallChain 上一个节点的子节点（DAG 而非纯链）
- 报告中"窗口内主要 caused_by" = 各 producer 贡献 stall 时间排序的 Top-N

### 3.5 自动上报合法性约束

平台必须拒绝以下非法 stall 上报组合（StatSink 在 `record_stall` 入口校验）：

| reason | caused_by | 是否合法 | 处理 |
|---|---|---|---|
| `OUTPUT_FULL` | None | ❌ | raise `InvalidStallReport` |
| `OUTPUT_BANDWIDTH` | None | ❌ | raise `InvalidStallReport` |
| `INPUT_EMPTY` | None | ⚠️ warn | 通常应能填上游 module，None 仅在 root source 模块允许 |
| `INTERNAL_*` | not None | ❌ | raise `InvalidStallReport` |
| `CAPABILITY_MISSING` | any | ❌ | 不该到这，raise `MapperBugError` |
| `WAITING_FOR_*` | None | ❌ | raise `InvalidStallReport` |

理由：`caused_by` 是反压链追溯的根，破坏其语义会使链断裂。CI lint 校验所有 `record_stall` 调用点，违反规则不允许合入。

## 4. Stall 分类与上报

### 4.1 Stall 类型

```python
class StallReason(Enum):
    # === 输入相关 ===
    INPUT_EMPTY = "input_empty"
        # 等待上游数据
    INPUT_PARTIAL = "input_partial"
        # 需要多个 input 同时到达，部分到达

    # === 输出相关 ===
    OUTPUT_FULL = "output_full"
        # 下游 FIFO 满，反压
    OUTPUT_BANDWIDTH = "output_bandwidth"
        # 下游带宽不足

    # === 内部资源 ===
    INTERNAL_RESOURCE_CONFLICT = "internal_resource_conflict"
        # 例：DSB bank conflict、AGU port 抢占
    INTERNAL_PIPELINE_HAZARD = "internal_pipeline_hazard"
        # 例：MAC 累加器写回冲突
    INTERNAL_CAPACITY = "internal_capacity"
        # 例：内部 FIFO 满、寄存器堆耗尽

    # === 配置/能力 ===
    CAPABILITY_MISSING = "capability_missing"
        # 不该到这，到了说明 Mapper 有 bug
    PRECISION_MISMATCH = "precision_mismatch"
        # 例：DAGC 收到不支持的精度组合

    # === 外部 ===
    WAITING_FOR_COMMAND = "waiting_for_command"
        # 等 OGU / OPSch 发指令
    WAITING_FOR_SYNC = "waiting_for_sync"
        # 等同步信号（barrier、event）
```

### 4.2 上报规范

模块不要直接调用 `record_stall`。Stall 由 ITransportPort 在反压时自动上报。模块只需要在以下场景额外上报：

```python
# 内部资源冲突：模块自己上报
def _on_bank_conflict(self):
    self._stat_sink.record_stall(
        module=self.module_id,
        reason=StallReason.INTERNAL_RESOURCE_CONFLICT,
        duration_ps=self._clock.period_ps,
        caused_by=None,  # 内部，无外部原因
        details={"conflict_bank": bank_id, "n_requesters": n}
    )

# 等待命令：等待时上报
def _wait_for_command(self):
    start = self._clock.current_time_ps()
    while not self._cmd_queue.has_pending():
        self._clock.wait_cycles(1)
    duration = self._clock.current_time_ps() - start
    if duration > 0:
        self._stat_sink.record_stall(
            module=self.module_id,
            reason=StallReason.WAITING_FOR_COMMAND,
            duration_ps=duration,
            caused_by="OGU",  # 命令来源
        )
```

### 4.3 反压在 ITransportPort 内部的自动上报

```python
# core/services/tlm_transport.py

class TlmTransportPort(ITransportPort):

    def send(self, token: TransportToken) -> TransportResult:
        send_start_ps = self._clock.current_time_ps()

        # 检查下游 ready
        while not self._downstream_port.can_accept():
            # 反压发生
            self._wait_for_downstream_notify()

        # 实际传输
        self._downstream_port.enqueue(token)
        send_end_ps = self._clock.current_time_ps()

        stall_duration = send_end_ps - send_start_ps

        if stall_duration > 0:
            # 自动上报 stall
            self._stat_sink.record_stall(
                module=self.owner_module,
                reason=StallReason.OUTPUT_FULL,
                duration_ps=stall_duration,
                caused_by=self._downstream_port.owner_module,  # 关键：下游归因
                details={
                    "port": self.name,
                    "downstream_port": self._downstream_port.name,
                    "downstream_fifo_level": self._downstream_port.fifo_level(),
                    "downstream_fifo_capacity": self._downstream_port.fifo_capacity(),
                }
            )

        return TransportResult(
            status=TransportStatus.OK,
            accepted_at_ps=send_end_ps,
            stall_duration_ps=stall_duration,
            stall_cause_module=self._downstream_port.owner_module if stall_duration > 0 else None,
        )
```

这是反压追溯的根：每次反压都自动留下 `caused_by` 痕迹，BackpressureTracer 沿着这些痕迹就能还原完整链。

## 5. FIFO 与连接

```python
# interfaces/transport.py

@dataclass(frozen=True)
class ConnectionSpec:
    """连接规格。在架构 DSL 中描述，由 Elaborator 实例化。"""
    source_module: str
    source_port: str
    sink_module: str
    sink_port: str
    fifo_depth: int          # 连接上的 FIFO 深度（与端口内部 FIFO 串联）
    latency_cycles: int      # 连线物理延迟（线长）
    bandwidth_gbps: float    # 物理带宽上限

class IConnection(ABC):
    """模块间连接的实体。"""

    @abstractmethod
    def spec(self) -> ConnectionSpec: ...

    @abstractmethod
    def current_in_flight(self) -> int:
        """正在 FIFO 中传输的 token 数。"""
        ...

    @abstractmethod
    def utilization(self) -> float:
        """带宽利用率。"""
        ...
```

关键设计：

- 连接上的 FIFO 是真实存在的存储，不是抽象概念
- 反压感知到的"下游 FIFO 满" = 连接 FIFO 满 OR 下游模块 input FIFO 满（两者串联）
- `latency_cycles` 模拟物理线延迟，token 入队后要等 latency 才到达下游

### 5.1 跨时钟域传输（CDC）

当 source 和 sink 的 `IClock.domain_id` 不同时，连接自动成为跨时钟域连接（CDC）。Elaborator 在 Phase 6 建立连接时检测并插入异步 CDC FIFO，无需 DSL 显式声明。

#### 5.1.1 CDC FIFO 行为

```python
@dataclass(frozen=True)
class CdcConnectionSpec(ConnectionSpec):
    """跨时钟域连接的扩展规格。继承自 ConnectionSpec。"""
    source_domain: str
    sink_domain: str
    sync_stages: int = 2              # 同步器级数（典型 2，可配置 3 增加 MTBF）
    async_fifo_depth: int = 8         # 异步 FIFO 深度，须 >= max(source_freq, sink_freq) / min(...)
    metastability_model: str = "none" # "none" | "statistical"
```

#### 5.1.2 CDC 增加的延迟与 stall

| 方向 | 额外延迟（cycle） | 计算基准 |
|---|---|---|
| Source domain → CDC FIFO 入口 | 0 | 在 source 域 |
| CDC FIFO 内同步 | `sync_stages + 1` | 按 **sink 域**周期计 |
| CDC FIFO → Sink | 0 | 在 sink 域 |
| **总额外延迟** | `(sync_stages + 1) × sink_period_ps` | |

例：main_clk (1GHz, 1000ps) → ctrl_clk (0.5GHz, 2000ps)，sync_stages=2 → 跨域额外 `3 × 2000ps = 6ns`。

#### 5.1.3 跨域 stall 的归因

跨域 FIFO 满引发反压时，`caused_by` 字段仍指向下游模块，但 `details` 必须包含跨域信息：

```python
self._stat_sink.record_stall(
    module=self.owner_module,
    reason=StallReason.OUTPUT_FULL,
    duration_ps=stall_duration,
    caused_by=self._downstream_port.owner_module,
    details={
        "port": self.name,
        "downstream_port": self._downstream_port.name,
        "cross_domain": True,                          # ← 关键标记
        "source_domain": self._source_clock.domain_id,
        "sink_domain": self._sink_clock.domain_id,
        "cdc_fifo_level": self._cdc_fifo.level(),
        "cdc_fifo_capacity": self._cdc_fifo.capacity(),
    }
)
```

BackpressureTracer 在生成报告时，跨域链路单独着色，避免与同域反压链混淆。

#### 5.1.4 Elaborator 校验

Phase 3 语义校验时：

- 跨域连接的 `async_fifo_depth` 必须 ≥ 4，否则警告（深度过小易死锁）
- 慢域 → 快域：警告但允许（快域空闲多）
- 快域 → 慢域：必须显式声明 `async_fifo_depth` ≥ `ceil(source_freq / sink_freq) × burst_len`，否则 error

## 6. 反压协议测试规范

每个模块都必须通过以下反压测试：

```python
# tests/integration/test_backpressure.py

class BackpressureTestSuite:
    """所有模块的反压行为通用测试。"""

    def test_output_backpressure_propagates(self, module_under_test):
        """下游 stub 不收数据，模块应自然 stall，不丢数据。"""
        module = module_under_test
        downstream_stub = NeverAcceptStub()
        connect(module.output_ports()["out"], downstream_stub.input_port)

        # 发足够多的输入，让模块产生输出
        send_inputs(module, n=100)
        run_simulation(cycles=1000)

        # 验证：
        assert downstream_stub.received_count() == 0  # 没收到
        assert module.snapshot_state().busy            # 模块在 stall
        stats = get_stats(module.module_id)
        assert stats.stall_count > 0
        assert stats.stall_reason_breakdown[StallReason.OUTPUT_FULL] > 0

    def test_input_backpressure_received(self, module_under_test):
        """上游高速发送，模块处理慢时应正确反压上游。"""
        module = module_under_test
        upstream_stub = FastSendStub(rate=100)  # 远超模块处理速度
        connect(upstream_stub.output_port, module.input_ports()["in"])

        downstream_consumer = FastConsumeStub()
        connect(module.output_ports()["out"], downstream_consumer.input_port)

        run_simulation(cycles=1000)

        # 验证：upstream 应经历 stall
        upstream_stats = get_stats(upstream_stub.module_id)
        assert upstream_stats.stall_reason_breakdown[StallReason.OUTPUT_FULL] > 0
        # caused_by 应指向 module_under_test
        backpressure_chain = trace_chain(upstream_stub.module_id)
        assert module_under_test.module_id in backpressure_chain.modules

    def test_no_data_loss_under_backpressure(self, module_under_test):
        """长时间反压后所有数据最终都被处理。"""
        # ... 类似上面，发 N 个 token，反压一段时间，最后验证 received == N

    def test_stall_attribution_correct(self):
        """三模块链 A→B→C，C 不消费，应观察到完整反压链。"""
        # B.stall caused_by C
        # A.stall caused_by B
        # trace_chain(A) 应包含 [A, B, C]，root_cause = C
```

## 7. 仿真不变量检查（Invariant Check）

每次仿真结束（无论成功还是异常退出），平台自动运行不变量检查。任何一项不通过，仿真结果标记为 `INVALID`，报告必须显著标注，**不允许参与决策评估**。

### 7.1 必查不变量

| ID | 不变量 | 检查方式 | 失败处理 |
|---|---|---|---|
| INV-1 | 所有 input token 都被消费 | `sum(producer.sent) == sum(consumer.received)` | INVALID + dump diff |
| INV-2 | 所有 in-flight token 已到达目的地 | `for conn: conn.current_in_flight() == 0` | INVALID + 列出残留 |
| INV-3 | 无死锁 | 仿真结束时无任何 SC_THREAD 处于 BACKPRESSURE 挂起 | INVALID + dump 挂起 thread |
| INV-4 | 反压链无环 | BackpressureTracer 构图后做拓扑排序 | INVALID + 输出环路 |
| INV-5 | 时间单调推进 | 所有 stall 事件 `time_ps` 序列单调非降 | INVALID（应是平台 bug） |
| INV-6 | `caused_by` 引用合法 | 每个非空 `caused_by` 指向架构中存在的 module id | INVALID + 列出非法引用 |
| INV-7 | 资源不超额 | 所有 FIFO `level <= capacity` 在任意时刻成立 | INVALID（应是平台 bug） |

### 7.2 推荐不变量（warn，不 INVALID）

| ID | 不变量 | 触发条件 |
|---|---|---|
| INV-W1 | 反压链不超过 depth 8 | 链过深通常意味着归因质量下降 |
| INV-W2 | 单模块 stall 不超过 90% busy 时间 | 远超阈值可能是 mapping 错误 |
| INV-W3 | CDC FIFO 平均占用 < 80% | 接近满意味着深度配错 |

### 7.3 API

```python
class IInvariantChecker(ABC):
    @abstractmethod
    def run_all(self, architecture: IArchitecture) -> InvariantReport: ...

@dataclass
class InvariantReport:
    overall_valid: bool                          # 任何 INV-* fail 即为 False
    failures: list["InvariantFailure"]
    warnings: list["InvariantWarning"]
    summary_text: str                            # 人类可读总结

@dataclass
class InvariantFailure:
    invariant_id: str                             # 如 "INV-3"
    description: str
    evidence: dict                                # 失败证据（挂起 thread / 残留 token 等）
```

`InvariantReport` 必须嵌入到主报告头部，且 `overall_valid == False` 时，报告其余部分（性能数字、面积/功耗、反压链分析）显示前必须先显示警告条幅。

