"""14.6/05.B 幂等键请求指纹（参照 Stripe）：同 key 不同请求必须拒绝，不能串味/吞单。

两个真实缺陷：
1. 同 key 复用但金额不同 → 原实现返回旧结果，客户端误以为新金额成功（吞单）；
2. 同 key 跨不同操作（topup vs withdraw）→ 原实现只按 (user,key) 命中，
   会把 topup 的缓存响应返回给 withdraw（串味）。
修复后两者都以 idempotency_key_conflict(409) 拒绝。
"""
from .conftest import auth, bind_payout, register, topup, verify_user


def test_same_key_different_amount_rejected(client, requester):
    key = "ik-amount"
    r1 = client.post("/api/v1/wallet/topup", json={"amount_cents": 10000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r1.status_code == 200
    # 同 key、不同金额 → 冲突拒绝（而非返回旧的 10000 结果）
    r2 = client.post("/api/v1/wallet/topup", json={"amount_cents": 50000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "idempotency_key_conflict"
    # 只入账一次首金额
    assert client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"] == 10000


def test_same_key_same_amount_still_replays(client, requester):
    key = "ik-replay"
    r1 = client.post("/api/v1/wallet/topup", json={"amount_cents": 3000},
                     headers={**auth(requester), "Idempotency-Key": key})
    r2 = client.post("/api/v1/wallet/topup", json={"amount_cents": 3000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r1.json() == r2.json()  # 完全相同 → 正常重放
    assert client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"] == 3000


def test_same_key_cross_operation_rejected(client, requester):
    bind_payout(client, requester)
    topup(client, requester, 20000)
    key = "ik-cross"
    # 先用于提现
    r1 = client.post("/api/v1/wallet/withdraw", json={"amount_cents": 5000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r1.status_code == 200
    # 同 key 复用于充值（不同 scope）→ 冲突拒绝，绝不能把提现结果当充值返回
    r2 = client.post("/api/v1/wallet/topup", json={"amount_cents": 5000},
                     headers={**auth(requester), "Idempotency-Key": key})
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "idempotency_key_conflict"


def test_key_scoped_per_user_unaffected(client, requester, worker):
    # 不同用户用同一 key、同一参数互不干扰（既有语义保持）
    client.post("/api/v1/wallet/topup", json={"amount_cents": 3000},
                headers={**auth(requester), "Idempotency-Key": "shared"})
    client.post("/api/v1/wallet/topup", json={"amount_cents": 3000},
                headers={**auth(worker), "Idempotency-Key": "shared"})
    assert client.get("/api/v1/wallet", headers=auth(requester)).json()["available_cents"] == 3000
    assert client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"] == 3000
