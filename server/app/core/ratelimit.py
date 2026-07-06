"""进程内滑动窗口限流（ACC-001「60s 防刷」）。

MVP 用内存计数器；多实例部署时替换为 Redis，接口不变。
"""
import time
from collections import defaultdict, deque

from app.core.errors import bad_request

_buckets: dict[str, deque] = defaultdict(deque)


def check(key: str, limit: int, window_seconds: int) -> None:
    """在 window 内超过 limit 次则拒绝（429 语义，用 400 承载错误码）。"""
    now = time.time()
    bucket = _buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        retry = int(window_seconds - (now - bucket[0])) + 1
        raise bad_request(f"操作过于频繁，请 {retry} 秒后重试", "rate_limited")
    bucket.append(now)


def reset() -> None:
    """测试辅助：清空所有计数。"""
    _buckets.clear()
