"""DEP-060~062 部署与可观测验证（20 号 spec）。

这套测试盯的是「部署这件事本身」：探针、指标、迁移与建表不漂移、
日志不泄密、配置自检拦得住错误上线。
"""
import pytest

from app.core import observability as obs
from app.core.db import Base, engine, migration_status

from .conftest import JOB_HEADERS, auth, register


# ---------- DEP-012 版本 ----------
def test_version_endpoint(client):
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    # 断言必备字段而非精确集合：后续批次会往这里加信息（如 FIN-053 沙箱标识），
    # 用相等断言会让每次增补都变成一次假失败
    assert {"version", "git_sha", "built_at", "env"} <= set(body)


# ---------- DEP-011 就绪含迁移状态 ----------
def test_readyz_reports_migration_state(client):
    body = client.get("/readyz").json()
    # 测试库由 create_all 建，没有 alembic_version 表 → not_applicable，且不影响就绪
    assert body["checks"]["migration"] in ("not_applicable", "ok")
    assert body["ready"] is True


# ---------- DEP-020/022 迁移与模型不漂移 ----------
def test_migrations_match_models():
    """迁移脚本建出的表**名与列名**必须与 ORM 模型一致。

    两条建表路径（开发 create_all / 生产 alembic）一旦漂移，
    「本地全绿、线上缺列」就会发生——这是最难查的一类线上事故。

    注意这一条只比名字。列的**属性**（nullable / 类型）由下面那条
    `test_migrations_match_column_properties` 比——分成两条是因为
    它们失败时要做的事不一样：缺列要补迁移，属性不一致要改哪一边
    得先判断「模型对还是迁移对」。
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, inspect

    import os
    import tempfile

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    assert ScriptDirectory.from_config(cfg).get_current_head(), "必须存在至少一个迁移版本"

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/mig.db"
        mig_engine = create_engine(url)
        from alembic import command

        cfg.set_main_option("sqlalchemy.url", url)
        os.environ["PLATFORM_DATABASE_URL"] = url
        try:
            # env.py 用的是 app.core.db.engine，这里直接把连接注入 alembic
            with mig_engine.connect() as conn:
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, "head")
                conn.commit()
        finally:
            os.environ.pop("PLATFORM_DATABASE_URL", None)

        mig_tables = set(inspect(mig_engine).get_table_names()) - {"alembic_version"}
        model_tables = set(Base.metadata.tables)
        assert model_tables - mig_tables == set(), f"迁移缺表：{model_tables - mig_tables}"

        for table in sorted(model_tables):
            mig_cols = {c["name"] for c in inspect(mig_engine).get_columns(table)}
            model_cols = set(Base.metadata.tables[table].columns.keys())
            assert model_cols - mig_cols == set(), f"{table} 迁移缺列：{model_cols - mig_cols}"


def test_migrations_match_column_properties():
    """DEP-022 列的**属性**也要对上：nullable 与类型，不只是名字。

    这一条是 V109 体检逼出来的。上面那条测试的 docstring 原本写着
    「表结构必须与 ORM 模型一致」，而它实际只比**名字集合**——
    V103 建 `queue_sla_notices` 时把 `created_at` 写成 `nullable=True`
    （模型是非 Optional 的 `Mapped[datetime]`），这条测试一路全绿。
    CI 里的 `alembic check` 当时是红的，但没人看 CI，红了三个批次。

    「承诺了却没有东西在检查」这个形状，这一路已经第八次（V96 的
    「在管理后台做」、V99 的「必须换人」、V101 的 `can_invoice`、
    V103 的 `SUPPORT_SLA_HOURS`、V106 的 eslint 豁免、V108 的两处脱敏
    docstring）。所以这次不是只修那一列，而是**把检查补到与承诺一样宽**。

    用 alembic 自己的 `compare_metadata`（就是 `alembic check` 背后那个），
    而不是手写属性比对——手写的第二份实现必然抄漏。
    """
    import os
    import tempfile

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/props.db"
        engine = create_engine(url)
        cfg.set_main_option("sqlalchemy.url", url)
        os.environ["PLATFORM_DATABASE_URL"] = url
        try:
            with engine.connect() as conn:
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, "head")
                conn.commit()
        finally:
            os.environ.pop("PLATFORM_DATABASE_URL", None)

        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "target_metadata": Base.metadata,
                    # SQLite 上的索引/约束名比对噪音很大（批处理模式会重命名），
                    # 而闸门要钉的是**会在生产迁移当场失败的东西**：缺表、缺列、
                    # nullable 与类型。一个假报警多的闸门会被人关掉。
                    "include_object": lambda obj, name, type_, reflected, compare_to: (
                        type_ in ("table", "column")
                    ),
                },
            )
            diff = compare_metadata(ctx, Base.metadata)

    interesting = [d for d in diff if _drift_kind(d) in _DRIFT_MUST_BE_EMPTY]
    assert not interesting, (
        "迁移建出来的结构与模型不一致：\n  "
        + "\n  ".join(repr(d) for d in interesting)
        + "\n补一条迁移，或者改模型——先判断哪一边是对的。"
    )


# 必须为空的漂移种类 -> 为什么它会在生产出事。值是理由，不是布尔（V90 那条）。
_DRIFT_MUST_BE_EMPTY: dict[str, str] = {
    "add_table": "模型有这张表而迁移没建——生产上第一次写它就 no such table",
    "remove_table": "迁移建了模型里没有的表——要么模型删漏了，要么迁移多建了",
    "add_column": "模型有这一列而迁移没加——生产上读它就报缺列",
    "remove_column": "迁移里有模型没有的列，且它可能是 NOT NULL——插入会失败",
    "modify_nullable": "一边允许空一边不允许——迁移收紧时存量 null 会让升级当场失败",
    "modify_type": "类型不一致——截断、精度丢失，钱的字段上是事故",
}


def _drift_kind(diff) -> str:
    """compare_metadata 返回的元素形状不统一：有的是元组，有的是元组列表。"""
    if isinstance(diff, list):
        return _drift_kind(diff[0]) if diff else ""
    return diff[0] if isinstance(diff, tuple) and diff else ""


def test_dep022_drift_scanner_can_actually_see_drift():
    """扫不到等于全绿，是最糟的一种绿。

    上面那条闸门的全部价值在于「它真的能看见属性漂移」。所以这里**人造**
    一处漂移（把一列的 nullable 翻过来）喂给同一个比对函数，它必须报出来。
    这一条防的正是 V109 修掉的那种情况：一个名字叫「不漂移」、
    实际上什么都比不出来的测试。
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine

    engine = create_engine("sqlite://")  # 内存库，不碰任何真实数据
    built = MetaData()
    Table("drift_probe", built, Column("id", Integer, primary_key=True),
          Column("made_at", DateTime, nullable=True))
    built.create_all(engine)

    wanted = MetaData()
    Table("drift_probe", wanted, Column("id", Integer, primary_key=True),
          Column("made_at", DateTime, nullable=False))  # 只差 nullable

    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "target_metadata": wanted,
                        "include_object": lambda o, n, t, r, c: t in ("table", "column")})
        diff = compare_metadata(ctx, wanted)

    kinds = {_drift_kind(d) for d in diff}
    assert "modify_nullable" in kinds, f"比对函数看不见 nullable 漂移，闸门是空的：{diff}"
    assert "modify_nullable" in _DRIFT_MUST_BE_EMPTY, "看得见却不判失败，等于没看"


