"""并发/重复提交防重放硬化（14.6 资金安全）：关键资金与状态操作的双提交守卫。

网络重试或用户双击可能把同一操作提交两次，最坏会造成重复放款/重复托管/一任务两合约。
本套件对每个关键操作验证：第二次提交被正确拒绝，且无任何重复副作用（放款/托管/记账）。
守卫依赖两层：状态机白名单 + get_db 异常整体回滚（拒绝即零副作用）。
"""
import sqlalchemy as sa

from app.core.db import SessionLocal, engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _count_contracts(task_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(
            sa.select(sa.func.count()).select_from(sa.text("contracts")).where(sa.text("task_id = :t")),
            {"t": task_id},
        )


def _contract_id(task_id: int) -> int:
    with engine.begin() as conn:
        return conn.execute(
            sa.text("SELECT id FROM contracts WHERE task_id = :t"), {"t": task_id}
        ).scalar()


# ---------- (1) 重复接受报名：一任务一合约，不产生第二份合约 ----------
def test_double_accept_application_no_second_contract(client, requester, worker):
    topup(client, requester, 50000)
    task = publish_task(client, requester)
    other = register(client, "16000000001", "另一报名者")
    verify_user(client, other, "候选乙")

    a1 = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker)).json()["id"]
    a2 = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(other)).json()["id"]

    r1 = client.post(f"/api/v1/applications/{a1}/accept", headers=auth(requester))
    assert r1.status_code == 200
    # 重复接受同一报名 → 任务已 matched，拒绝
    r_same = client.post(f"/api/v1/applications/{a1}/accept", headers=auth(requester))
    assert r_same.status_code == 409 and r_same.json()["detail"]["code"] == "not_recruiting"
    # 接受第二个报名 → 同样拒绝（不能一任务两合约）
    r2 = client.post(f"/api/v1/applications/{a2}/accept", headers=auth(requester))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "not_recruiting"

    assert _count_contracts(task["id"]) == 1  # 全程只有一份合约


# ---------- (2) 重复报名：唯一去重守卫 ----------
def test_double_apply_rejected(client, requester, worker):
    task = publish_task(client, requester)
    r1 = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r1.status_code == 201
    r2 = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "already_applied"
    # 只有一条报名
    apps = client.get(f"/api/v1/tasks/{task['id']}/applications", headers=auth(requester)).json()
    assert len(apps) == 1


# ---------- (3) 重复托管：托管资金只扣一次 ----------
def test_double_fund_holds_escrow_once(client, requester, worker):
    topup(client, requester, 50000)
    task = publish_task(client, requester)
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker)).json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester)).json()["contract_id"]
    for u in (requester, worker):
        client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u))

    r1 = client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    assert r1.status_code == 200
    # 第二次托管 → 合约已非 signed 态，拒绝
    r2 = client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "not_fundable"

    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["escrow_cents"] == 20000 and w["available_cents"] == 30000  # 只托管一次


# ---------- (4) 重复交付：状态机拒绝二次流转 ----------
def test_double_deliver_rejected_by_state_machine(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)

    r1 = client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    assert r1.status_code == 200
    # 已 pending_acceptance，再次交付非法流转
    r2 = client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "invalid_transition"


# ---------- (5) 重复验收放款：不重复放款 ----------
def test_double_accept_delivery_no_double_release(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))

    r1 = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r1.status_code == 200 and r1.json()["status"] == "completed"
    balance_after_first = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert balance_after_first == 18400  # 20000 - 8%

    # 第二次验收：release 已非 funded 态 → 拒绝，且整体回滚不放款
    r2 = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "not_releasable"

    balance_after_second = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert balance_after_second == balance_after_first  # 无二次放款
    # 发布者托管清零且未被二次扣款
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0


# ---------- (6) 重复里程碑验收：分期放款不重复 ----------
def test_double_milestone_accept_no_double_release(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester, budget_cents=40000)
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker)).json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/milestones", json={"items": [
        {"title": "首期", "amount_cents": 20000},
        {"title": "尾期", "amount_cents": 20000},
    ]}, headers=auth(requester))
    for u in (requester, worker):
        client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(requester))

    client.post(f"/api/v1/contracts/{cid}/milestones/1/deliver", headers=auth(worker))
    r1 = client.post(f"/api/v1/contracts/{cid}/milestones/1/accept", headers=auth(requester))
    assert r1.status_code == 200
    bal = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert bal == 18400  # 首期 20000 - 8%

    # 重复验收首期 → 里程碑已 released，拒绝
    r2 = client.post(f"/api/v1/contracts/{cid}/milestones/1/accept", headers=auth(requester))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "invalid_milestone_state"
    assert client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"] == bal


# ---------- (7) 一任务一合约：DB 唯一约束是最后一道防线 ----------
def test_one_task_one_contract_db_uniqueness(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    cid = _contract_id(task["id"])
    # 直接尝试插入第二份同 task_id 合约 → DB 唯一约束拒绝
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO contracts (task_id, requester_id, executor_id, amount_cents, "
                    "fee_bps, status, terms) VALUES (:t, :r, :e, 1, 800, 'pending_signatures', 'x')"
                ),
                {"t": task["id"], "r": requester["id"], "e": worker["id"]},
            )
    assert _count_contracts(task["id"]) == 1 and cid  # 仍只有原始一份
