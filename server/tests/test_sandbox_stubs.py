"""STUB-050~056 沙箱桩验证（27 号 spec）。

抽象层只发布退化实现等于没预留接口——换供应商那天才第一次执行到这些分支，
而那正是最不能出错的时刻。这套测试让**合规形态**（存管 + 可靠签名 +
第三方存证）的完整路径现在就被覆盖。

**同时守住红线**：补桩不能削弱生产拦截，沙箱与 mock 一视同仁地被拒。
"""
import pytest

from app.core.config import settings
from app.core.db import SessionLocal
from app.vendors import ledger, notary, registry, sandbox, signature

from .conftest import JOB_HEADERS, auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


@pytest.fixture()
def custody(monkeypatch):
    """把全套沙箱桩装上：存管 + 沙箱支付 + 可靠签名 + 第三方存证。"""
    sandbox.reset_sandbox()
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "sandbox")
    monkeypatch.setattr(settings, "LEDGER_BACKEND", "custody")
    monkeypatch.setattr(settings, "SIGNATURE_PROVIDER", "sandbox-ca")
    monkeypatch.setattr(settings, "NOTARY_PROVIDER", "sandbox-notary")
    registry.reset()
    ledger.reset()
    signature.set_signature_provider(None)
    notary.set_notary(None)
    yield
    sandbox.reset_sandbox()
    registry.reset()
    ledger.reset()
    signature.set_signature_provider(None)
    notary.set_notary(None)


# ---------- STUB-050 存管闭环 ----------
def test_full_loop_runs_in_custody_mode(client, requester, worker, custody):
    """合规形态下跑通完整闭环：钱进存管专户，平台只发分账指令。

    这条路径此前**一行测试都没有**——`CustodyLedger` 遇到 mock 支付直接抛错。
    """
    topup(client, requester, 100000)
    assert sandbox.BOOK.balances.get(sandbox.ESCROW_ACCOUNT) == 100000, \
        "付款没有进存管专户，说明仍是「钱经过平台」的形态"

    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r.status_code == 200, r.text

    body = client.get(f"/api/v1/contracts/{cid}/settlements", headers=auth(requester)).json()
    assert body["sandbox"] is False  # 存管形态不再是沙箱标识
    order = body["settlements"][0]
    assert order["backend"] == "custody"
    assert order["custody_ref"], "存管模式下必须带回存管方流水号"
    assert sum(s["amount_cents"] for s in order["splits"]) == order["total_cents"]

    # 存管账簿里执行者与平台各自收到钱
    fee = 30000 * 800 // 10000
    assert sandbox.BOOK.balances[f"custody:user:{worker['id']}"] == 30000 - fee
    assert sandbox.BOOK.balances["custody:user:0"] == fee


def test_money_invariants_hold_in_custody_mode(client, requester, worker, custody):
    from app.modules.risk import service as risk

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))

    with SessionLocal() as db:
        assert risk.reconcile(db)["ok"] is True


def test_custody_ledger_rejects_provider_without_split(client, custody, monkeypatch):
    """切回 mock 支付（没有 split_settle）→ 明确报错，不静默退回内部账本。"""
    from app.vendors.base import VendorError

    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "mock")
    registry.reset()
    with SessionLocal() as db:
        with pytest.raises(VendorError) as exc:
            ledger.get_ledger().execute(db, type("O", (), {"id": 1})(), [])
    assert exc.value.code == "custody_unsupported"


# ---------- STUB-052 失败注入 ----------
def test_settlement_failure_rolls_back(client, requester, worker, custody, monkeypatch):
    """STUB-013/052 分账失败 → 整体回滚，不留半途状态。

    失败路径比成功路径更需要提前跑过——真出问题时没有第二次机会。
    """
    from app.modules.finance.models import SettlementOrder

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))

    before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    monkeypatch.setenv(sandbox.FAIL_MODE_ENV, "split_settle")
    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r.status_code >= 400, "分账失败却返回成功"

    after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert after == before, "分账失败但钱已经动了 —— 没有回滚"
    with SessionLocal() as db:
        assert db.query(SettlementOrder).count() == 0, "失败的指令不该留在库里"


