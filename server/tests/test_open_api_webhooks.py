"""API 开放接口 + HOOK Webhook（54 号 spec）。

起点：全站唯一的身份是**用户会话 token**，那是给**人**用的。
最省事的做法是「让集成方存一个用户 token」，三条都不成立——
会话会被吊销（用户改密后对方集成第二天全挂且不知道为什么）、
权限全有（能提现、能改密、能注销）、没法审计。

所以 API Key 是另一类主体，不是用户凭证的别名。
"""
import json

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.openapi import service as api_service
from app.modules.openapi.models import SCOPES, ApiKey, Webhook, WebhookDelivery
from tests.conftest import JOB_HEADERS, auth, ban_user_row, register, topup, verify_user
from tests.test_task_flow import publish_task


def make_key(client, user, scopes=("tasks:read",), name="集成"):
    r = client.post("/api/v1/developer/api-keys",
                    json={"name": name, "scopes": list(scopes)}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def api(key: str) -> dict:
    return {"X-API-Key": key}


# --------------------------------------------------------- API-001 只显示一次
def test_api001_plaintext_key_is_shown_once_and_only_hashed_at_rest(client, requester):
    """与密码同一条道理：能解出来就意味着有人能解出来。"""
    body = make_key(client, requester)
    raw = body["key"]
    assert raw.startswith("pk_")
    assert "唯一一次" in body["warning"]

    listed = client.get("/api/v1/developer/api-keys", headers=auth(requester)).json()
    assert all("key" not in row for row in listed), "列表里回显了完整密钥"
    assert listed[0]["key_prefix"] in raw and len(listed[0]["key_prefix"]) < len(raw)

    with SessionLocal() as db:
        row = db.get(ApiKey, body["id"])
        assert row.key_hash != raw and len(row.key_hash) == 64
        assert raw not in row.key_hash


def test_api001_rotation_invalidates_the_old_key_immediately(client, requester):
    """明文找不回来，所以轮换是「丢了怎么办」的唯一出路，必须提供。"""
    old = make_key(client, requester)
    assert client.get("/api/v1/open/v1/tasks", headers=api(old["key"])).status_code == 200

    new = client.post(f"/api/v1/developer/api-keys/{old['id']}/rotate",
                      headers=auth(requester)).json()
    assert client.get("/api/v1/open/v1/tasks", headers=api(old["key"])).status_code == 403
    assert client.get("/api/v1/open/v1/tasks", headers=api(new["key"])).status_code == 200


def test_revoked_key_stops_working(client, requester):
    body = make_key(client, requester)
    client.delete(f"/api/v1/developer/api-keys/{body['id']}", headers=auth(requester))
    assert client.get("/api/v1/open/v1/tasks", headers=api(body["key"])).status_code == 403


# ------------------------------------------------------------- API-002 Scope
def test_api002_missing_scope_is_rejected_and_says_which_one(client, requester):
    body = make_key(client, requester, scopes=("tasks:read",))
    r = client.get("/api/v1/open/v1/wallet", headers=api(body["key"]))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "insufficient_scope"
    assert "wallet:read" in r.json()["detail"]["message"], "没说清楚缺哪个 scope"


def test_api002_there_is_no_money_moving_scope_at_all(client):
    """**出金是这个平台上唯一不可逆的动作。**

    集成方的 key 泄露概率远高于用户密码（它躺在 CI 变量、日志、截图里），
    而一次错误出金是追不回来的。所以这一批不给 API Key 任何动钱的能力。
    """
    for s in SCOPES:
        assert not s.startswith("wallet:write"), s
        assert "withdraw" not in s and "payout" not in s and "transfer" not in s, s
    assert "wallet:read" in SCOPES          # 只读是可以的

    from app.main import app

    open_paths = [p for p in app.openapi()["paths"] if "/open/v1/" in p]
    assert open_paths, "开放 API 一个端点都没有？"
    for p in open_paths:
        for word in ("withdraw", "topup", "transfer", "payout", "deactivate", "password"):
            assert word not in p, f"开放 API 暴露了动钱/改账号的端点：{p}"


def test_api002_unknown_scope_is_rejected_at_creation(client, requester):
    r = client.post("/api/v1/developer/api-keys",
                    json={"name": "坏的", "scopes": ["wallet:write"]},
                    headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_scope"
    assert "没有任何动钱的范围" in r.json()["detail"]["message"]


def test_api002_empty_scope_is_rejected(client, requester):
    r = client.post("/api/v1/developer/api-keys", json={"name": "空", "scopes": []},
                    headers=auth(requester))
    assert r.status_code == 400


def test_scopes_endpoint_explains_why_there_is_no_write_money_scope(client):
    doc = client.get("/api/v1/developer/scopes").json()
    assert "不可逆" in doc["notice"]
    assert {s["key"] for s in doc["scopes"]} == set(SCOPES)


# ------------------------------------------------- API-003 不能超过所属用户
def test_api003_banning_the_user_kills_their_api_key(client, requester):
    """**封禁只封了人、没封住机器**，那封禁就是假的。"""
    body = make_key(client, requester)
    assert client.get("/api/v1/open/v1/tasks", headers=api(body["key"])).status_code == 200
    ban_user_row(requester["id"])
    r = client.get("/api/v1/open/v1/tasks", headers=api(body["key"]))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "account_banned"


def test_api003_key_only_sees_its_owners_data(client, requester, worker):
    """Key 是用户授权给机器的一个子集，不是独立的权限来源。"""
    topup(client, requester, 50000)
    mine = publish_task(client, requester, title="我的任务")
    others = publish_task(client, worker, title="别人的任务")
    body = make_key(client, requester)

    rows = client.get("/api/v1/open/v1/tasks", headers=api(body["key"])).json()
    ids = {t["id"] for t in rows}
    assert mine["id"] in ids and others["id"] not in ids
    assert client.get(f"/api/v1/open/v1/tasks/{others['id']}",
                      headers=api(body["key"])).status_code == 404


def test_api004_api_key_cannot_call_session_only_endpoints(client, requester):
    """会话专属的端点（改密、提现、注销）不接受 API Key。"""
    body = make_key(client, requester, scopes=tuple(SCOPES))
    for method, path in (("POST", "/api/v1/wallet/withdraw"),
                         ("POST", "/api/v1/users/me/deactivate"),
                         ("GET", "/api/v1/users/me")):
        r = client.request(method, path, headers=api(body["key"]), json={})
        assert r.status_code in (403, 422), f"{path} 居然接受了 API Key：{r.status_code}"


def test_missing_key_is_rejected(client):
    r = client.get("/api/v1/open/v1/tasks")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "api_key_required"


# ------------------------------------------------------------ HOOK-001 签名
def test_hook001_signature_covers_the_timestamp(client):
    """**只签 body 的话，攻击者可以拿一个旧请求原样重放，签名照样对得上。**"""
    secret = "s3cr3t"
    body = '{"event":"task.completed"}'
    now = utcnow()
    ts = str(int(now.timestamp()))
    sig = api_service.sign(secret, ts, body)

    assert api_service.verify(secret, ts, body, sig, now=now) is True
    # 换个时间戳，同样的签名就不成立了——这正是「时间戳进签名」的意义
    assert api_service.verify(secret, str(int(ts) + 1), body, sig, now=now) is False


def test_hook001_old_requests_are_rejected(client):
    secret = "s3cr3t"
    body = "{}"
    now = utcnow()
    old_ts = str(int(now.timestamp()) - api_service.SIGNATURE_TOLERANCE_SECONDS - 10)
    sig = api_service.sign(secret, old_ts, body)
    assert api_service.verify(secret, old_ts, body, sig, now=now) is False


def test_hook001_wrong_secret_fails(client):
    now = utcnow()
    ts = str(int(now.timestamp()))
    sig = api_service.sign("right", ts, "{}")
    assert api_service.verify("wrong", ts, "{}", sig, now=now) is False


def test_hook001_each_webhook_gets_its_own_secret(client, requester, worker):
    """一个泄露不该让所有人的签名都可伪造。"""
    a = client.post("/api/v1/developer/webhooks",
                    json={"url": "https://a.example/hook", "events": ["task.completed"]},
                    headers=auth(requester)).json()
    b = client.post("/api/v1/developer/webhooks",
                    json={"url": "https://b.example/hook", "events": ["task.completed"]},
                    headers=auth(worker)).json()
    assert a["secret"] != b["secret"] and len(a["secret"]) >= 20


def test_webhook_must_be_https(client, requester):
    r = client.post("/api/v1/developer/webhooks",
                    json={"url": "http://insecure.example/hook",
                          "events": ["task.completed"]}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "https_required"


def test_unknown_event_is_rejected(client, requester):
    r = client.post("/api/v1/developer/webhooks",
                    json={"url": "https://a.example/h", "events": ["user.password_changed"]},
                    headers=auth(requester))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_event"
    # 理由要说清楚为什么不是全量开放
    assert "审过敏感字段" in r.json()["detail"]["message"]


# -------------------------------------------------------- HOOK-002 重试与停用
class FakeSender:
    def __init__(self, code=200):
        self.code, self.calls = code, []

    def __call__(self, url, body, ts, sig):
        self.calls.append({"url": url, "body": body, "ts": ts, "sig": sig})
        return self.code, "ok" if 200 <= self.code < 300 else "boom"


def _hook(client, user, events=("task.completed",)):
    return client.post("/api/v1/developer/webhooks",
                       json={"url": "https://hook.example/x", "events": list(events)},
                       headers=auth(user)).json()


def test_hook002_successful_delivery_is_recorded(client, requester):
    hook = _hook(client, requester)
    sender = FakeSender(200)
    with SessionLocal() as db:
        api_service.enqueue(db, "task.completed", {"task_id": 1, "status": "completed"})
        db.commit()
        result = api_service.deliver_pending(db, sender=sender)
        db.commit()
    assert result["sent"] == 1
    rows = client.get(f"/api/v1/developer/webhooks/{hook['id']}/deliveries",
                      headers=auth(requester)).json()
    assert rows[0]["status"] == "delivered" and rows[0]["response_code"] == 200


def test_hook002_failure_retries_then_disables_and_notifies(client, requester):
    """**悄悄停掉比不停更坏**——对方会以为平台根本没有事件。"""
    hook = _hook(client, requester)
    sender = FakeSender(500)
    with SessionLocal() as db:
        for i in range(api_service.MAX_CONSECUTIVE_FAILURES):
            api_service.enqueue(db, "task.completed", {"task_id": i})
            db.commit()
            # 每轮都把 next_attempt_at 拨到现在，跳过退避等待
            for d in db.query(WebhookDelivery).filter(
                    WebhookDelivery.status.in_(("pending", "failed"))).all():
                d.next_attempt_at = utcnow()
            db.commit()
            api_service.deliver_pending(db, sender=sender)
            db.commit()
        disabled = db.get(Webhook, hook["id"]).active

    assert disabled is False, "连续失败没有自动停用"
    hooks = client.get("/api/v1/developer/webhooks", headers=auth(requester)).json()
    assert "自动停用" in hooks[0]["disabled_reason"]
    notices = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("Webhook" in n["title"] for n in notices), "停用了却没通知拥有者"


def test_hook002_retry_uses_backoff_not_immediate(client, requester):
    _hook(client, requester)
    sender = FakeSender(500)
    with SessionLocal() as db:
        api_service.enqueue(db, "task.completed", {"task_id": 1})
        db.commit()
        api_service.deliver_pending(db, sender=sender)
        db.commit()
        d = db.query(WebhookDelivery).first()
        assert d.status == "failed"
        assert d.next_attempt_at > utcnow(), "失败后立刻重试，会把对方打挂"


def test_hook002_delivery_record_exists_so_disputes_have_an_exit(client, requester):
    """没有记录的话，集成方报「我没收到」时平台只能说「我发了」——
    两边都无法证明，这种争执没有出口。"""
    hook = _hook(client, requester)
    sender = FakeSender(404)
    with SessionLocal() as db:
        api_service.enqueue(db, "task.completed", {"task_id": 7})
        db.commit()
        api_service.deliver_pending(db, sender=sender)
        db.commit()
    rows = client.get(f"/api/v1/developer/webhooks/{hook['id']}/deliveries",
                      headers=auth(requester)).json()
    assert rows[0]["response_code"] == 404 and rows[0]["attempts"] == 1


def test_only_the_owner_sees_delivery_records(client, requester, worker):
    hook = _hook(client, requester)
    r = client.get(f"/api/v1/developer/webhooks/{hook['id']}/deliveries",
                   headers=auth(worker))
    assert r.status_code == 404


# ---------------------------------------------------------- HOOK-003 不发敏感
def test_hook003_sensitive_fields_never_leave_the_platform(client, requester):
    """**webhook 的接收端是我们控制不了的。**

    一个写进对方日志的手机号，就是我们泄露的手机号。
    """
    _hook(client, requester)
    sender = FakeSender(200)
    with SessionLocal() as db:
        api_service.enqueue(db, "task.completed", {
            "task_id": 1, "status": "completed",
            "phone": "13800000000", "real_name": "张三",
            "address_exact": "静安区南京西路 1234 号", "amount_cents": 20000,
            "nested": {"phone": "13900000000", "ok": "keep"},
        })
        db.commit()
        api_service.deliver_pending(db, sender=sender)
        db.commit()

    body = json.loads(sender.calls[0]["body"])["data"]
    for leaked in ("phone", "real_name", "address_exact", "amount_cents"):
        assert leaked not in body, f"{leaked} 出站了"
    assert "phone" not in body["nested"], "嵌套里的手机号漏了"
    assert body["nested"]["ok"] == "keep" and body["task_id"] == 1


def test_hook003_headers_carry_signature_and_timestamp(client, requester):
    hook = _hook(client, requester)
    sender = FakeSender(200)
    with SessionLocal() as db:
        api_service.enqueue(db, "task.completed", {"task_id": 1})
        db.commit()
        api_service.deliver_pending(db, sender=sender)
        db.commit()
        secret = db.get(Webhook, hook["id"]).secret

    call = sender.calls[0]
    assert api_service.verify(secret, call["ts"], call["body"], call["sig"]) is True


def test_job_endpoint_is_registered_and_token_guarded(client):
    r = client.post("/api/v1/openapi/jobs/deliver-webhooks")
    assert r.status_code == 403
    ok = client.post("/api/v1/openapi/jobs/deliver-webhooks", headers=JOB_HEADERS)
    assert ok.status_code == 200
