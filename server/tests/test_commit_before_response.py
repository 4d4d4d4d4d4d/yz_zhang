"""CONC-070 写操作必须在响应发出**之前**提交（105 号 spec）。

FastAPI 0.142 里，`yield` 依赖的收尾代码默认（`scope="request"`）在响应**送达客户端
之后**才执行——而 `get_db` 的 `commit()` 就在收尾代码里。于是：

- 客户端可能在提交之前就拿到 200，紧接着发下一个请求，读到的还是旧数据。
  V130 在 Postgres 上跑全链路验收时撞见：**注销返回 200 之后，紧接着的请求仍通过了
  鉴权**（六轮一次）。一个已注销账号的登录态在那一瞬间仍然有效。
- 提交若失败（唯一约束、序列化冲突、连接断开），客户端已经被告知成功了。对钱来说，
  就是「充值成功」先于入账提交送达。

`TestClient` 看不见这个窗口：它等整个 ASGI 调用结束（包括响应之后的收尾）才返回。
所以这里直接驱动 ASGI 应用，在**响应体被发出的那一刻**，用一个独立的会话去库里看
那笔写入是否已经提交。
"""
import asyncio
import inspect
import json
import re
from pathlib import Path

from app.core.db import SessionLocal
from tests.conftest import auth, register


def _call_and_peek(app, method: str, path: str, headers: dict, body: dict | None, peek):
    """驱动 ASGI 应用；响应体发出的那一刻调用 peek()，返回 (status, peek 的结果)。"""
    raw = json.dumps(body).encode() if body is not None else b""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "scheme": "http", "server": ("testserver", 80), "client": ("t", 1),
        "headers": [(k.lower().encode(), v.encode()) for k, v in
                    {**headers, "content-type": "application/json"}.items()],
    }
    sent = {"body": False}
    out = {}

    async def receive():
        if sent["body"]:
            await asyncio.sleep(3600)
        sent["body"] = True
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
        elif message["type"] == "http.response.body" and "seen" not in out:
            # 客户端此刻已经拿到了响应——它的下一个请求随时可能到
            out["seen"] = peek()

    asyncio.run(app(scope, receive, send))
    return out["status"], out["seen"]


def _app():
    from app.main import app

    return app


def test_conc070_deactivation_is_committed_before_the_client_hears_ok(client):
    """注销：客户端拿到 200 的那一刻，库里必须已经是「已注销、会话已吊销」。"""
    from app.modules.account.models import LoginSession, User

    u = register(client, "13800131001", "注销的人")

    def peek():
        with SessionLocal() as db:
            user = db.get(User, u["id"])
            live = db.query(LoginSession).filter_by(user_id=u["id"], revoked=False).count()
            return user.is_deleted, live

    status, (deleted, live_sessions) = _call_and_peek(
        _app(), "POST", "/api/v1/users/me/deactivate", auth(u), None, peek)
    assert status == 200
    assert deleted is True and live_sessions == 0, (
        "客户端已经拿到「注销成功」，库里却还没提交——它紧接着的请求仍会通过鉴权"
    )


def test_conc070_topup_is_committed_before_the_client_hears_succeeded(client):
    """充值：「成功」送达的那一刻，钱必须已经入账提交。"""
    from app.modules.wallet.models import WalletAccount

    u = register(client, "13800131002", "充值的人")

    def peek():
        with SessionLocal() as db:
            acct = db.get(WalletAccount, u["id"])
            return acct.available_cents if acct else 0

    status, seen = _call_and_peek(
        _app(), "POST", "/api/v1/wallet/topup",
        {**auth(u), "Idempotency-Key": "conc070-topup"}, {"amount_cents": 1234}, peek)
    assert status == 200
    assert seen == 1234, f"客户端已经拿到「充值成功」，库里的余额却是 {seen}"


def test_conc070_every_generator_dependency_is_function_scoped():
    """路由树里每一个 `yield` 依赖都必须是 function 作用域。

    不是只查 `get_db`：job 锁守卫（`job_slot`）也是 `yield` 依赖，而且依赖 `get_db`。
    **作用域是 FastAPI 依赖缓存键的一部分**——同一个请求里 `Depends(get_db)` 与
    `Depends(get_db, scope="function")` 混用，会建出**两个会话**：鉴权读到的 user 在一个
    会话里、业务写入在另一个里。所以要么全改，要么一处都别改；这条钉住「全改」。
    """
    from fastapi.dependencies.models import Dependant
    from fastapi.routing import APIRoute

    def walk_routes(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r
            inner = getattr(r, "original_router", None) or getattr(r, "app", None)
            sub = getattr(inner, "routes", None)
            if sub and inner is not r:
                yield from walk_routes(sub)

    bad, seen_gen = [], 0

    def walk(dep: Dependant, where: str):
        nonlocal seen_gen
        for sub in dep.dependencies:
            call = sub.call
            if call is not None and (inspect.isgeneratorfunction(call)
                                     or inspect.isasyncgenfunction(call)):
                seen_gen += 1
                # 不写 scope 的 yield 依赖，FastAPI 当作 "request"（_get_computed_scope）
                scope = sub.scope or "request"
                if scope != "function":
                    bad.append(f"{where} → {getattr(call, '__qualname__', call)}（{scope}）")
            walk(sub, where)

    routes = list(walk_routes(_app().routes))
    for r in routes:
        walk(r.dependant, f"{sorted(r.methods)[0]} {r.path}")
    assert len(routes) > 200, f"只扫到 {len(routes)} 条路由，遍历可能坏了"
    assert seen_gen > 200, f"只看到 {seen_gen} 个 yield 依赖，扫描可能坏了"
    assert not bad, "这些 yield 依赖会在响应发出之后才收尾（提交）：\n  " + "\n  ".join(sorted(set(bad))[:20])


def test_conc070_no_bare_get_db_in_source():
    """源码层面再钉一次：新写的端点照抄 `Depends(get_db)` 就红。"""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in app_dir.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"Depends\((get_db|job_slot\([^)]*\))\)", text):
            offenders.append(f"{f.relative_to(app_dir)}: {m.group(0)}")
    assert not offenders, "没有写 scope=\"function\" 的依赖：\n  " + "\n  ".join(offenders[:20])
