"""PAY-007 提现风控（业界惯例）：日限额硬拒 + 大额冻结人审 + 守恒不破。"""
import sqlalchemy as sa

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.modules.risk.service import reconcile

from .conftest import auth, register, topup, verify_user


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def _make_admin(client, phone):
    admin = register(client, phone, "风控员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def _rich_user(client, phone, amount=20_000_000):
    from .conftest import bind_payout

    u = register(client, phone, "有钱人")
    verify_user(client, u, "富户")
    bind_payout(client, u, holder="富户")
    topup(client, u, amount)
    return u


def test_small_withdraw_immediate_large_goes_review(client):
    admin = _make_admin(client, "22000000000")
    u = _rich_user(client, "22000000001")

    # 小额：即时出账
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 5000}, headers=auth(u))
    assert r.json()["status"] == "done"
    _assert_conserved()

    # 大额：冻结 + 待审，钱未出账
    big = settings.LARGE_WITHDRAW_CENTS
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": big}, headers=auth(u))
    body = r.json()
    assert body["status"] == "pending_review" and body["frozen_cents"] == big
    _assert_conserved()  # 冻结有据（withdraw_frozen 计入对账口径）

    # 批准：冻结划出，守恒仍成立
    req_id = body["request_id"]
    r = client.post(f"/api/v1/wallet/withdraw-requests/{req_id}/approve", headers=auth(admin))
    assert r.json()["status"] == "approved"
    w = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert w["frozen_cents"] == 0
    _assert_conserved()
    # 重复裁决被拒
    r = client.post(f"/api/v1/wallet/withdraw-requests/{req_id}/approve", headers=auth(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "request_closed"


def test_reject_refunds_to_available(client):
    admin = _make_admin(client, "22000000010")
    u = _rich_user(client, "22000000011")
    before = client.get("/api/v1/wallet", headers=auth(u)).json()["available_cents"]

    big = settings.LARGE_WITHDRAW_CENTS + 5000
    req_id = client.post("/api/v1/wallet/withdraw",
                         json={"amount_cents": big}, headers=auth(u)).json()["request_id"]
    client.post(f"/api/v1/wallet/withdraw-requests/{req_id}/reject", headers=auth(admin))
    w = client.get("/api/v1/wallet", headers=auth(u)).json()
    assert w["available_cents"] == before and w["frozen_cents"] == 0  # 全额退回
    _assert_conserved()


def test_daily_limit_counts_done_plus_pending(client):
    u = _rich_user(client, "22000000021")
    limit = settings.WITHDRAW_DAILY_LIMIT_CENTS

    # 一笔大额待审占掉大部分额度
    client.post("/api/v1/wallet/withdraw",
                json={"amount_cents": limit - 100}, headers=auth(u))
    # 再提 200 → 超日限额（待审也计入）
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 200}, headers=auth(u))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "daily_limit_exceeded"
    _assert_conserved()


def test_withdraw_review_admin_only(client):
    u = _rich_user(client, "22000000031")
    req_id = client.post("/api/v1/wallet/withdraw",
                         json={"amount_cents": settings.LARGE_WITHDRAW_CENTS},
                         headers=auth(u)).json()["request_id"]
    # 普通用户不能审自己的提现
    r = client.post(f"/api/v1/wallet/withdraw-requests/{req_id}/approve", headers=auth(u))
    assert r.status_code == 403
    r = client.get("/api/v1/wallet/withdraw-requests", headers=auth(u))
    assert r.status_code == 403