def test_migration_status_shape():
    status = migration_status()
    assert status["state"] in ("ok", "mismatch", "not_applicable", "unknown")


def test_create_all_refused_in_prod(monkeypatch):
    """DEP-020 生产唯一建表路径是 alembic；create_all 在多副本下会互相踩。"""
    from app.core import db as db_module

    monkeypatch.setattr(db_module.settings, "ENV", "prod")
    with pytest.raises(RuntimeError, match="alembic"):
        db_module.init_db()


# ---------- DEP-040 日志脱敏 ----------
@pytest.mark.parametrize(
    "raw,forbidden",
    [
        ("用户 13812345678 登录", "13812345678"),
        ("证件 110101199001011234 核验", "110101199001011234"),
        ("卡号 6222020000123456 打款", "6222020000123456"),
    ],
)
def test_log_redaction(raw, forbidden):
    out = obs.redact(raw)
    assert forbidden not in out
    assert "*" in out


def test_json_formatter_redacts_and_carries_request_id():
    import logging

    formatter = obs.JsonFormatter()
    token = obs.request_id_var.set("rid-123")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1,
                                   "手机 13812345678 已验证", None, None)
        out = formatter.format(record)
    finally:
        obs.request_id_var.reset(token)
    assert "13812345678" not in out
    assert "rid-123" in out


# ---------- DEP-041 request_id ----------
def test_request_id_echoed_and_honored(client):
    r = client.get("/healthz")
    assert r.headers.get("X-Request-Id")
    r2 = client.get("/healthz", headers={"X-Request-Id": "caller-supplied-id"})
    assert r2.headers["X-Request-Id"] == "caller-supplied-id"  # 透传，便于跨服务串联


# ---------- DEP-042 指标 ----------
def test_metrics_requires_job_token(client):
    assert client.get("/metrics").status_code in (401, 403)


def test_metrics_exposes_request_and_money_series(client):
    client.get("/healthz")
    r = client.get("/metrics", headers=JOB_HEADERS)
    assert r.status_code == 200
    text = r.text
    for series in ("http_requests_total", "http_request_duration_seconds_bucket",
                   "platform_escrow_cents", "platform_pending_withdraw_cents",
                   "platform_open_disputes"):
        assert series in text, f"缺少指标 {series}"


def test_metrics_uses_route_template_not_raw_path(client, requester):
    """路径里带 id 时必须用路由模板，否则指标基数会被任务 id 打爆。"""
    client.get("/api/v1/tasks/12345", headers=auth(requester))
    text = client.get("/metrics", headers=JOB_HEADERS).text
    assert "12345" not in text


# ---------- DEP-051 job 健康 ----------
def test_jobz_records_last_success(client):
    assert client.get("/jobz").status_code in (401, 403)
    client.post("/api/v1/tasks/jobs/auto-accept", headers=JOB_HEADERS)
    body = client.get("/jobz", headers=JOB_HEADERS).json()
    row = next(j for j in body["jobs"] if j["job"] == "auto_accept")
    assert row["last_success_at"] is not None
    assert row["seconds_since_success"] is not None
    assert row["last_error"] == ""


# ---------- DEP-062 生产配置自检 ----------
def test_cors_origins_parsing(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://a.example, https://b.example")
    assert settings.cors_origins() == ["https://a.example", "https://b.example"]


def test_cron_job_list_covers_every_job_endpoint(client):
    """worker 必须真的驱动**全部** job 端点。

    漏掉一个的后果是「那件事再也不会自动发生」，而且没有任何报错——
    所以这里用路由表反查，新增 job 端点却忘了排期会直接测试失败。
    """
    from scripts.cron import JOBS

    scheduled = {path for path, _ in JOBS}
    exposed = {
        route.path for route in client.app.routes
        if "/jobs/" in getattr(route, "path", "") and "POST" in getattr(route, "methods", set())
    }
    assert exposed - scheduled == set(), f"以下 job 端点没有被 cron 排期：{exposed - scheduled}"
