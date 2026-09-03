"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def stat_sink(event_bus: InMemoryEventBus) -> InMemoryStatSink:
    return InMemoryStatSink(event_bus=event_bus)


@pytest.fixture
def isolated_registry():
    """Snapshot and restore the global ModuleRegistry around a test.

    Lets tests register dummy / mis-named modules without polluting other tests.
    """
    snapshot = dict(ModuleRegistry._registry)
    try:
        ModuleRegistry._clear_for_test()
        yield ModuleRegistry
    finally:
        ModuleRegistry._registry.clear()
        ModuleRegistry._registry.update(snapshot)


@pytest.fixture
def isolated_numerical_registry():
    snapshot = dict(NumericalModelRegistry._registry)
    try:
        NumericalModelRegistry._clear_for_test()
        yield NumericalModelRegistry
    finally:
        NumericalModelRegistry._registry.clear()
        NumericalModelRegistry._registry.update(snapshot)
