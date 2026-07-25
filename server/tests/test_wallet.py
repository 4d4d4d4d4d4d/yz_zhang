"""05/12 钱包：SC-020/021/022, PAY-004/005"""
from .conftest import auth, bind_payout, register, topup, verify_user


def test_wallet_topup_and_balance(client, requester):
    topup(client, requester, 10000)
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["available_cents"] == 10000 and w["escrow_cents"] == 0


def test_withdraw_requires_verification(client):
    user = register(client, "13700000001")
    topup(client, user, 5000)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=auth(user))
    assert r.status_code == 403  # ACC-020 未实名禁止提现
    verify_user(client, user)
    # PAY-005 未绑收款账户不可提现
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=auth(user))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_payout_account"
    bind_payout(client, user)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=auth(user))
    assert r.status_code == 200
    assert r.json()["available_cents"] == 4000


def test_withdraw_insufficient(client, requester):
    bind_payout(client, requester)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 999}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "insufficient_balance"


def test_sc022_ledger_traceable(client, requester):
    bind_payout(client, requester)
    topup(client, requester, 3000)
    client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=auth(requester))
    ledger = client.get("/api/v1/wallet/ledger", headers=auth(requester)).json()
    kinds = [e["kind"] for e in ledger]
    assert "topup" in kinds and "withdraw" in kinds
