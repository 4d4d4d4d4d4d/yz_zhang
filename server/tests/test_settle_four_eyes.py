"""SEC-061c / PAY-042b 大额平台结算的四眼（148 号 spec）。

提现早就有「两个不同管理员先后确认」（PAY-042）；平台结算把佣金从平台账户划走，却一个人就能做完。
"""
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.admin.models import AdminAudit
from app.modules.wallet import service as wallet
from tests.conftest import auth, make_admin

API = "/api/v1/admin/platform-finance"


def _fin(client, phone, roles=("finance",)):
    a = make_admin(client, phone, f"财务{phone[-2:]}")
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = list(roles)
        db.commit()
    return a


def _fund_platform(cents):
    with SessionLocal() as db:
        wallet.get_or_create(db, wallet.PLATFORM_USER_ID).available_cents += cents
        db.commit()


def _balance():
    with SessionLocal() as db:
        return wallet.get_or_create(db, wallet.PLATFORM_USER_ID).available_cents


def test_small_settle_is_still_one_step(client, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_SETTLE_DUAL_APPROVAL_CENTS", 5000)
    _fund_platform(10000)
    a = _fin(client, "13800270001")
    r = client.post(f"{API}/settle", json={"amount_cents": 4999}, headers=auth(a)).json()
    assert r == {"settled_cents": 4999, "balance_cents": 5001}


def test_large_settle_waits_for_a_different_finance_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_SETTLE_DUAL_APPROVAL_CENTS", 5000)
    _fund_platform(20000)
    a, b = _fin(client, "13800270002"), _fin(client, "13800270003")
    r = client.post(f"{API}/settle", json={"amount_cents": 8000, "memo": "季度对公结算"}, headers=auth(a)).json()
    assert r["status"] == "awaiting_second" and r["amount_cents"] == 8000
    assert _balance() == 20000, "发起不动钱"
    pending = client.get(f"{API}/settle-requests", headers=auth(b)).json()
    assert [(x["id"], x["requested_by"], x["memo"]) for x in pending] == [(r["request_id"], a["id"], "季度对公结算")]
    same = client.post(f"{API}/settle-requests/{r['request_id']}/approve", headers=auth(a))
    assert same.status_code == 400 and same.json()["detail"]["code"] == "same_approver"
    ok = client.post(f"{API}/settle-requests/{r['request_id']}/approve", headers=auth(b)).json()
    assert ok["status"] == "settled" and ok["decided_by"] == b["id"] and ok["balance_cents"] == 12000
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(ok, "PlatformSettleApproved")
    assert _balance() == 12000
    again = client.post(f"{API}/settle-requests/{r['request_id']}/approve", headers=auth(b))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "settle_already_decided"
    with SessionLocal() as db:
        actions = [x.action for x in db.query(AdminAudit).filter(AdminAudit.target_type == "platform_settle").order_by(AdminAudit.id)]
    assert actions == ["platform_settle_request", "platform_settle"]


def test_reject_needs_a_reason_unless_withdrawn_by_the_requester(client, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_SETTLE_DUAL_APPROVAL_CENTS", 5000)
    _fund_platform(20000)
    a, b = _fin(client, "13800270004"), _fin(client, "13800270005")
    r1 = client.post(f"{API}/settle", json={"amount_cents": 6000}, headers=auth(a)).json()
    bad = client.post(f"{API}/settle-requests/{r1['request_id']}/reject", json={}, headers=auth(b))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "reason_required"
    rej = client.post(f"{API}/settle-requests/{r1['request_id']}/reject", json={"reason": "金额与对账单不符"}, headers=auth(b)).json()
    assert rej["status"] == "rejected" and rej["decision_reason"] == "金额与对账单不符"
    r2 = client.post(f"{API}/settle", json={"amount_cents": 6000}, headers=auth(a)).json()
    own = client.post(f"{API}/settle-requests/{r2['request_id']}/reject", json={}, headers=auth(a)).json()
    assert own["decision_reason"] == "发起人撤回"
    assert _balance() == 20000


def test_balance_is_checked_when_requesting_and_again_when_confirming(client, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_SETTLE_DUAL_APPROVAL_CENTS", 5000)
    _fund_platform(9000)
    a, b = _fin(client, "13800270006"), _fin(client, "13800270007")
    over = client.post(f"{API}/settle", json={"amount_cents": 99999}, headers=auth(a))
    assert over.status_code == 400 and over.json()["detail"]["code"] == "insufficient_platform_balance"
    r = client.post(f"{API}/settle", json={"amount_cents": 8000}, headers=auth(a)).json()
    client.post(f"{API}/settle", json={"amount_cents": 4000}, headers=auth(b))   # 小额先划走了一部分
    late = client.post(f"{API}/settle-requests/{r['request_id']}/approve", headers=auth(b))
    assert late.status_code == 400 and late.json()["detail"]["code"] == "insufficient_platform_balance"
    assert _balance() == 5000


def test_only_finance(client):
    ops = _fin(client, "13800270008", roles=("ops",))
    for method, path in (("get", "/settle-requests"), ("post", "/settle-requests/1/approve"), ("post", "/settle-requests/1/reject")):
        r = getattr(client, method)(f"{API}{path}", headers=auth(ops), **({"json": {}} if method == "post" else {}))
        assert r.json()["detail"]["code"] == "admin_role_required", path


def test_shape(client, monkeypatch):
    from tests.test_client_shape_alignment import _assert_shape

    monkeypatch.setattr(settings, "PLATFORM_SETTLE_DUAL_APPROVAL_CENTS", 5000)
    _fund_platform(9000)
    a = _fin(client, "13800270009")
    r = client.post(f"{API}/settle", json={"amount_cents": 6000}, headers=auth(a)).json()
    _assert_shape(r, "PlatformSettlePending")
    rows = client.get(f"{API}/settle-requests", headers=auth(a)).json()
    first = rows[0]
    _assert_shape(first, "PlatformSettleRequestRow")
