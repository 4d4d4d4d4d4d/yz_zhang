# SPEC-002：反压协议规范

文档状态：Draft v0.1
作者：架构组
目的：定义模块间数据传输的反压协议、stall 上报机制、反压链追溯算法
依赖：SPEC-001 IModule 接口规范

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
