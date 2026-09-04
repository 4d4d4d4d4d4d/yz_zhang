"""SEC-050~054 抗攻击验证（23 号 spec）。

原有限流是**账号维度**——攻击者每次换手机号，计数器永远是 1，形同虚设。
本套件验证补上的 IP 维度确实生效，且**不能靠伪造 XFF 绕过**。
"""
import pytest

from app.core import guard
from app.core.clientip import client_ip
from app.core.config import settings

from .conftest import auth, register


@pytest.fixture(autouse=True)
def _clean_guard():
    from app.core.ratelimit import reset as rl_reset

    guard.reset()
    rl_reset()
    yield
    guard.reset()
    rl_reset()


def send_code(client, phone, headers=None):
    return client.post("/api/v1/auth/send-code", json={"phone": phone},
                       headers=headers or {})


# ---------- SEC-050 IP 维度限流：换账号不换 IP 仍被拦 ----------
def test_ip_limit_blocks_account_rotation(client):
    """这是原实现最大的漏洞：只按手机号限，批量注册完全不受影响。"""
    codes = []
    for i in range(12):
        codes.append(send_code(client, f"1390000{i:04d}").status_code)
    assert 400 in codes, f"每次换手机号就绕过限流 —— IP 维度没生效：{codes}"
    blocked = [c for c in codes if c == 400]
    assert len(blocked) >= 2


def test_account_limit_still_applies(client):
    """账号维度不能因为加了 IP 维度就失效：同号高频同样被拦。"""
    codes = [send_code(client, "13900008888").status_code for _ in range(5)]
    assert codes[0] == 200
    assert 400 in codes


# ---------- SEC-051 XFF 伪造不能绕过 ----------
def test_forged_xff_cannot_bypass_ip_limit(client, monkeypatch):
    """攻击者每次带一个不同的伪造 X-Forwarded-For。

    只要我们不信任 XFF（或只信任反代注入的最后一跳），伪造就无效。
    """
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)  # 无反代：只认 socket 对端
    codes = []
    for i in range(12):
        codes.append(
            send_code(client, f"1391111{i:04d}",
                      headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code
        )
    assert 400 in codes, f"伪造 XFF 绕过了 IP 限流：{codes}"


def test_client_ip_takes_last_hop_not_first(monkeypatch):
    """SEC-011 取的必须是**右侧**可信跳，不是客户端可控的左侧。"""
    from starlette.requests import Request

    def make(xff: str, peer="10.0.0.9"):
        scope = {
            "type": "http", "headers": [(b"x-forwarded-for", xff.encode())],
            "client": (peer, 1234), "method": "GET", "path": "/", "query_string": b"",
        }
        return Request(scope)

    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    # 客户端伪造了两个前缀 IP，真实 IP 由反代追加在最后
    assert client_ip(make("1.2.3.4, 5.6.7.8, 198.51.100.7")) == "198.51.100.7"

    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    assert client_ip(make("1.2.3.4, 5.6.7.8, 198.51.100.7")) == "5.6.7.8"

    # XFF 比预期短（说明没走预期代理链）→ 退回 socket 对端，绝不采信 XFF
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 3)
    assert client_ip(make("1.2.3.4")) == "10.0.0.9"

    # 未配代理时完全忽略 XFF
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)
    assert client_ip(make("1.2.3.4, 5.6.7.8")) == "10.0.0.9"


# ---------- SEC-052 认证失败自动封禁 ----------
def test_repeated_login_failures_trigger_ban(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 3)
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_SECONDS", 300)
    register(client, "13900002222", "受害者")

    codes = []
    for _ in range(6):
        from app.core.ratelimit import reset as rl_reset

        rl_reset()  # 单独验证封禁逻辑，不让限流先拦下
        codes.append(client.post("/api/v1/auth/login",
                                 json={"phone": "13900002222", "password": "wrong-pass"}
                                 ).status_code)
    assert 403 in codes, f"连续认证失败没有触发封禁：{codes}"
    body = client.post("/api/v1/auth/login",
                       json={"phone": "13900002222", "password": "pass123456"}).json()
    assert body["detail"]["code"] == "temporarily_banned"  # 封禁期内正确密码也拒


