"""DRILL-034 闭环脚本断言失败时打出服务端最近的错误（308 号 spec，V335）。

V112 那次 500，冒烟只报了 `None == 18400`，病因要人去翻 uvicorn 日志。现在服务端在进程内留最近 20 条未处理异常
（过脱敏，只存类型、一句话、出错位置），`/errorz` 用与 /jobz 同一把令牌取；冒烟与真浏览器联调失败时顺手打印。
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import observability as obs
from scripts import smoke
from tests.test_deployment import JOB_HEADERS


def _boom_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(obs.ObservabilityMiddleware)

    @app.get("/wallet/{uid}")
    def boom(uid: int):
        raise RuntimeError(f"wallet missing for 13812345678 uid={uid}")

    return app


def test_unhandled_errors_are_kept_redacted_newest_first_and_bounded():
    obs._recent_errors.clear()
    c = TestClient(_boom_app(), raise_server_exceptions=False)
    assert c.get("/wallet/7", headers={"X-Request-Id": "rid-abc"}).status_code == 500
    [e] = obs.recent_errors()
    assert (e["method"], e["path"], e["error"], e["request_id"]) == ("GET", "/wallet/{uid}", "RuntimeError", "rid-abc")
    assert "13812345678" not in e["message"] and "138****5678" in e["message"], "过脱敏"
    assert e["where"].startswith("tests/test_errorz.py:"), "出错位置是抛异常的那一行，不是中间件"
    for i in range(25):
        obs.record_error(ValueError(f"n{i}"), "POST", "/x")
    rows = obs.recent_errors()
    assert len(rows) == obs.RECENT_MAX == 20 and rows[0]["message"] == "n24", "新的在前、最多 20 条"
    assert len(obs._recent_errors) == 20, "进程里也只留 20 条，不会越攒越多"
    assert obs.recent_errors(3)[2]["message"] == "n22"
    obs._recent_errors.clear()


def test_where_points_at_our_code_even_when_the_library_raised():
    """异常常常在第三方库 / 标准库里抛（json、SQLAlchemy）：出错位置要落在调用它的本仓那一行。"""
    import json

    obs._recent_errors.clear()
    try:
        json.loads("{bad")
    except ValueError as exc:
        obs.record_error(exc, "GET", "/x")
    [e] = obs.recent_errors()
    assert e["where"].startswith("tests/test_errorz.py:"), e["where"]
    obs._recent_errors.clear()


def test_errorz_needs_the_job_token(client):
    obs._recent_errors.clear()
    assert client.get("/errorz").status_code in (401, 403), "与 /jobz 同一把令牌"
    obs.record_error(KeyError("balance"), "GET", "/api/v1/wallet")
    body = client.get("/errorz?limit=50", headers=JOB_HEADERS).json()
    assert [r["error"] for r in body["errors"]] == ["KeyError"]
    obs._recent_errors.clear()
    assert client.get("/errorz", headers=JOB_HEADERS).json() == {"errors": []}


def test_smoke_prints_the_server_errors_and_says_so_when_it_cannot(monkeypatch):
    rows = [{"ts": "2026-10-24T01:00:00Z", "method": "GET", "path": "/api/v1/wallet", "error": "IntegrityError",
             "message": "UNIQUE constraint failed: wallets.user_id", "where": "app/modules/wallet/service.py:42",
             "request_id": "r1"}]
    monkeypatch.setattr(smoke, "req", lambda *a, **k: (200, {"errors": rows}))
    text = smoke.server_errors_text()
    assert "GET /api/v1/wallet → IntegrityError: UNIQUE constraint failed" in text
    assert "app/modules/wallet/service.py:42" in text and "request_id r1" in text
    monkeypatch.setattr(smoke, "req", lambda *a, **k: (200, {"errors": []}))
    assert "没有未处理的异常" in smoke.server_errors_text()
    monkeypatch.setattr(smoke, "req", lambda *a, **k: (404, {}))
    assert "/errorz 返回 404" in smoke.server_errors_text(), "老版本服务端没有这个接口时说清楚"

    def gone(*a, **k):
        raise SystemExit(2)
    monkeypatch.setattr(smoke, "req", gone)
    assert "连不上" in smoke.server_errors_text()


def test_a_failed_smoke_step_prints_them_before_exiting(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "server_errors_text", lambda limit=3: "    GET /x → Boom: 炸了")
    import pytest

    with pytest.raises(SystemExit):
        smoke.step("读钱包", False, "None == 18400")
    out = capsys.readouterr().out
    assert "✗ 读钱包  None == 18400" in out and "服务端最近的错误" in out and "Boom: 炸了" in out
    smoke.step("读钱包", True)
    assert "服务端最近的错误" not in capsys.readouterr().out, "通过时不打"