# ---------- STUB-051 补桩不削弱拦截（最容易做错的地方）----------
def test_sandbox_providers_still_rejected_in_production(monkeypatch):
    """沙箱形态虽真，仍不接任何真实机构 —— 生产必须一视同仁地拒绝。"""
    monkeypatch.setattr(registry.settings, "ENV", "prod")
    for kind in ("PAYMENT", "SMS", "KYC", "MODERATION"):
        monkeypatch.setattr(registry.settings, f"{kind}_PROVIDER", "sandbox")
    monkeypatch.setattr(registry.settings, "LEDGER_BACKEND", "custody")
    monkeypatch.setattr(registry.settings, "SIGNATURE_PROVIDER", "sandbox-ca")
    monkeypatch.setattr(registry.settings, "NOTARY_PROVIDER", "sandbox-notary")
    monkeypatch.setattr(registry.settings, "JWT_SECRET", "strong-secret")
    monkeypatch.setattr(registry.settings, "JOB_TOKEN", "strong-token")
    monkeypatch.setattr(registry.settings, "DATABASE_URL", "postgresql+psycopg://x/y")
    monkeypatch.setattr(registry.settings, "CORS_ORIGINS", "https://a.example")
    monkeypatch.setattr(registry.settings, "EXPOSE_DOCS", False)
    monkeypatch.setattr(registry.settings, "TRUSTED_PROXY_HOPS", 1)

    with pytest.raises(RuntimeError) as exc:
        registry.startup_check()
    message = str(exc.value)
    assert "sandbox" in message
    assert "PLATFORM_SIGNATURE_PROVIDER" in message
    assert "PLATFORM_NOTARY_PROVIDER" in message


def test_provider_grade_three_states(monkeypatch):
    """STUB-003 三态区分：production / sandbox / mock。"""
    assert registry.provider_grade("payment", "mock") == "mock"
    assert registry.provider_grade("payment", "sandbox") == "sandbox"
    assert registry.provider_grade("payment", "acme-pay") == "production"
    assert registry.provider_grade("moderation", "local") == "mock"


def test_admin_panel_shows_grade(client):
    from app.modules.account.models import User

    admin = register(client, "13800011001", "管理员")
    with SessionLocal() as db:
        row = db.get(User, admin["id"])
        row.is_admin = True
        db.add(row)
        db.commit()
    body = client.get("/api/v1/admin/vendors", headers=auth(admin)).json()
    assert all(v["grade"] in ("production", "sandbox", "mock") for v in body["vendors"])


# ---------- STUB-053 可靠签名沙箱 ----------
def test_sandbox_ca_upgrades_reliability_and_still_detects_tampering(
    client, requester, worker, custody
):
    """桩的价值在于把契约钉死：升级证明力的同时，篡改检出必须依然成立。"""
    from app.modules.contract.models import Contract

    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    cid = match_and_fund(client, requester, worker, task)

    body = client.get(f"/api/v1/contracts/{cid}/signatures", headers=auth(requester)).json()
    assert body["valid"] is True
    assert all(s["reliability"] == "qualified" for s in body["signatures"])
    assert "构成可靠电子签名" in body["reliability_note"]

    with SessionLocal() as db:
        row = db.get(Contract, cid)
        row.terms += "\n（偷改）"
        db.add(row)
        db.commit()
    after = client.get(f"/api/v1/contracts/{cid}/signatures", headers=auth(requester)).json()
    assert after["valid"] is False, "换了 qualified 签名反而检不出篡改"


def test_sandbox_signature_verify_rejects_forgery(custody):
    """伪造签名值必须验不过——只返回固定值的桩没有意义。"""
    provider = signature.get_signature_provider()
    result = provider.sign(7, "a" * 64, {})
    assert provider.verify(7, "a" * 64, result) is True
    assert provider.verify(8, "a" * 64, result) is False          # 换人
    assert provider.verify(7, "b" * 64, result) is False          # 换文本
    result.signature = "deadbeef"
    assert provider.verify(7, "a" * 64, result) is False          # 伪造签名


