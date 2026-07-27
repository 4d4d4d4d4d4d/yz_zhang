"""SC-012 签署有效期：成交后超期未双签自动作废（业界 offer 有效期惯例）。

防的是真实资金卡死：成交即冻结执行者保证金，若一方失联不签字，
合约永挂 pending_signatures、保证金无限期冻结、任务卡 matched。
job 作废后：合约取消、保证金原路退还、任务关闭、双方收通知，全程守恒。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.modules.account.models import utcnow
from app.modules.risk.service import reconcile

from .conftest import JOB_HEADERS, auth, register, topup, verify_user
from .test_task_flow import publish_task


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def _backdate_contract(cid: int, days: float) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE contracts SET created_at = :d WHERE id = :c"),
                     {"d": utcnow() - timedelta(days=days), "c": cid})


def _match(client, boss, worker, deposit=0):
    task = publish_task(client, boss, budget_cents=20000, deposit_cents=deposit)
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={},
                         headers=auth(worker)).json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(boss)).json()["contract_id"]
    return task, cid


def test_expired_unsigned_contract_released_with_deposit(client, requester, worker):
    topup(client, requester, 50000)
    topup(client, worker, 10000)
    task, cid = _match(client, requester, worker, deposit=3000)
    w = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert w["frozen_cents"] == 3000  # 成交即冻结保证金

    _backdate_contract(cid, settings.SIGN_EXPIRE_DAYS + 0.1)
    r = client.post("/api/v1/contracts/jobs/expire-unsigned", headers=JOB_HEADERS)
    assert r.json()["expired"] == 1
    _assert_conserved()

    # 保证金解冻回可用；合约取消；任务关闭
    w = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert w["frozen_cents"] == 0 and w["available_cents"] == 10000
    c = client.get(f"/api/v1/contracts/{cid}", headers=auth(requester)).json()
    assert c["status"] == "cancelled" and c["deposit_status"] == "returned"
    t = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert t["status"] == "cancelled"
    # 双方收到作废通知
    for u in (requester, worker):
        notices = client.get("/api/v1/notifications", headers=auth(u)).json()
        assert any("签署超期作废" in n["title"] for n in notices)


def test_half_signed_also_expires_but_fresh_and_funded_untouched(client, requester, worker):
    topup(client, requester, 100000)

    # 半签超期 → 作废
    _, cid_half = _match(client, requester, worker)
    client.post(f"/api/v1/contracts/{cid_half}/sign", headers=auth(requester))
    _backdate_contract(cid_half, settings.SIGN_EXPIRE_DAYS + 1)

    # 新鲜未签 → 不动
    _, cid_fresh = _match(client, requester, worker)

    # 已双签托管但 created_at 久远 → 不动（只回收 pending_signatures）
    _, cid_funded = _match(client, requester, worker)
    for u in (requester, worker):
        client.post(f"/api/v1/contracts/{cid_funded}/sign", headers=auth(u))
    client.post(f"/api/v1/contracts/{cid_funded}/fund", headers=auth(requester))
    _backdate_contract(cid_funded, settings.SIGN_EXPIRE_DAYS + 5)

    r = client.post("/api/v1/contracts/jobs/expire-unsigned", headers=JOB_HEADERS)
    assert r.json()["expired"] == 1  # 只作废半签超期那单
    _assert_conserved()

    assert client.get(f"/api/v1/contracts/{cid_half}",
                      headers=auth(requester)).json()["status"] == "cancelled"
    assert client.get(f"/api/v1/contracts/{cid_fresh}",
                      headers=auth(requester)).json()["status"] == "pending_signatures"
    assert client.get(f"/api/v1/contracts/{cid_funded}",
                      headers=auth(requester)).json()["status"] == "funded"
    # 托管资金分毫未动
    assert client.get("/api/v1/wallet", headers=auth(requester)).json()["escrow_cents"] == 20000

    # 重跑幂等：无新超期单
    assert client.post("/api/v1/contracts/jobs/expire-unsigned", headers=JOB_HEADERS).json()["expired"] == 0
    _assert_conserved()
