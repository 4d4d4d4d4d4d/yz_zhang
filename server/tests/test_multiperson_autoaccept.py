"""TASK-007 多人任务预算守恒 + TASK-031 自动验收边界与资金守恒。

两条真实未钉住的路径：
1. 名额拆分的整除余数——Σ名额预算必须等于母任务预算（与 AI 分解同一守恒原则），
   否则每单静默蒸发若干分钱；
2. 超时自动验收 job 的时间边界（恰好到期/未到期）及其放款的守恒性——
   这是唯一一条「无人点击也会动钱」的路径。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.modules.account.models import utcnow
from app.modules.risk.service import reconcile

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


# ---------- TASK-007 名额预算守恒 ----------
def test_multiperson_slot_budgets_sum_to_parent(client, requester):
    """不可整除预算（10000/3）：余数并入末位名额，Σ名额 == 母任务预算。"""
    r = client.post("/api/v1/tasks", json={
        "title": "传单派发三人组", "description": "商圈派发宣传单页半天",
        "category": "跑腿", "budget_cents": 10000, "is_remote": True,
        "people_needed": 3, "publish_now": True,
    }, headers=auth(requester))
    assert r.status_code == 200 or r.status_code == 201
    slots = r.json()["slots"]
    budgets = [s["budget_cents"] for s in slots]
    assert budgets == [3333, 3333, 3334]
    assert sum(budgets) == 10000  # 一分不丢


def test_multiperson_full_cycle_conserves_money(client, requester):
    """两个名额分别成交放款，总放款/抽佣与母任务预算精确对应。"""
    topup(client, requester, 50000)
    r = client.post("/api/v1/tasks", json={
        "title": "会场布置双人组", "description": "活动会场桌椅布置与撤场",
        "category": "跑腿", "budget_cents": 10001, "is_remote": True,
        "people_needed": 2, "publish_now": True,
    }, headers=auth(requester))
    slots = r.json()["slots"]
    assert [s["budget_cents"] for s in slots] == [5000, 5001]

    total_paid = 0
    for i, slot in enumerate(slots):
        w = register(client, f"1900000010{i}", f"帮手{i}")
        verify_user(client, w, f"帮手{i}号")
        match_and_fund(client, requester, w, slot)
        client.post(f"/api/v1/tasks/{slot['id']}/deliver", headers=auth(w))
        client.post(f"/api/v1/tasks/{slot['id']}/accept-delivery", headers=auth(requester))
        _assert_conserved()
        got = client.get("/api/v1/wallet", headers=auth(w)).json()["available_cents"]
        assert got == slot["budget_cents"] - slot["budget_cents"] * 800 // 10000
        total_paid += slot["budget_cents"]
    assert total_paid == 10001  # 全额进入托管并放出，无蒸发


# ---------- TASK-031 自动验收边界 ----------
def _set_delivered_at(task_id: int, dt) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET delivered_at = :d WHERE id = :t"),
                     {"d": dt, "t": task_id})


def test_auto_accept_boundary_and_conservation(client, requester, worker):
    """恰好到期的自动验收放款且守恒；未到期的一律不动。"""
    topup(client, requester, 60000)

    # 单 A：交付时间 = 恰好越过 cutoff 1 秒 → 应被自动验收
    task_due = publish_task(client, requester, title="到期单", budget_cents=20000)
    match_and_fund(client, requester, worker, task_due)
    client.post(f"/api/v1/tasks/{task_due['id']}/deliver", headers=auth(worker))
    _set_delivered_at(task_due["id"],
                      utcnow() - timedelta(days=settings.AUTO_ACCEPT_DAYS, seconds=1))

    # 单 B：还差 1 小时到期 → 不得被动
    task_fresh = publish_task(client, requester, title="未到期单", budget_cents=20000)
    match_and_fund(client, requester, worker, task_fresh)
    client.post(f"/api/v1/tasks/{task_fresh['id']}/deliver", headers=auth(worker))
    _set_delivered_at(task_fresh["id"],
                      utcnow() - timedelta(days=settings.AUTO_ACCEPT_DAYS) + timedelta(hours=1))

    before = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    r = client.post("/api/v1/tasks/jobs/auto-accept")
    assert r.json()["auto_accepted"] == 1  # 只动到期的那单
    _assert_conserved()

    after = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert after == before + 20000 - 1600  # 到期单放款 20000 - 8%
    assert client.get(f"/api/v1/tasks/{task_due['id']}",
                      headers=auth(requester)).json()["status"] == "completed"
    assert client.get(f"/api/v1/tasks/{task_fresh['id']}",
                      headers=auth(requester)).json()["status"] == "pending_acceptance"

    # job 重跑幂等：无新到期单则零动作，余额不变
    r = client.post("/api/v1/tasks/jobs/auto-accept")
    assert r.json()["auto_accepted"] == 0
    assert client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"] == after
    _assert_conserved()
