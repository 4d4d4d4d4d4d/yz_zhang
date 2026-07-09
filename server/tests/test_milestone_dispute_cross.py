"""SC-004×DSP-007 交叉路径：分期部分放款后进入纠纷，裁决只分割剩余托管。

这是资金侧最后一条未钉住的交叉边：首期已放款 → 纠纷冻结 → 仲裁分账。
必须保证：已放款部分不可追回/不重复计算，裁决基数=剩余托管（DSP-008 split_base），
冻结期间一切放款操作被拒，全程 reconcile 账实一致。
"""
from app.core.db import SessionLocal
from app.modules.risk.service import reconcile

import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth, register, topup, verify_user
from .test_task_flow import publish_task


def _assert_conserved():
    with SessionLocal() as db:
        r = reconcile(db)
    assert r["ok"], f"资金守恒被打破：{r['mismatches']}"


def _make_admin(client, phone):
    admin = register(client, phone, "仲裁员")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET is_admin = 1 WHERE id = :id"), {"id": admin["id"]})
    return admin


def _setup_partial_released(client, boss, worker, deposit=0):
    """两期合约（12000+8000），首期已放款。返回 (task, cid)。"""
    task = publish_task(client, boss, budget_cents=20000, deposit_cents=deposit)
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={},
                         headers=auth(worker)).json()["id"]
    cid = client.post(f"/api/v1/applications/{app_id}/accept",
                      headers=auth(boss)).json()["contract_id"]
    client.post(f"/api/v1/contracts/{cid}/milestones", json={"items": [
        {"title": "首期", "amount_cents": 12000},
        {"title": "尾期", "amount_cents": 8000},
    ]}, headers=auth(boss))
    for u in (boss, worker):
        client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(u))
    client.post(f"/api/v1/contracts/{cid}/fund", headers=auth(boss))
    client.post(f"/api/v1/contracts/{cid}/milestones/1/deliver", headers=auth(worker))
    client.post(f"/api/v1/contracts/{cid}/milestones/1/accept", headers=auth(boss))
    _assert_conserved()
    return task, cid


def test_verdict_after_partial_release_splits_only_remaining(client):
    admin = _make_admin(client, "18000000000")
    boss = register(client, "18000000001", "发布方")
    verify_user(client, boss)
    worker = register(client, "18000000002", "执行方")
    verify_user(client, worker, "执行方甲")
    topup(client, boss, 100000)

    task, cid = _setup_partial_released(client, boss, worker)
    w_after_m1 = client.get("/api/v1/wallet", headers=auth(worker)).json()["available_cents"]
    assert w_after_m1 == 11040  # 首期 12000 - 8%
    b_mid = client.get("/api/v1/wallet", headers=auth(boss)).json()
    assert b_mid["escrow_cents"] == 8000  # 只剩尾期托管

    # 纠纷 → 冻结 → 裁决 50%：只分割剩余 8000
    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "尾期交付质量有争议"}, headers=auth(boss)).json()
    r = client.post(f"/api/v1/disputes/{d['id']}/verdict",
                    json={"executor_share_bps": 5000, "reason": "各担一半"},
                    headers=auth(admin))
    assert r.status_code == 200
    # DSP-008 复核基数必须是剩余托管，而非合约总额
    assert r.json()["split_base_cents"] == 8000
    _assert_conserved()

    w = client.get("/api/v1/wallet", headers=auth(worker)).json()
    b = client.get("/api/v1/wallet", headers=auth(boss)).json()
    # 执行者：首期不动 + 剩余的一半 4000 - 8% 手续费
    assert w["available_cents"] == w_after_m1 + 4000 - 320
    # 发布者：退回另一半，托管清零
    assert b["available_cents"] == b_mid["available_cents"] + 4000
    assert b["escrow_cents"] == 0


def test_frozen_contract_blocks_milestone_ops(client):
    _make_admin(client, "18000000010")
    boss = register(client, "18000000011", "发布方")
    verify_user(client, boss)
    worker = register(client, "18000000012", "执行方")
    verify_user(client, worker, "执行方乙")
    topup(client, boss, 100000)

    task, cid = _setup_partial_released(client, boss, worker)
    client.post(f"/api/v1/contracts/{cid}/milestones/2/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/disputes",
                json={"reason": "尾期交付质量有争议"}, headers=auth(boss))

    # 冻结中：尾期验收放款必须被拒（否则绕过纠纷直接把钱放走）
    r = client.post(f"/api/v1/contracts/{cid}/milestones/2/accept", headers=auth(boss))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "contract_frozen"
    # 冻结中：整体取消也被拒
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(boss))
    assert r.status_code == 409
    _assert_conserved()
    # 钱一分没动
    assert client.get("/api/v1/wallet", headers=auth(boss)).json()["escrow_cents"] == 8000


def test_settlement_after_partial_release_conserves(client):
    """和解路径（非仲裁）同样只分剩余托管，且带保证金时正常退还。"""
    boss = register(client, "18000000021", "发布方")
    verify_user(client, boss)
    worker = register(client, "18000000022", "执行方")
    verify_user(client, worker, "执行方丙")
    topup(client, boss, 100000)
    topup(client, worker, 10000)  # 保证金来源

    task, cid = _setup_partial_released(client, boss, worker, deposit=3000)
    w_mid = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert w_mid["frozen_cents"] == 3000  # 保证金冻结中

    d = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "尾期范围理解有分歧"}, headers=auth(worker)).json()
    # 执行方提 25%，发布方接受
    client.post(f"/api/v1/disputes/{d['id']}/settlement",
                json={"executor_share_bps": 2500, "reason": "和解"}, headers=auth(worker))
    r = client.post(f"/api/v1/disputes/{d['id']}/settlement/accept", headers=auth(boss))
    assert r.status_code == 200 and r.json()["status"] == "settled"
    _assert_conserved()

    w = client.get("/api/v1/wallet", headers=auth(worker)).json()
    # 剩余 8000 的 25% = 2000 - 160 手续费；保证金 3000 解冻回可用
    assert w["frozen_cents"] == 0
    assert w["available_cents"] == w_mid["available_cents"] + 2000 - 160 + 3000
    b = client.get("/api/v1/wallet", headers=auth(boss)).json()
    assert b["escrow_cents"] == 0  # 托管清零，退回 6000
