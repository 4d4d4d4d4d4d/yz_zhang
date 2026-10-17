"""SEC-061f / PAY-042c 四眼按金额分级与第二人级别（155 号 spec）。

V176 之后，大额提现和平台结算都要两位不同的财务先后确认。但「两位财务」对一笔 ¥2 万和一笔 ¥200 万一视同仁；
而超级管理员先批、普通财务「确认」的，等于下级给上级盖章，复核形同虚设。
"""
from app.core.admin_roles import check_second_approver, rank
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.wallet import service as wallet
from tests.conftest import auth, make_admin, money, register, topup, verify_user

SETTLE = "/api/v1/admin/platform-finance"


def _admin(client, phone, roles):
    a = make_admin(client, phone, f"管理员{phone[-2:]}")
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = list(roles)
        db.commit()
    return a


def _big_withdraw(client, phone, amount):
    u = register(client, phone, "提现的人")
    verify_user(client, u, name="提现")
    topup(client, u, amount + 1000000)
    client.put("/api/v1/wallet/payout-account", json={"kind": "bank", "account_no": f"6222{phone[-8:]}11", "holder_name": "提现"},
               headers=auth(u))
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": amount}, headers=money(auth(u)))
    assert r.status_code == 200, r.text
    return r.json()["request_id"]


def test_rank_super_above_others():
    def u(roles):
        return User(is_admin=True, admin_roles=roles)

    assert rank(u(["super"])) == 2 and rank(u(["finance"])) == 1 and rank(u([])) == 2   # 未分级按 super
    assert rank(User(is_admin=False, admin_roles=[])) == 0


def test_large_withdraw_needs_a_super_admin_as_second(client, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_SECOND_APPROVAL_CENTS", 3000000)
    amount = 3000000
    rid = _big_withdraw(client, "13800300001", amount)
    f1, f2 = _admin(client, "13800300011", ["finance"]), _admin(client, "13800300012", ["finance"])
    boss = _admin(client, "13800300013", ["super"])
    url = f"/api/v1/wallet/withdraw-requests/{rid}/approve"
    assert client.post(url, headers=auth(f1)).json()["status"] == "awaiting_second"
    row = next(r for r in client.get("/api/v1/wallet/withdraw-requests", params={"status": "awaiting_second"}, headers=auth(f2)).json() if r["id"] == rid)
    assert row["needs_super_second"] is True
    r = client.post(url, headers=auth(f2))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "second_approver_role"
    assert "30000.00" in r.json()["detail"]["message"], "门槛数字取自配置"
    with SessionLocal() as db:
        from app.modules.wallet.models import WithdrawRequest

        assert db.get(WithdrawRequest, rid).status == "awaiting_second", "被拒的第二人不能让钱动"
    assert client.post(url, headers=auth(boss)).status_code == 200


def test_below_the_line_two_finance_admins_still_suffice(client, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_SECOND_APPROVAL_CENTS", 3000000)
    rid = _big_withdraw(client, "13800300002", settings.WITHDRAW_DUAL_APPROVAL_CENTS + 100000)
    f1, f2 = _admin(client, "13800300021", ["finance"]), _admin(client, "13800300022", ["finance"])
    url = f"/api/v1/wallet/withdraw-requests/{rid}/approve"
    client.post(url, headers=auth(f1))
    row = next(r for r in client.get("/api/v1/wallet/withdraw-requests", params={"status": "awaiting_second"}, headers=auth(f2)).json() if r["id"] == rid)
    assert row["needs_super_second"] is False
    assert client.post(url, headers=auth(f2)).status_code == 200


def test_second_cannot_rank_below_first(client, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_SECOND_APPROVAL_CENTS", 10 ** 12)
    rid = _big_withdraw(client, "13800300003", settings.WITHDRAW_DUAL_APPROVAL_CENTS + 100000)
    boss, fin = _admin(client, "13800300031", ["super"]), _admin(client, "13800300032", ["finance"])
    url = f"/api/v1/wallet/withdraw-requests/{rid}/approve"
    client.post(url, headers=auth(boss))
    r = client.post(url, headers=auth(fin))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "second_approver_rank"
    boss2 = _admin(client, "13800300033", ["super"])
    assert client.post(url, headers=auth(boss2)).status_code == 200


def test_large_platform_settle_needs_a_super_admin_as_second(client, monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_SETTLE_DUAL_APPROVAL_CENTS", 5000)
    monkeypatch.setattr(settings, "SUPER_SECOND_APPROVAL_CENTS", 50000)
    with SessionLocal() as db:
        wallet.get_or_create(db, wallet.PLATFORM_USER_ID).available_cents += 200000
        db.commit()
    a, b = _admin(client, "13800300041", ["finance"]), _admin(client, "13800300042", ["finance"])
    boss = _admin(client, "13800300043", ["super"])
    req = client.post(f"{SETTLE}/settle", json={"amount_cents": 60000}, headers=auth(a)).json()
    small = client.post(f"{SETTLE}/settle", json={"amount_cents": 6000}, headers=auth(a)).json()
    rows = {x["id"]: x for x in client.get(f"{SETTLE}/settle-requests", headers=auth(b)).json()}
    assert rows[req["request_id"]]["needs_super_second"] is True and rows[small["request_id"]]["needs_super_second"] is False
    r = client.post(f"{SETTLE}/settle-requests/{req['request_id']}/approve", headers=auth(b))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "second_approver_role"
    assert client.post(f"{SETTLE}/settle-requests/{small['request_id']}/approve", headers=auth(b)).status_code == 200
    assert client.post(f"{SETTLE}/settle-requests/{req['request_id']}/approve", headers=auth(boss)).status_code == 200


def test_check_second_approver_unit(monkeypatch):
    monkeypatch.setattr(settings, "SUPER_SECOND_APPROVAL_CENTS", 100)
    fin, boss = User(is_admin=True, admin_roles=["finance"]), User(is_admin=True, admin_roles=["super"])
    check_second_approver(fin, fin, 99)
    check_second_approver(fin, boss, 100)
    check_second_approver(None, boss, 10 ** 9)
    for first, second, amount in [(fin, fin, 100), (boss, fin, 1)]:
        try:
            check_second_approver(first, second, amount)
        except Exception as e:   # noqa: BLE001
            assert getattr(e, "status_code", 0) == 403
        else:
            raise AssertionError((first.admin_roles, second.admin_roles, amount))
