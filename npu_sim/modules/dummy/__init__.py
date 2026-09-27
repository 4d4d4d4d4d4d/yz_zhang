"""Dummy module: framework self-test fixture (both timing and functional)."""

from npu_sim.modules.dummy.dummy_module import Dummy
from npu_sim.modules.dummy.dummy_numerical import DummyGoldenModel

__all__ = ["Dummy", "DummyGoldenModel"]
