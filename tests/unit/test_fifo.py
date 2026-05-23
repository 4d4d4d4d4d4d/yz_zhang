"""Unit tests for runtime.Fifo."""

from __future__ import annotations

import pytest

from npu_sim.runtime.fifo import Fifo


def test_enqueue_until_full():
    f = Fifo(capacity=3)
    assert f.try_enqueue("a")
    assert f.try_enqueue("b")
    assert f.try_enqueue("c")
    assert f.is_full()
    assert not f.try_enqueue("d")
    assert f.level() == 3


def test_dequeue_fifo_order():
    f = Fifo(capacity=4)
    for x in ("a", "b", "c"):
        assert f.try_enqueue(x)
    assert f.try_dequeue() == "a"
    assert f.try_dequeue() == "b"
    assert f.try_dequeue() == "c"
    assert f.try_dequeue() is None


def test_peek_does_not_consume():
    f = Fifo(capacity=2)
    f.try_enqueue("a")
    assert f.peek() == "a"
    assert f.peek() == "a"
    assert f.level() == 1


def test_empty_fifo():
    f = Fifo(capacity=2)
    assert f.is_empty()
    assert f.try_dequeue() is None
    assert f.peek() is None


def test_invalid_capacity_rejected():
    with pytest.raises(ValueError):
        Fifo(capacity=0)
    with pytest.raises(ValueError):
        Fifo(capacity=-1)
