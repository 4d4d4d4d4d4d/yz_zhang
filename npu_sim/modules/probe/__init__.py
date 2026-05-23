"""Probe modules: Producer / Consumer used by backpressure tests."""

from npu_sim.modules.probe.consumer import Consumer
from npu_sim.modules.probe.passthrough import Passthrough
from npu_sim.modules.probe.producer import Producer

__all__ = ["Consumer", "Passthrough", "Producer"]