# ---------- STUB-054 第三方存证沙箱 ----------
def test_sandbox_notary_marks_backed(client, requester, worker, custody):
    topup(client, requester, 100000)
    task = publish_task(client, requester, budget_cents=30000)
    match_and_fund(client, requester, worker, task)

    r = client.post("/api/v1/anchors/jobs/notarize", headers=JOB_HEADERS)
    assert r.json()["backed"] is True
    cov = client.get("/api/v1/anchors/coverage").json()
    assert cov["uncovered_entries"] == 0
    assert "全部存证均有第三方背书" in cov["note"]


# ---------- STUB-055 严格短信路径 ----------
def test_sandbox_sms_requires_requesting_code_first(client, monkeypatch):
    """mock 的固定码让「必须先请求验证码」这段逻辑永远不被执行。"""
    monkeypatch.setattr(settings, "SMS_PROVIDER", "sandbox")
    registry.reset()
    try:
        r = client.post("/api/v1/auth/register",
                        json={"phone": "13800011010", "password": "pass123456",
                              "nickname": "严格路径", "sms_code": "123456"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "sms_code_missing"

        sent = client.post("/api/v1/auth/send-code", json={"phone": "13800011010"})
        assert "dev_code" not in sent.json(), "沙箱短信不得回显验证码"
        code = registry.get_provider("sms").sent["13800011010"]

        r = client.post("/api/v1/auth/register",
                        json={"phone": "13800011010", "password": "pass123456",
                              "nickname": "严格路径", "sms_code": "000000"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "sms_code_invalid"

        r = client.post("/api/v1/auth/register",
                        json={"phone": "13800011010", "password": "pass123456",
                              "nickname": "严格路径", "sms_code": code})
        assert r.status_code == 201, r.text
    finally:
        registry.reset()


# ---------- STUB-056 eKYC 三态 ----------
def test_sandbox_kyc_manual_review(client, monkeypatch):
    """`manual` 转人工分支：不置实名，等人工复核。"""
    from app.modules.account.models import User

    monkeypatch.setattr(settings, "KYC_PROVIDER", "sandbox")
    registry.reset()
    try:
        user = register(client, "13800011020", "转人工")
        r = client.post("/api/v1/users/me/verify",
                        json={"real_name": "张三", "id_number": "110101199001019999"},
                        headers=auth(user))
        assert r.status_code == 200
        assert r.json() == {"is_verified": False, "status": "manual_review"}
        with SessionLocal() as db:
            assert db.get(User, user["id"]).is_verified is False

        failed = register(client, "13800011021", "核验失败")
        r = client.post("/api/v1/users/me/verify",
                        json={"real_name": "李四", "id_number": "110101199001010000"},
                        headers=auth(failed))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "kyc_failed"
    finally:
        registry.reset()


# ---------- STUB-032/033 其余桩 ----------
def test_sandbox_moderation_sends_media_to_review(monkeypatch):
    monkeypatch.setattr(settings, "MODERATION_PROVIDER", "sandbox")
    registry.reset()
    try:
        provider = registry.get_provider("moderation")
        assert provider.check("text", "正常内容").status == "pass"
        assert provider.check("text", "正常内容", ["/api/v1/files/x.png"]).status == "review"
        assert provider.check("text", "帮忙刷单").status == "reject"
    finally:
        registry.reset()


def test_sandbox_storage_signs_direct_upload(monkeypatch):
    """真实对象存储是「文件不经过平台」的直传形态。"""
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "sandbox")
    registry.reset()
    try:
        result = registry.get_provider("storage").sign_upload("image/png")
        assert result.data["direct_upload"] is True
        assert result.data["upload_url"].startswith("https://")
        assert result.data["expires_in"] > 0
    finally:
        registry.reset()


def test_sandbox_failure_injection_is_scoped(custody, monkeypatch):
    """失败注入只影响被点名的操作，不会把整个沙箱变成坏的。"""
    from app.vendors.base import VendorError

    provider = registry.get_provider("payment")
    monkeypatch.setenv(sandbox.FAIL_MODE_ENV, "create_payout")
    with pytest.raises(VendorError):
        provider.create_payout("o1", {"kind": "bank"}, 100)
    assert provider.create_charge("o2", 100, "x").ok is True  # 其它操作不受影响
