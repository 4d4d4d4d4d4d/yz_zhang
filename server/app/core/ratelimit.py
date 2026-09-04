"""限流（ACC-001「60s 防刷」）。

CONC-020/021/022：接口 `check(key, limit, window)` 不变，后端可换：

- `MemoryRateLimiter`：进程内滑动窗口。单副本正确，多副本下每个副本各限一份。
- `RedisRateLimiter`：`INCR` + `EXPIRE` 原子固定窗口，多副本共享同一份计数。

**降级策略**：Redis 连续失败达阈值即进入冷却期，期间直接用内存实现并告警。
限流是防滥用手段，不是正确性依赖——为它牺牲登录可用性是错误的取舍。
"""
import time
from collections import defaultdict, deque
from typing import Protocol

from app.core.config import settings
from app.core.errors import bad_request


def _reject(retry: int):
    raise bad_request(f"操作过于频繁，请 {retry} 秒后重试", "rate_limited")


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """超限时返回建议重试秒数，未超限返回 None。"""

    def reset(self) -> None: ...


class MemoryRateLimiter:
    """进程内滑动窗口。"""

    def __init__(self) -> None:
        self._buckets: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.time()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return int(window_seconds - (now - bucket[0])) + 1
        bucket.append(now)
        return None

    def reset(self) -> None:
        self._buckets.clear()


class RedisRateLimiter:
    """Redis 固定窗口计数：INCR 首次命中时设 EXPIRE，天然原子且无需 Lua。"""

    def __init__(self, client) -> None:
        self._client = client

    def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        bucket = f"rl:{key}:{int(time.time()) // window_seconds}"
        count = int(self._client.incr(bucket))
        if count == 1:
            self._client.expire(bucket, window_seconds)
        if count > limit:
            ttl = int(self._client.ttl(bucket) or window_seconds)
            return max(ttl, 1)
        return None

    def reset(self) -> None:  # pragma: no cover - 生产不清库
        pass


_memory = MemoryRateLimiter()
_remote: RateLimiter | None = None
_fail_count = 0
_cooldown_until = 0.0
_degraded_reason = ""


def _get_remote() -> RateLimiter | None:
    """惰性连接 Redis：未配置 URL 或依赖缺失时返回 None（用内存实现）。"""
    global _remote, _degraded_reason
    if not settings.REDIS_URL:
        return None
    if _remote is None:
        try:
            import redis  # type: ignore

            _remote = RedisRateLimiter(redis.Redis.from_url(settings.REDIS_URL))
        except Exception as exc:  # pragma: no cover - 依赖缺失路径
            _degraded_reason = f"redis unavailable: {type(exc).__name__}"
            return None
    return _remote


def _note_failure(exc: Exception) -> None:
    global _fail_count, _cooldown_until, _degraded_reason
    _fail_count += 1
    _degraded_reason = f"redis error: {type(exc).__name__}"
    if _fail_count >= settings.RATELIMIT_FAIL_THRESHOLD:
        _cooldown_until = time.time() + settings.RATELIMIT_COOLDOWN_SECONDS


def check(key: str, limit: int, window_seconds: int) -> None:
    """在 window 内超过 limit 次则拒绝（429 语义，用 400 承载错误码）。"""
    global _fail_count
    remote = _get_remote() if time.time() >= _cooldown_until else None
    if remote is not None:
        try:
            retry = remote.hit(key, limit, window_seconds)
        except Exception as exc:  # Redis 抖动 → 记一次失败并落回内存实现
            _note_failure(exc)
        else:
            _fail_count = 0
            if retry is not None:
                _reject(retry)
            return
    retry = _memory.hit(key, limit, window_seconds)
    if retry is not None:
        _reject(retry)


def backend_status() -> str:
    """DEP-011 就绪探针里展示当前限流后端，降级时明确可见。"""
    if not settings.REDIS_URL:
        return "memory"
    if time.time() < _cooldown_until:
        return f"memory (degraded: {_degraded_reason})"
    return "redis"


def reset() -> None:
    """测试辅助：清空所有计数与降级状态。"""
    global _fail_count, _cooldown_until, _degraded_reason
    _memory.reset()
    _fail_count = 0
    _cooldown_until = 0.0
    _degraded_reason = ""
