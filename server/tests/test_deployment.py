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
    assert set(body) == {"version", "git_sha", "built_at", "env"}


# ---------- DEP-011 就绪含迁移状态 ----------
def test_readyz_reports_migration_state(client):
    body = client.get("/readyz").json()
    # 测试库由 create_all 建，没有 alembic_version 表 → not_applicable，且不影响就绪
    assert body["checks"]["migration"] in ("not_applicable", "ok")
    assert body["ready"] is True


# ---------- DEP-020/022 迁移与模型不漂移 ----------
def test_migrations_match_models():
    """迁移脚本建出的表结构必须与 ORM 模型一致。

    两条建表路径（开发 create_all / 生产 alembic）一旦漂移，
    「本地全绿、线上缺列」就会发生——这是最难查的一类线上事故。
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
