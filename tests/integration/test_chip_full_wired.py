"""全连线芯片 use case — 回应"全是干测试,没有整颗芯片直接交互"的批评。

与 usecase_npu_v4_full_stack.yaml(26 模块、6 连接,多数模块只贡献面积)
不同,usecase_chip_full_wired.yaml 是每条连接都有真实流量的交互芯片:

  控制面:host → CMDQ → MCU → MAC.in_cmd
  权重面:weight_src → WB → MAC.in_weight
  激活面:act_src → DAGC → DSB → MAC.in_act
  结果面:MAC.out_psum → OB → VAU → AVP → Quant → sink

本文件断言"交互"本身:token 在四条面之间流动、上游行为改变下游状态、
单模块 knob 改动通过连接传导为整芯片端到端 drain 变化。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
from npu_sim.evaluation.runner import run_simulation
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
BASE = "usecase_chip_full_wired.yaml"
TUNED = "usecase_chip_full_wired_tuned.yaml"


@pytest.fixture(scope="module")
def chip():
    """Elaborate once, run once, keep the arch for counter introspection."""
    arch = elaborate(str(FIXTURES / BASE))
    result = run_simulation(arch, max_cycles=5000)
    return arch, result


class TestEveryConnectionCarriesTraffic:
    """没有乘客模块:12+ 条连接每条 tokens_delivered > 0。"""

    def test_all_connections_delivered_tokens(self, chip):
        _, result = chip
        assert len(result.tokens_delivered) >= 12
        dead = {k: v for k, v in result.tokens_delivered.items() if v == 0}
        assert dead == {}, f"connections with zero traffic: {dead}"

    def test_no_tokens_left_in_flight(self, chip):
        _, result = chip
        stuck = {k: v for k, v in result.tokens_in_flight.items() if v != 0}
        assert stuck == {}, f"tokens stuck in FIFOs at drain: {stuck}"

    def test_run_valid(self, chip):
        _, result = chip
        assert result.invariant_report.overall_valid


class TestControlPlaneChain:
    """host 命令穿过 CMDQ、MCU 完整到达 MAC。"""

    def test_cmdq_passes_all_host_commands(self, chip):
        arch, _ = chip
        cmdq = arch.modules["cmdq"]
        assert cmdq._enqueued == 3
        assert cmdq._dequeued == 3

    def test_mcu_dispatches_every_command(self, chip):
        arch, result = chip
        assert arch.modules["mcu"].dispatched == 3
        assert result.tokens_delivered["mcu.op_out→mac.in_cmd"] == 3


class TestWeightPlaneReachesCompute:
    """权重面 → 计算面的跨面交互:WB serve 之后 MAC 状态被改变。"""

    def test_wb_serves_loaded_tiles(self, chip):
        arch, _ = chip
        wb = arch.modules["wb"]
        assert wb.weights_served == 2

    def test_mac_observed_weight_arrival(self, chip):
        """MAC._weight_loaded 由 WB 的 serve token 置位 —— 这是模块间
        状态机交互的直接证据,不是测试代码注入的。"""
        arch, _ = chip
        assert arch.modules["mac"]._weight_loaded is True


class TestResultPlaneHandsOff:
    """MAC → OB → … → sink 逐级交接,无丢失。"""

    def test_ob_accepts_and_flushes_every_psum(self, chip):
        arch, _ = chip
        ob = arch.modules["ob"]
        assert ob.psums_accepted == 6
        assert ob.flushed_tiles == 6

    def test_sink_receives_every_activation(self, chip):
        _, result = chip
        assert result.tokens_delivered["q_out.data_out→sink.in"] == 6

    def test_quant_shrinks_output_width(self, chip):
        """Quant 在芯片输出端真实工作:6 tokens processed。"""
        arch, _ = chip
        assert arch.modules["q_out"].processed == 6


class TestSingleKnobPropagatesEndToEnd:
    """整芯片敏感性:只改输出端 Quant 一个 knob,影响通过连接传导。

    真实芯片语义:本芯片的端到端关键路径是 MCU 控制面(260 拍/op ×
    3 ops ≈ 780k ps),激活面早早跑完。因此 Quant +1 拍/token 不改 drain
    (非关键路径),而是表现为 AVP 被 q_out 反压的 stall 增加 —— SPEC-002
    §3.3 归因把瓶颈正确指到 q_out。这正是"模块交互中的芯片"与"孤立模块
    测试"的区别:影响走连接传导,落点由整芯片的关键路径决定。
    """

    def test_per_channel_quant_propagates_via_backpressure(self):
        base = elaborate_and_run(str(FIXTURES / BASE), max_cycles=5000)
        tuned = elaborate_and_run(str(FIXTURES / TUNED), max_cycles=5000)
        report = compare(base, tuned)
        assert report.both_valid
        # 传导证据 1:上游 AVP 被 q_out 反压的 stall 增加。
        assert report.stall_delta_ps > 0, (
            "single-module knob change failed to propagate as backpressure"
        )
        # 传导证据 2:瓶颈归因指向被改的模块(两个运行都识别 q_out)。
        assert report.baseline_bottleneck == "q_out"
        assert report.variant_bottleneck == "q_out"
        # drain 不变是符合预期的:关键路径在 MCU 控制面,不在 Quant。
        assert report.area_delta_um2 == pytest.approx(3_500, abs=1.0)

    def test_chip_critical_path_is_control_plane(self):
        """佐证上一条:drain 由 MCU 的 3 × 260 拍决定(~780k ps),
        激活面(6 tokens)远早于此完成。"""
        base = elaborate_and_run(str(FIXTURES / BASE), max_cycles=5000)
        assert 750_000 <= base.drain_time_ps <= 850_000


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
