"""VND-050~053 外部供应商接入抽象层验证（19 号 spec）。

重点不是「模拟实现能跑通」——那太容易了。重点是**接真实供应商时才暴露的坑**
在模拟通道下就已经被钉死：回调验签、回调重放、金额不符、幂等、熔断、
生产自检、证件号不落明文。
"""
import pytest

from app.core.db import SessionLocal
from app.vendors import base as vendor_base
from app.vendors import payment_service
from app.vendors.models import PaymentOrder, VendorCall

from .conftest import auth, register, topup, verify_user


def _order_of(user_id: int) -> PaymentOrder:
    with SessionLocal() as db:
        return (
            db.query(PaymentOrder)
            .filter(PaymentOrder.user_id == user_id)
            .order_by(PaymentOrder.id.desc())
            .first()
        )


# ---------- VND-011 两阶段充值 ----------
def test_topup_creates_order_and_credits_once(client):
    user = register(client, "13800007001", "充值者")
    r = client.post("/api/v1/wallet/topup", json={"amount_cents": 30000}, headers=auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["available_cents"] == 30000

    order = _order_of(user["id"])
    assert order.status == "succeeded"
    assert order.amount_cents == 30000
    assert order.external_ref  # 外部单号已落库，可对账

    # VND-003 外部调用留痕
    with SessionLocal() as db:
        calls = db.query(VendorCall).filter(VendorCall.kind == "payment").all()
    assert any(c.operation == "create_charge" and c.status == "succeeded" for c in calls)


# ---------- VND-012 回调验签 ----------
def test_callback_rejects_bad_signature_without_crediting(client):
    user = register(client, "13800007002", "回调测试")
    topup(client, user, 10000)
    order = _order_of(user["id"])

    payload = {"order_no": order.order_no, "amount_cents": 999999, "external_ref": "x"}
    r = client.post("/api/v1/wallet/pay/callback", json={**payload, "sign": "forged"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_signature"

    r = client.get("/api/v1/wallet", headers=auth(user))
    assert r.json()["available_cents"] == 10000  # 余额纹丝不动


def test_callback_replay_credits_only_once(client):
    """回调重放是真实支付最常见的攻击面：同一订单必须只入账一次。"""
    user = register(client, "13800007003", "重放测试")
    topup(client, user, 10000)
    order = _order_of(user["id"])

    payload = {"order_no": order.order_no, "amount_cents": 10000, "external_ref": "ext-1"}
    payload["sign"] = payment_service.make_signature(payload)
    for _ in range(3):
        r = client.post("/api/v1/wallet/pay/callback", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["replayed"] is True

    assert client.get("/api/v1/wallet", headers=auth(user)).json()["available_cents"] == 10000


def test_callback_amount_mismatch_suspends_order(client):
    """回调金额与订单不符：绝不按回调金额入账，挂起人工。"""
    user = register(client, "13800007004", "金额不符")
    with SessionLocal() as db:
        order = PaymentOrder(order_no="TP-MISMATCH-1", user_id=user["id"],
                             amount_cents=10000, provider="mock", status="pending")
        db.add(order)
        db.commit()

    payload = {"order_no": "TP-MISMATCH-1", "amount_cents": 999999, "external_ref": "ext"}
    payload["sign"] = payment_service.make_signature(payload)
    r = client.post("/api/v1/wallet/pay/callback", json=payload)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "amount_mismatch"

    with SessionLocal() as db:
        row = db.query(PaymentOrder).filter(PaymentOrder.order_no == "TP-MISMATCH-1").first()
    assert row.status == "mismatch"
    assert client.get("/api/v1/wallet", headers=auth(user)).json()["available_cents"] == 0

    # 挂起后即便补一个「正确金额」的回调也不放行——需人工核对
    good = {"order_no": "TP-MISMATCH-1", "amount_cents": 10000, "external_ref": "ext"}
    good["sign"] = payment_service.make_signature(good)
    r2 = client.post("/api/v1/wallet/pay/callback", json=good)
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "order_mismatch"


# ---------- VND-004 幂等：同幂等键不重复打供应商 ----------
def test_vendor_call_idempotency(client):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return vendor_base.VendorResult(ok=True, external_ref="ext-42")

    with SessionLocal() as db:
        for _ in range(3):
            r = vendor_base.call(db, "payment", "mock", "create_payout", {"amount_cents": 100},
                                 fn, idem_key="payout:same-key")
            assert r.external_ref == "ext-42"
        db.commit()
    assert calls["n"] == 1, "相同幂等键必须只真正调用一次外部服务"


# ---------- VND-005 熔断 ----------
def test_circuit_breaker_opens_after_repeated_failures(client):
    vendor_base.circuit_reset()

    def boom():
        raise vendor_base.VendorError("timeout", "超时", retryable=True)

    with SessionLocal() as db:
        for _ in range(vendor_base.FAIL_THRESHOLD):
            with pytest.raises(vendor_base.VendorError):
                vendor_base.call(db, "sms", "mock", "send_code", {"phone": "1"}, boom)
        db.commit()
    assert vendor_base.circuit_state("sms:mock") == "open"

    with SessionLocal() as db:
        with pytest.raises(vendor_base.VendorError) as exc:
            vendor_base.call(db, "sms", "mock", "send_code", {"phone": "1"},
                             lambda: vendor_base.VendorResult(ok=True))
    assert exc.value.code == "circuit_open"  # 冷却期内快速失败，不再打供应商
    vendor_base.circuit_reset()


# ---------- VND-002 错误收敛 ----------
def test_vendor_error_maps_to_http_status():
    retryable = vendor_base.VendorError("timeout", "超时", retryable=True).as_http()
    rejected = vendor_base.VendorError("declined", "被拒绝", retryable=False).as_http()
    assert retryable.status_code == 502 and retryable.detail["code"] == "vendor_timeout"
    assert rejected.status_code == 400 and rejected.detail["code"] == "vendor_declined"


# ---------- VND-003 留痕脱敏 ----------
def test_vendor_call_digest_redacts_secrets(client):
    with SessionLocal() as db:
        vendor_base.call(db, "sms", "mock", "send_code",
                         {"phone": "13800000000", "code": "123456", "scene": "verify"},
                         lambda: vendor_base.VendorResult(ok=True, external_ref="e"))
        db.commit()
    with SessionLocal() as db:
        row = db.query(VendorCall).order_by(VendorCall.id.desc()).first()
    assert "13800000000" not in row.request_digest
    assert "123456" not in row.request_digest
    assert "chars" in row.request_digest  # 只留字段名与长度


# ---------- VND-020/021 短信 ----------
def test_send_code_endpoint_and_ratelimit(client):
    r = client.post("/api/v1/auth/send-code", json={"phone": "13800007010"})
    assert r.status_code == 200, r.text
    assert r.json()["dev_code"] == "123456"  # 模拟通道回显
    for _ in range(3):
        r = client.post("/api/v1/auth/send-code", json={"phone": "13800007010"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "rate_limited"


def test_sms_code_stored_as_hash_only(client):
    from app.vendors.models import SmsCode

    client.post("/api/v1/auth/send-code", json={"phone": "13800007011"})
    with SessionLocal() as db:
        row = db.query(SmsCode).filter(SmsCode.phone == "13800007011").first()
    assert row is not None
    assert row.code_hash and "123456" not in row.code_hash


# ---------- VND-022/023 实名 ----------
def test_kyc_stores_digest_not_plaintext(client):
    from app.modules.account.models import User

    user = register(client, "13800007020", "实名者")
    verify_user(client, user, id_number="110101199001011234")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
    assert row.is_verified is True
    assert row.id_digest and "110101199001011234" not in row.id_digest
    assert row.id_masked.startswith("110") and row.id_masked.endswith("1234")


def test_kyc_rejects_duplicate_id_number(client):
    """同一证件号不得绑定多个账号——一人多号是补贴套利的第一步。"""
    a = register(client, "13800007021", "甲")
    b = register(client, "13800007022", "乙")
    verify_user(client, a, id_number="110101199001011234")
    r = client.post("/api/v1/users/me/verify",
                    json={"real_name": "张三", "id_number": "110101199001011234"},
                    headers=auth(b))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "id_already_bound"


def test_kyc_rejects_malformed_id(client):
    user = register(client, "13800007023", "格式错")
    r = client.post("/api/v1/users/me/verify",
                    json={"real_name": "张三", "id_number": "1101011990010"},
                    headers=auth(user))
    assert r.status_code in (400, 422)


# ---------- VND-041/042 后台面板与生产自检 ----------
def test_admin_vendor_panel_lists_mocks(client):
    from app.modules.account.models import User

    admin = register(client, "13800007030", "管理员")
    with SessionLocal() as db:
        row = db.get(User, admin["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    r = client.get("/api/v1/admin/vendors", headers=auth(admin))
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = {v["kind"]: v for v in body["vendors"]}
    assert kinds["payment"]["provider"] == "mock" and kinds["payment"]["is_mock"] is True
    assert set(body["blocking_for_production"]) == {"payment", "sms", "kyc", "moderation"}


def test_production_startup_check_blocks_mock_providers(monkeypatch):
    """VND-042 生产环境仍是模拟支付 → 启动即失败。把上线前必须完成的对接
    变成硬性拦截，而不是一行没人看的日志。"""
    from app.vendors import registry

    monkeypatch.setattr(registry.settings, "ENV", "prod")
    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    message = str(exc.value)
    assert "payment" in message
    assert "PLATFORM_JWT_SECRET" in message  # 弱密钥也一并拦下


def test_dev_startup_check_passes(monkeypatch):
    from app.vendors import registry

    monkeypatch.setattr(registry.settings, "ENV", "dev")
    registry.startup_check()  # 开发环境不拦，否则没人能本地跑起来


# ---------- VND-030 机审仍走抽象层（行为不变） ----------
def test_moderation_still_blocks_banned_words(client):
    user = register(client, "13800007040", "发布者")
    verify_user(client, user)
    topup(client, user, 100000)
    r = client.post("/api/v1/tasks",
                    json={"title": "帮忙刷单", "description": "刷单任务", "category": "跑腿代办",
                          "budget_cents": 10000, "city": "杭州"},
                    headers=auth(user))
    assert r.status_code == 400
