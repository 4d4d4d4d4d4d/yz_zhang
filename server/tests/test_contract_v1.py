"""05 合约增强：SC-004 多里程碑分期 / SC-007 变更单"""
from .conftest import auth, topup
from .test_task_flow import publish_task


def _matched_contract(client, requester, worker, budget=100000):
    """报名成交但未签署，返回 contract_id 与 task。"""
    topup(client, requester, budget * 2)
    task = publish_task(client, requester, budget_cents=budget, title="装修项目", category="维修")
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    app_id = r.json()["id"]
    contract_id = client.post(
        f"/api/v1/applications/{app_id}/accept", headers=auth(requester)
    ).json()["contract_id"]
    return contract_id, task


def _sign_and_fund(client, requester, worker, contract_id):
    for u in (requester, worker):
        assert client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(u)).status_code == 200
    assert client.post(f"/api/v1/contracts/{contract_id}/fund", headers=auth(requester)).status_code == 200


def test_sc004_default_single_milestone(client, requester, worker):
    contract_id, _ = _matched_contract(client, requester, worker)
    c = client.get(f"/api/v1/contracts/{contract_id}", headers=auth(requester)).json()
    assert len(c["milestones"]) == 1 and c["milestones"][0]["amount_cents"] == 100000


def test_sc004_define_milestones_conservation(client, requester, worker):
    contract_id, _ = _matched_contract(client, requester, worker)
    # 金额不守恒被拒
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 1}]},
        headers=auth(requester),
    )
    assert r.status_code == 400
    # 执行者不能定义
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "全部", "amount_cents": 100000}]},
        headers=auth(worker),
    )
    assert r.status_code == 400
    # 三期守恒成功
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [
            {"title": "拆旧", "amount_cents": 20000},
            {"title": "硬装", "amount_cents": 50000},
            {"title": "收尾", "amount_cents": 30000},
        ]},
        headers=auth(requester),
    )
    assert r.status_code == 200 and len(r.json()["milestones"]) == 3


def test_sc004_staged_delivery_and_release(client, requester, worker):
    contract_id, task = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000}, {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    # 签署后不能重定义里程碑
    r = client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "x", "amount_cents": 100000}]},
        headers=auth(requester),
    )
    assert r.status_code == 409
    # 未交付不能放款
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    assert r.status_code == 409
    # 首期交付 → 放款：执行者收到 40000-8%
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    assert r.status_code == 200
    assert r.json()["released_cents"] == 40000 and r.json()["status"] == "funded"
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["available_cents"] == 40000 - 40000 * 800 // 10000
    # 尾期交付+放款 → 合约 released、任务自动闭环
    client.post(f"/api/v1/contracts/{contract_id}/milestones/2/deliver", headers=auth(worker))
    r = client.post(f"/api/v1/contracts/{contract_id}/milestones/2/accept", headers=auth(requester))
    assert r.json()["status"] == "released"
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert detail["status"] == "completed"
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0


def test_sc004_partial_release_then_cancel_uses_remaining(client, requester, worker):
    """部分放款后取消：规则只作用于剩余托管额。"""
    contract_id, task = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000}, {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    # 发布者取消：补偿 = 剩余 60000 的 20%
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(requester))
    assert r.json()["executor_compensation_cents"] == 12000
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0
    assert wr["available_cents"] == 200000 - 40000 - 12000  # 充值-首期-补偿


def test_sc007_change_order_increase_and_decrease(client, requester, worker):
    contract_id, task = _matched_contract(client, requester, worker)
    _sign_and_fund(client, requester, worker, contract_id)
    # 执行者提出加价到 120000
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 120000, "reason": "增加阳台施工"},
        headers=auth(worker),
    )
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]
    # 提案方不能自己接受
    r = client.post(f"/api/v1/contracts/{contract_id}/change-orders/{order_id}/accept", headers=auth(worker))
    assert r.status_code == 400
    # 有 pending 变更单时不能再提
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 90000}, headers=auth(requester),
    )
    assert r.status_code == 409
    # 发布者接受 → 追加托管 20000、版本+1、任务预算同步
    r = client.post(f"/api/v1/contracts/{contract_id}/change-orders/{order_id}/accept", headers=auth(requester))
    c = r.json()
    assert c["amount_cents"] == 120000 and c["version"] == 2
    assert c["milestones"][0]["amount_cents"] == 120000
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 120000
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert detail["budget_cents"] == 120000
    # 再来一次减价到 110000 → 退差额
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 110000, "reason": "取消部分项目"},
        headers=auth(requester),
    )
    order2 = r.json()["id"]
    client.post(f"/api/v1/contracts/{contract_id}/change-orders/{order2}/accept", headers=auth(worker))
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 110000


def test_sc007_change_rejected_after_release_started(client, requester, worker):
    contract_id, _ = _matched_contract(client, requester, worker)
    client.post(
        f"/api/v1/contracts/{contract_id}/milestones",
        json={"items": [{"title": "首期", "amount_cents": 40000}, {"title": "尾期", "amount_cents": 60000}]},
        headers=auth(requester),
    )
    _sign_and_fund(client, requester, worker, contract_id)
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/deliver", headers=auth(worker))
    client.post(f"/api/v1/contracts/{contract_id}/milestones/1/accept", headers=auth(requester))
    r = client.post(
        f"/api/v1/contracts/{contract_id}/change-orders",
        json={"new_amount_cents": 200000}, headers=auth(worker),
    )
    assert r.status_code == 409  # 已开始放款不可整体改价
