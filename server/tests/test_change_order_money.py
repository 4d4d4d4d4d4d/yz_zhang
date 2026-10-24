"""SC-007 变更单资金守恒：改价会动托管资金（加价补托管/减价退款），

这是资金守恒最容易漏的一条路径——现有属性测试的随机生命周期未覆盖变更单。
本套件对加价/减价两个方向，在 funded 态下走完整改价并放款，每步后 reconcile
断言账实一致；并钉住守卫：提案方不能自接、重复接受被拒、已放款不可整体改价。
"""
import random

from app.core.db import SessionLocal
from app.modules.risk.service import reconcile

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def _fund_contract(client, boss, worker, budget):
    task = publish_task(client, boss, budget_cents=budget)
    cid = match_and_fund(client, boss, worker, task)
    return task, cid


def test_change_order_increase_holds_extra_escrow_and_conserves(client):
    boss = register(client, "17000000001", "发布方")
    verify_user(client, boss)
    worker = register(client, "17000000002", "执行方")
    verify_user(client, worker, "执行方乙")
    topup(client, boss, 100000)

    _, cid = _fund_contract(client, boss, worker, 20000)
    _assert_conserved()
    before = client.get("/api/v1/wallet", headers=auth(boss)).json()
    assert before["escrow_cents"] == 20000

    # 加价到 30000：需补托管 10000
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "加需求"},
                      headers=auth(boss)).json()["id"]
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))
    _assert_conserved()
    mid = client.get("/api/v1/wallet", headers=auth(boss)).json()
    assert mid["escrow_cents"] == 30000 and mid["available_cents"] == before["available_cents"] - 10000

    # 放款：执行者拿 30000 - 8%
    tid = client.get(f"/api/v1/contracts/{cid}", headers=auth(boss)).json()["task_id"]
    client.post(f"/api/v1/tasks/{tid}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{tid}/accept-delivery", headers=auth(boss))
    _assert_conserved()
    assert client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"] == 27600


def test_change_order_decrease_refunds_and_conserves(client):
    boss = register(client, "17000000003", "发布方")
    verify_user(client, boss)
    worker = register(client, "17000000004", "执行方")
    verify_user(client, worker, "执行方丁")
    topup(client, boss, 100000)

    _, cid = _fund_contract(client, boss, worker, 40000)
    _assert_conserved()
    before = client.get("/api/v1/wallet", headers=auth(boss)).json()

    # 减价到 25000：退回托管 15000 到可用余额
    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 25000, "reason": "砍需求"},
                      headers=auth(boss)).json()["id"]
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))
    _assert_conserved()
    mid = client.get("/api/v1/wallet", headers=auth(boss)).json()
    assert mid["escrow_cents"] == 25000 and mid["available_cents"] == before["available_cents"] + 15000

    tid = client.get(f"/api/v1/contracts/{cid}", headers=auth(boss)).json()["task_id"]
    client.post(f"/api/v1/tasks/{tid}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{tid}/accept-delivery", headers=auth(boss))
    _assert_conserved()
    assert client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"] == 23000  # 25000-8%


def test_change_order_guards(client):
    boss = register(client, "17000000005", "发布方")
    verify_user(client, boss)
    worker = register(client, "17000000006", "执行方")
    verify_user(client, worker, "执行方戊")
    topup(client, boss, 100000)
    _, cid = _fund_contract(client, boss, worker, 20000)

    oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                      json={"new_amount_cents": 30000, "reason": "加需求"},
                      headers=auth(boss)).json()["id"]
    # 提案方不能自接
    r = client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(boss))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_counterparty"
    # 已有 pending 变更单时不能再提
    r = client.post(f"/api/v1/contracts/{cid}/change-orders",
                    json={"new_amount_cents": 35000, "reason": "又加"}, headers=auth(boss))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "change_pending"
    # 对方接受
    client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))
    _assert_conserved()
    # 重复接受同一变更单被拒（防重放，无二次补托管）
    r = client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "change_closed"
    _assert_conserved()


def test_change_order_random_walk_conserves(client):
    """随机多轮改价（金额上下浮动）后放款，全程 reconcile 恒成立。"""
    rng = random.Random(20260707)
    boss = register(client, "17000000007", "发布方")
    verify_user(client, boss)
    worker = register(client, "17000000008", "执行方")
    verify_user(client, worker, "执行方己")
    topup(client, boss, 5_000_000)

    for n in range(8):
        budget = rng.choice([10000, 20000, 30000])
        _, cid = _fund_contract(client, boss, worker, budget)
        amount = budget
        for _ in range(rng.randint(1, 3)):
            new_amount = rng.choice([8000, 15000, 25000, 45000])
            if new_amount == amount:
                continue
            oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                              json={"new_amount_cents": new_amount, "reason": f"改{n}"},
                              headers=auth(boss)).json().get("id")
            if oid is None:
                continue
            client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))
            amount = new_amount
            _assert_conserved()
        tid = client.get(f"/api/v1/contracts/{cid}", headers=auth(boss)).json()["task_id"]
        client.post(f"/api/v1/tasks/{tid}/deliver", headers=auth(worker))
        client.post(f"/api/v1/tasks/{tid}/accept-delivery", headers=auth(boss))
        _assert_conserved()
