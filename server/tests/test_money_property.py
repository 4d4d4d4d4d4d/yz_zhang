"""资金守恒属性测试：随机化生命周期序列后，对账三不变量必须始终成立。

用随机 seed 驱动多条任务走不同结局（验收/取消/纠纷仲裁/申诉），
每步后调用 reconcile() 断言全局守恒 + 托管有据 + 冻结有据，逼出资源泄漏。
"""
import random

import sqlalchemy as sa

from app.core.db import engine
from app.modules.risk.service import reconcile

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _make_admin(client, phone):
    admin = register(client, phone, "仲裁")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def _assert_conserved(client):
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def test_money_conservation_under_random_lifecycles(client):
    rng = random.Random(20260704)
    admin = _make_admin(client, "14000000000")
    boss = register(client, "14000000001", "发布者")
    verify_user(client, boss)
    workers = []
    for i in range(3):
        w = register(client, f"1400001000{i}", f"执行者{i}")
        verify_user(client, w, f"执行{i}")
        topup(client, w, 50000)  # 备用于保证金
        workers.append(w)
    topup(client, boss, 5_000_000)

    outcomes = ["accept", "cancel_by_boss", "cancel_by_worker",
                "verdict", "appeal", "milestone"]

    for n in range(20):
        outcome = rng.choice(outcomes)
        deposit = rng.choice([0, 0, 3000])  # 三分之一带保证金
        budget = rng.choice([10000, 20000, 40000])
        worker = rng.choice(workers)

        task = publish_task(client, boss, title=f"随机单{n}", budget_cents=budget,
                            deposit_cents=deposit)

        if outcome == "milestone":
            # 走多里程碑分期路径
            app_id = client.post(f"/api/v1/tasks/{task['id']}/applications",
                                 json={}, headers=auth(worker)).json()["id"]
            cid = client.post(f"/api/v1/applications/{app_id}/accept",
                              headers=auth(boss)).json()["contract_id"]
            client.post(f"/api/v1/contracts/{cid}/milestones", json={"items": [
                {"title": "首期", "amount_cents": budget // 2},
                {"title": "尾期", "amount_cents": budget - budget // 2},
            ]}, headers=auth(boss))
            for h in (boss, worker):
                client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(h))
            client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(boss))
            _assert_conserved(client)
            for idx in (1, 2):
                client.post(f"/api/v1/contracts/{cid}/milestones/{idx}/deliver", headers=auth(worker))
                client.post(f"/api/v1/contracts/{cid}/milestones/{idx}/accept", headers=auth(boss))
                _assert_conserved(client)
            continue

        cid = match_and_fund(client, boss, worker, task)
        _assert_conserved(client)

        if outcome == "accept":
            client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
            client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(boss))
        elif outcome == "cancel_by_boss":
            client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(boss))
        elif outcome == "cancel_by_worker":
            client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(worker))
        elif outcome in ("verdict", "appeal"):
            d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                            json={"reason": "交付质量有争议，需要仲裁"}, headers=auth(boss)).json()
            share = rng.choice([0, 3000, 5000, 10000])
            client.post(f"/api/v1/disputes/{d['id']}/verdict",
                        json={"executor_share_bps": share, "reason": "规则裁决"},
                        headers=auth(admin))
            _assert_conserved(client)
            if outcome == "appeal":
                client.post(f"/api/v1/disputes/{d['id']}/appeal", headers=auth(worker))
                new_share = rng.choice([0, 4000, 8000, 10000])
                client.post(f"/api/v1/disputes/{d['id']}/appeal-verdict",
                            json={"executor_share_bps": new_share, "reason": "复核终局"},
                            headers=auth(admin))
        _assert_conserved(client)

    # 终局：全平台账实一致
    _assert_conserved(client)
