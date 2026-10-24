"""CONC-060/061 连接预算的算术要有东西在算（98 号 spec）。

起因是量了一遍生产编排文件与池参数的实际数字：

    deploy/docker-compose.prod.yml:  uvicorn ... --workers 2
    config.py:                       DB_POOL_SIZE=10, DB_MAX_OVERFLOW=20
    => 2 × 30 = 60 条连接
    postgres:16-alpine 默认           max_connections = 100（3 条留给超级用户）

今天这个数字是活得下去的。问题在于**没有任何地方在算它**：

- 把 `--workers 2` 调成 8（一个看起来只会「扛得更多」的改动）→ 240 条，
  直接超出 100；
- 把 `replicas: 1` 加到 3 → 同样超。

而超出之后的表现不是某个接口变慢，是 PostgreSQL 直接拒连
（`FATAL: sorry, too many clients already`）——**每一个接口同时 500，
包括健康检查**。于是编排器判定容器不健康并重启它，重启后它又去抢同样多的连接。

**这正是「一个承诺没有任何东西在检查」的又一次**：池参数的注释写着
「CONC-002 连接池」，而连接池该满足的那条不等式没人验。

本篇把三件事钉住：
1. 编排文件里真实的 worker/副本数，与 `PLATFORM_API_WORKERS` 一致；
2. 这个数乘以单进程占用，不超过预算；
3. 预算本身不超过数据库真实的 `max_connections`（扣掉保留连接）。
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO / "deploy" / "docker-compose.prod.yml"

# PostgreSQL 默认 max_connections=100，其中 superuser_reserved_connections=3。
# 再留一些给 alembic 迁移、人工 psql 排查与监控采集——
# **上线当天迁移连不上库，和服务连不上库一样是事故。**
PG_DEFAULT_MAX_CONNECTIONS = 100
RESERVED_FOR_SUPERUSER = 3
RESERVED_FOR_OPS = 10


def _compose_text() -> str:
    assert PROD_COMPOSE.exists(), f"找不到生产编排文件：{PROD_COMPOSE}"
    return PROD_COMPOSE.read_text(encoding="utf-8")


def _declared_workers() -> int:
    """编排文件里 api 服务真实启动了几个 uvicorn worker。"""
    text = _compose_text()
    m = re.search(r'"--workers",\s*"(\d+)"', text)
    assert m, (
        "在生产编排文件里找不到 `--workers N`。"
        "它要么被改成了别的启动方式（那本篇的算术就按新方式重写），"
        "要么没写——而不写等于 1 个 worker，也该显式写出来"
    )
    return int(m.group(1))


def _api_replicas() -> int:
    """api 服务的副本数（没声明就是 1）。"""
    text = _compose_text()
    # 只看 api 那一段：worker 容器也有 deploy.replicas，但它走 HTTP 不开池
    m = re.search(r"^  api:$(.*?)^  \w", text, re.M | re.S)
    if not m:
        return 1
    r = re.search(r"replicas:\s*(\d+)", m.group(1))
    return int(r.group(1)) if r else 1


def test_conc060_pool_timeout_is_short_enough_to_be_a_message_not_a_hang():
    """池满时等 10 秒就放弃，而不是 SQLAlchemy 默认的 30 秒。

    30 秒的等待在用户那边等于「这页卡死了」——他会刷新，于是又来一个请求，
    池更满。**让他快点看到一句话，比让他等半分钟再看到同一句话好。**
    """
    from app.core.config import settings

    assert 1 <= settings.DB_POOL_TIMEOUT <= 15, (
        f"PLATFORM_DB_POOL_TIMEOUT={settings.DB_POOL_TIMEOUT}："
        "太短会把正常的排队当成故障，太长会让用户面对一个转圈的页面并去刷新"
    )


def test_conc060_engine_really_got_the_pool_timeout():
    """设了参数不等于传进去了——这一条验真的传到了引擎上。

    非 SQLite 才有池参数，所以这里直接造一个 Postgres URL 的引擎
    （不连库，`create_engine` 只是构造）。
    """
    from app.core.config import settings
    from app.core.db import _make_engine

    eng = _make_engine("postgresql+psycopg://u:p@127.0.0.1:1/none")
    assert eng.pool._timeout == settings.DB_POOL_TIMEOUT, (
        "引擎上的 pool_timeout 与配置不一致——参数没传进去，配置就只是个摆设"
    )
    assert eng.pool._max_overflow == settings.DB_MAX_OVERFLOW
    eng.dispose()


def test_conc061_deployment_worker_count_matches_the_declared_one():
    """编排文件里的 worker 数必须与 `PLATFORM_API_WORKERS` 的默认值一致。

    这两个数在两份文件里各写一遍，而连接预算是按后者算的——
    **改了编排而没改声明，算术就在算一个不存在的部署。**
    """
    from app.core.config import settings

    workers = _declared_workers() * _api_replicas()
    assert workers == settings.API_WORKERS, (
        f"编排文件里是 {_declared_workers()} worker × {_api_replicas()} 副本 "
        f"= {workers} 个开池进程，而 PLATFORM_API_WORKERS 的默认值是 "
        f"{settings.API_WORKERS}。两个数不一致时，连接预算算的是后者，"
        "也就是算了一个不存在的部署"
    )


def test_conc061_connection_demand_fits_the_budget():
    """进程数 × (池 + 溢出) ≤ 预算。超了就是上线当天全站 500。"""
    from app.core.config import settings

    per_process = settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW
    demand = settings.API_WORKERS * per_process
    assert demand <= settings.DB_CONNECTION_BUDGET, (
        f"{settings.API_WORKERS} × (池 {settings.DB_POOL_SIZE} + 溢出 "
        f"{settings.DB_MAX_OVERFLOW}) = {demand} 条，超过预算 "
        f"{settings.DB_CONNECTION_BUDGET}。连接耗尽时每一个接口都会同时 500，"
        "包括健康检查——编排器会开始重启容器，而重启后它又去抢同样多的连接"
    )


def test_conc061_budget_fits_a_default_postgres():
    """预算本身不能超过数据库真实能给的连接数。

    生产编排用的是 `postgres:16-alpine` 且**没有调过 max_connections**，
    所以上限就是默认的 100；其中 3 条留给超级用户，再留 10 条给
    alembic 迁移、人工 psql 排查与监控采集——
    **上线当天迁移连不上库，和服务连不上库一样是事故。**

    哪天真的调大了 `max_connections`，这条会提醒把它写进编排文件，
    而不是让预算凭空变大。
    """
    from app.core.config import settings

    text = _compose_text()
    tuned = re.search(r"max_connections\s*=?\s*(\d+)", text)
    ceiling = int(tuned.group(1)) if tuned else PG_DEFAULT_MAX_CONNECTIONS
    usable = ceiling - RESERVED_FOR_SUPERUSER - RESERVED_FOR_OPS
    assert settings.DB_CONNECTION_BUDGET <= usable, (
        f"预算 {settings.DB_CONNECTION_BUDGET} 超过数据库可用连接 {usable}"
        f"（上限 {ceiling} − 超级用户 {RESERVED_FOR_SUPERUSER} − "
        f"运维 {RESERVED_FOR_OPS}）。"
        "要么下调预算，要么在编排文件里显式调大 max_connections 并重跑这条"
    )


def test_conc061_startup_check_really_blocks_an_over_budget_deployment():
    """闸门自己的红验：把 worker 调到超预算，`startup_check` 必须拒绝启动。

    **不靠「以后有人改坏时才知道」**——这条拦截本身要被验证过会拦。
    """
    from app.core.config import settings
    from app.vendors.registry import startup_check

    old = (settings.ENV, settings.API_WORKERS, settings.DATABASE_URL)
    settings.ENV = "prod"
    settings.API_WORKERS = 99          # 99 × 30 = 2970，远超预算
    settings.DATABASE_URL = "postgresql+psycopg://u:p@db:5432/x"
    try:
        with pytest.raises(RuntimeError) as err:
            startup_check()
        assert "连接预算不够" in str(err.value), (
            f"拒绝启动了，但不是因为连接预算：{str(err.value)[:200]}"
        )
    finally:
        settings.ENV, settings.API_WORKERS, settings.DATABASE_URL = old


def test_conc061_sqlite_deployments_are_not_judged_by_this_arithmetic():
    """SQLite 没有连接池，这条算术对它没有意义，不该误报。

    **一个假报警多的闸门会被人关掉**——本地与测试跑的都是 SQLite。
    """
    from app.core.config import settings
    from app.vendors.registry import startup_check

    old = (settings.ENV, settings.API_WORKERS, settings.DATABASE_URL)
    settings.ENV = "prod"
    settings.API_WORKERS = 99
    settings.DATABASE_URL = "sqlite:///./x.db"
    try:
        # prod + SQLite 本来就会因为别的红线被拦（第 9 条），
        # 这里只断言**不是因为连接预算**被拦。
        try:
            startup_check()
        except RuntimeError as exc:
            assert "连接预算不够" not in str(exc), (
                "SQLite 部署被连接预算拦住了——那条算术对它没有意义"
            )
    finally:
        settings.ENV, settings.API_WORKERS, settings.DATABASE_URL = old
