"""PAY-005 收款账户绑定：提现前置 + 实名一致校验 + 账号脱敏（业界必备）。"""
from .conftest import auth, bind_payout, register, topup, verify_user


def test_withdraw_blocked_without_payout_account(client, requester):
    topup(client, requester, 10000)
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_payout_account"

    bind_payout(client, requester)  # requester 实名为「张三」
    r = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 1000}, headers=auth(requester))
    assert r.status_code == 200


def test_holder_name_must_match_real_name(client, requester):
    # 收款人姓名与实名不一致 → 拒绝（防代提/洗钱）
    r = client.put("/api/v1/wallet/payout-account",
                   json={"kind": "bank", "account_no": "6222020000123456", "holder_name": "王五"},
                   headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "holder_name_mismatch"


def test_get_payout_account_masked(client, requester):
    assert client.get("/api/v1/wallet/payout-account",
                      headers=auth(requester)).json()["bound"] is False
    bind_payout(client, requester)
    got = client.get("/api/v1/wallet/payout-account", headers=auth(requester)).json()
    assert got["bound"] is True and got["account_no"] == "6222****3456"  # 脱敏
    assert got["holder_name"] == "张三"


def test_bind_requires_verification(client):
    user = register(client, "28000000001", "未实名")  # 不实名
    r = client.put("/api/v1/wallet/payout-account",
                   json={"kind": "alipay", "account_no": "user@example.com", "holder_name": "某人"},
                   headers=auth(user))
    assert r.status_code == 403  # require_verified


def test_rebind_overwrites(client, requester):
    bind_payout(client, requester)
    r = client.put("/api/v1/wallet/payout-account",
                   json={"kind": "alipay", "account_no": "13800000001@alipay", "holder_name": "张三"},
                   headers=auth(requester))
    assert r.status_code == 200 and r.json()["kind"] == "alipay"
    got = client.get("/api/v1/wallet/payout-account", headers=auth(requester)).json()
    assert got["kind"] == "alipay"