def test_successful_login_clears_failure_counter(client, monkeypatch):
    """偶发输错不该累积成封禁——成功一次即清零。"""
    from app.core.ratelimit import reset as rl_reset

    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 3)
    register(client, "13900003333", "手滑用户")
    for _ in range(2):
        rl_reset()
        client.post("/api/v1/auth/login",
                    json={"phone": "13900003333", "password": "wrong"})
    rl_reset()
    ok = client.post("/api/v1/auth/login",
                     json={"phone": "13900003333", "password": "pass123456"})
    assert ok.status_code == 200
    for _ in range(2):
        rl_reset()
        client.post("/api/v1/auth/login",
                    json={"phone": "13900003333", "password": "wrong"})
    rl_reset()
    again = client.post("/api/v1/auth/login",
                        json={"phone": "13900003333", "password": "pass123456"})
    assert again.status_code == 200, "成功登录未清零失败计数"


def test_admin_can_unban(client, monkeypatch):
    """误封公司出口 IP 会挡住一整栋楼，必须能人工解除。"""
    from app.modules.account.models import User

    from app.core.db import SessionLocal

    admin = register(client, "13900004444", "管理员")
    with SessionLocal() as db:
        row = db.get(User, admin["id"])
        row.is_admin = True
        db.add(row)
        db.commit()

    guard.note_auth_failure("203.0.113.99")
    monkeypatch.setattr(settings, "AUTH_FAIL_BAN_THRESHOLD", 1)
    guard.note_auth_failure("203.0.113.99")
    assert guard.ban_remaining("203.0.113.99") > 0

    board = client.get("/api/v1/admin/security", headers=auth(admin)).json()
    assert any(r["ip"] == "203.0.113.99" for r in board["banned"])

    r = client.post("/api/v1/admin/security/unban", json={"ip": "203.0.113.99"},
                    headers=auth(admin))
    assert r.status_code == 200
    assert guard.ban_remaining("203.0.113.99") == 0


def test_security_board_requires_admin(client):
    user = register(client, "13900005555", "普通人")
    assert client.get("/api/v1/admin/security", headers=auth(user)).status_code == 403


# ---------- SEC-012 全局写限流兜底 ----------
def test_global_write_limit_protects_unlisted_endpoints(client, monkeypatch):
    """新端点忘了加限流也不至于裸奔——中间件按 IP 兜底。"""
    monkeypatch.setattr(settings, "WRITE_RATE_PER_MINUTE", 5)
    codes = [client.post("/api/v1/reports",
                         json={"target_type": "task", "target_id": 1, "reason": "spam"}
                         ).status_code for _ in range(10)]
    assert 429 in codes, f"全局写限流未生效：{codes}"


def test_read_requests_not_write_limited(client, monkeypatch):
    """读请求不受写限流影响，否则正常浏览会被误杀。"""
    monkeypatch.setattr(settings, "WRITE_RATE_PER_MINUTE", 2)
    codes = [client.get("/api/v1/tasks").status_code for _ in range(10)]
    assert all(c == 200 for c in codes), codes


def test_probes_exempt_from_write_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "WRITE_RATE_PER_MINUTE", 1)
    for _ in range(5):
        assert client.get("/healthz").status_code == 200


# ---------- SEC-002 安全响应头 ----------
def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_hsts_only_in_prod(client, monkeypatch):
    """开发环境不能发 HSTS——一旦发了，本地浏览器会强制 HTTPS 直到过期。"""
    assert "Strict-Transport-Security" not in client.get("/healthz").headers
    monkeypatch.setattr(settings, "ENV", "prod")
    assert "Strict-Transport-Security" in client.get("/healthz").headers


# ---------- SEC-033 上传响应加固 ----------
def test_uploaded_file_cannot_be_executed_as_script(client):
    import base64

    user = register(client, "13900006666", "上传者")
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()
    url = client.post("/api/v1/files",
                      json={"content_type": "image/png", "data_base64": png},
                      headers=auth(user)).json()["url"]
    r = client.get(url)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in r.headers["Content-Security-Policy"]


# ---------- SEC-053 生产自检 ----------
def test_prod_selfcheck_rejects_insecure_boundary(monkeypatch):
    from app.vendors import registry

    monkeypatch.setattr(registry.settings, "ENV", "prod")
    monkeypatch.setattr(registry.settings, "CORS_ORIGINS", "*")
    monkeypatch.setattr(registry.settings, "EXPOSE_DOCS", True)
    monkeypatch.setattr(registry.settings, "TRUSTED_PROXY_HOPS", 0)
    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    message = str(exc.value)
    assert "CORS" in message
    assert "API 文档" in message
    assert "TRUSTED_PROXY_HOPS" in message


def test_docs_exposed_in_dev(client):
    assert client.get("/openapi.json").status_code == 200
