"""Bounded FIFO used by TlmConnection. Reference: SPEC-002 §5."""

from __future__ import annotations

from collections import deque
from typing import Any, Optional


class Fifo:
    """Bounded queue. Returns False on enqueue when full; None on dequeue when empty."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"Fifo capacity must be >= 1, got {capacity}.")
        self._capacity = capacity
        self._items: deque[Any] = deque()

    def try_enqueue(self, item: Any) -> bool:
        if len(self._items) >= self._capacity:
            return False
        self._items.append(item)
        return True

    def try_dequeue(self) -> Optional[Any]:
        if not self._items:
            return None
        return self._items.popleft()

    def peek(self) -> Optional[Any]:
        return self._items[0] if self._items else None

    def level(self) -> int:
        return len(self._items)

    @property
    def capacity(self) -> int:
        return self._capacity

    def is_full(self) -> bool:
        return len(self._items) >= self._capacity

    def is_empty(self) -> bool:
        return not self._items
