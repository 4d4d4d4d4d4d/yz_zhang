"""CONC-067 调外部服务时不许挂着数据库事务（113 号 spec）。

量过：全量测试里 260 次供应商调用有 259 次发生在一个**没结束的事务**里
（实名、充值下单、提现出款、内容审核、存储删除……）。在 Postgres 上那意味着：
每一次等供应商的时间里，这个请求都占着一条池连接（`idle in transaction`）和它拿过的行锁。
供应商一慢，连接池先耗尽——**与这个供应商毫无关系的接口一起挂**。
业界的说法是 *never call APIs inside database transactions*：要么先提交再调用、回来另开事务回写，
要么走 outbox 让 worker 在事务外投递。

这里做两件事：
1. 按线程记「打开着的事务」：引擎的 begin / commit / rollback 事件；
2. `guard(kind, provider)`：把供应商实现包一层，任何方法被调用时检查这个线程有没有打开着的事务。
   开发 / 测试环境直接抛错（让测试红、让写代码的人当场改）；生产只记日志与指标、照常执行——
   **生产上不能因为一条防御性检查把用户的请求打挂**。
"""
from __future__ import annotations

import logging
import threading
from collections import Counter

from sqlalchemy import event

_state = threading.local()
violations: Counter[str] = Counter()
_log = logging.getLogger("txguard")


# 状态记在**连接**上，再按「哪个线程开的事务」归到那个线程名下。
#
# 第一版按线程记深度：begin 加一、commit / rollback 减一。真服务端上跑出一个偶发的误报——
# FastAPI 带 yield 的依赖，进入与收尾**可能落在线程池里不同的线程上**：事务在线程 X 上开、
# 在线程 Y 上提交，X 的计数永远减不回去，之后落到 X 上的任何请求一调供应商就被判成「挂着事务」
# （开发 / 沙箱直接 500，生产是一串假告警）。测试客户端碰巧很少换线程，所以整套测试一直是绿的。
# 现在：begin 时把连接登记进开它的那个线程的集合，并在连接上记下这个集合；
# commit / rollback 无论在哪个线程触发，都从**登记它的那个集合**里删掉。
# 连接上的 info 跟着池里的物理连接走（跨多次借出都在）：登记用一次性的令牌，
# 万一某次归还没有触发 commit / rollback 事件，下一次 begin 先把那个旧令牌从旧集合里清掉。
def _open() -> dict:
    s = getattr(_state, "open", None)
    if s is None:
        s = _state.open = {}
    return s


def _depth() -> int:
    return len(_open())


_READS = ("SELECT", "PRAGMA", "SAVEPOINT", "RELEASE", "SHOW", "WITH")


def install(engine) -> None:
    """在引擎上挂事件。重复调用无害（每个引擎只挂一次）。"""
    if getattr(engine, "_txguard_installed", False):
        return

    @event.listens_for(engine, "begin")
    def _begin(conn):  # noqa: ANN001
        _end(conn)
        token = object()
        owner = _open()
        owner[token] = conn.info
        conn.info["txguard_owner"] = (owner, token)
        conn.info["txguard_wrote"] = ""

    @event.listens_for(engine, "commit")
    def _commit(conn):  # noqa: ANN001
        _end(conn)

    @event.listens_for(engine, "rollback")
    def _rollback(conn):  # noqa: ANN001
        _end(conn)

    @event.listens_for(engine, "before_cursor_execute")
    def _execute(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        head = statement.lstrip().upper()
        # 行锁（SELECT … FOR UPDATE）和写一样：替调用方提交会悄悄放掉它想要的串行化
        if not head.startswith(_READS) or " FOR UPDATE" in head:
            # 报错时要能说出「是哪一条写让这个事务放不掉」：只记语句开头，不记参数
            conn.info["txguard_wrote"] = " ".join(statement.split())[:80]

    engine._txguard_installed = True


def _end(conn) -> None:  # noqa: ANN001
    owned = conn.info.pop("txguard_owner", None)
    conn.info.pop("txguard_wrote", None)
    if owned is not None:
        owner, token = owned
        owner.pop(token, None)


def _last_write() -> str:
    return next((w for info in list(_open().values()) if (w := info.get("txguard_wrote"))), "")


def wrote_in_transaction() -> bool:
    """这个线程打开着的事务里有没有写过（INSERT / UPDATE / DELETE …）。"""
    return bool(_last_write())


def in_transaction() -> bool:
    """当前线程有没有打开着的数据库事务。"""
    return _depth() > 0


def _call_site() -> str:
    """业务代码里离这次调用最近的那一行：生产日志要能直接指到改哪里。"""
    import traceback

    for frame in reversed(traceback.extract_stack()[:-3]):
        f = frame.filename.replace("\\", "/")
        if "/app/modules/" in f or ("/app/" in f and "/app/core/txguard" not in f and "/app/vendors/" not in f):
            return f"{f.split('/app/', 1)[-1]}:{frame.lineno}"
    return "?"


class TransactionHeldAcrossVendorCall(RuntimeError):
    pass


def check(kind: str, method: str) -> None:
    if not in_transaction():
        return
    key = f"{kind}.{method}"
    violations[key] += 1
    from app.core.config import settings

    last = _last_write()
    why = f"；事务里写过：{last}" if last else f"；未写过，打开着的事务 {_depth()} 个"
    msg = (f"调用供应商 {key}（{_call_site()}）时还挂着一个数据库事务{why}："
           "先提交（或用 vendor_base.release）再调用，回来另开事务回写（CONC-067）")
    if settings.ENV in ("prod", "staging"):
        _log.error(msg)
        return
    raise TransactionHeldAcrossVendorCall(msg)


class Guarded:
    """供应商实现的透明代理：属性照常读，方法调用前过一次 `check`。"""

    __slots__ = ("_kind", "_inner")

    def __init__(self, kind: str, inner) -> None:  # noqa: ANN001
        object.__setattr__(self, "_kind", kind)
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name: str):
        value = getattr(self._inner, name)
        if not callable(value) or name.startswith("_") or getattr(self._inner, "in_process", False):
            return value
        kind = self._kind

        def call(*args, **kwargs):
            check(kind, name)
            return value(*args, **kwargs)

        return call

    def __setattr__(self, name: str, value) -> None:  # noqa: ANN001
        setattr(self._inner, name, value)

    @property
    def unwrapped(self):
        return self._inner


def reset() -> None:
    """测试辅助。"""
    violations.clear()
    _open().clear()
