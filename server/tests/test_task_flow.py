"""03/05/07 任务闭环：发布→报名→推荐→成交→合约→托管→执行→验收→放款→评价"""
from .conftest import JOB_HEADERS, auth, register, topup, verify_user

CLEAN_TASK = {
    "title": "周末大扫除",
    "description": "两室一厅深度保洁",
    "category": "保洁",
    "task_type": "service",
    "required_skills": ["保洁"],
    "budget_cents": 20000,
    "city": "上海",
    "lat": 31.2304,
    "lng": 121.4737,
    "address_hint": "静安寺商圈",
    "address_exact": "静安区南京西路 1234 号 5 栋 302",
}


def publish_task(client, user, **overrides):
    payload = {**CLEAN_TASK, **overrides}
    r = client.post("/api/v1/tasks", json=payload, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def match_and_fund(client, requester, worker, task, bid=None):
    """报名 → 接受 → 双签 → 托管，返回 contract_id。"""
    body = {"message": "有经验"}
    if bid:
        body["bid_cents"] = bid
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json=body, headers=auth(worker))
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    r = client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    assert r.status_code == 200, r.text
    contract_id = r.json()["contract_id"]
    for u in (requester, worker):
        assert client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(u)).status_code == 200
    r = client.post(f"/api/v1/contracts/{contract_id}/fund", headers=auth(requester))
    assert r.status_code == 200, r.text
    return contract_id


def test_task001_publish_and_machine_review(client, requester):
    task = publish_task(client, requester)
    assert task["status"] == "published"
    # TASK-004 违禁词机审拒绝
    r = client.post(
        "/api/v1/tasks", json={**CLEAN_TASK, "title": "帮忙刷单"}, headers=auth(requester)
    )
    assert r.status_code == 400
    # 线下任务必须有位置
    r = client.post(
        "/api/v1/tasks", json={**CLEAN_TASK, "lat": None, "lng": None}, headers=auth(requester)
    )
    assert r.status_code == 400


def test_match001_apply_requires_verification(client, requester):
    task = publish_task(client, requester)
    stranger = register(client, "13600000001")
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(stranger))
    assert r.status_code == 403  # 未实名不能接单


def test_match002_recommendations_ranked_with_reasons(client, requester, worker):
    # worker 有匹配技能且同城
    client.patch(
        "/api/v1/users/me",
        json={"skills": ["保洁"], "lat": 31.23, "lng": 121.47, "city": "上海"},
        headers=auth(worker),
    )
    far_user = register(client, "13600000002", "远方无技能")
    verify_user(client, far_user, "王五")
    client.patch(
        "/api/v1/users/me", json={"skills": ["编程"], "lat": 39.9, "lng": 116.4}, headers=auth(far_user)
    )
    task = publish_task(client, requester)
    recs = client.get(f"/api/v1/tasks/{task['id']}/recommendations", headers=auth(requester)).json()
    assert recs[0]["user_id"] == worker["id"]
    assert recs[0]["score"] > recs[-1]["score"]
    assert any("技能" in reason for reason in recs[0]["reasons"])  # 可解释


def test_geo010_nearby_filter_and_desensitized_address(client, requester, worker):
    publish_task(client, requester, title="市区保洁")
    publish_task(client, requester, title="远郊保洁", lat=30.0, lng=120.0, address_hint="远郊")
    r = client.get("/api/v1/tasks", params={"lat": 31.23, "lng": 121.47, "max_km": 10})
    titles = [t["title"] for t in r.json()]
    assert "市区保洁" in titles and "远郊保洁" not in titles
    # GEO-004 广场上的任务不暴露精确地址
    assert all(t["address_exact"] == "" for t in r.json())


def test_full_closed_loop_with_escrow_and_fee(client, requester, worker):
    """核心闭环：托管 2 万分 → 验收 → 执行者收到 92%（8% 抽佣）。"""
    topup(client, requester, 50000)
    task = publish_task(client, requester)
    contract_id = match_and_fund(client, requester, worker, task)

    # 托管后余额
    w = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert w["available_cents"] == 30000 and w["escrow_cents"] == 20000

    # 成交后执行者可见精确地址（GEO-004）
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert detail["status"] == "in_progress" and "南京西路" in detail["address_exact"]

    # GEO-020 到场打卡：太远被拒，就近通过
    r = client.post(
        f"/api/v1/tasks/{task['id']}/checkin", json={"lat": 30.0, "lng": 120.0}, headers=auth(worker)
    )
    assert r.status_code == 400
    r = client.post(
        f"/api/v1/tasks/{task['id']}/checkin",
        json={"lat": 31.2305, "lng": 121.4738},
        headers=auth(worker),
    )
    assert r.status_code == 201

    # 进度 → 交付 → 验收
    client.post(f"/api/v1/tasks/{task['id']}/progress", json={"content": "已完成客厅"}, headers=auth(worker))
    assert client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker)).status_code == 200
    r = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert r.status_code == 200 and r.json()["status"] == "completed"

    # SC-005/SC-009 放款与抽佣
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["available_cents"] == 18400  # 20000 - 8%
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["escrow_cents"] == 0

    # 双向评价 + 盲评（CRED-002）
    client.post(f"/api/v1/tasks/{task['id']}/reviews", json={"stars": 5}, headers=auth(requester))
    visible = client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(worker)).json()
    assert visible == []  # 对方已评但自己未评 → 不可见
    client.post(f"/api/v1/tasks/{task['id']}/reviews", json={"stars": 4}, headers=auth(worker))
    visible = client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(worker)).json()
    assert len(visible) == 2

    # 信用分更新（CRED-001/002）
    prof = client.get(f"/api/v1/users/{worker['id']}").json()
    assert prof["credit_score"] > 100 and prof["tasks_completed"] == 1


def test_task026_cancel_rules(client, requester, worker):
    """SC-006 托管后发布者取消 → 执行者获 20% 补偿。"""
    topup(client, requester, 20000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    r = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=auth(requester))
    assert r.status_code == 200
    assert r.json()["executor_compensation_cents"] == 4000
    ww = client.get("/api/v1/wallet", headers=auth(worker)).json()
    assert ww["available_cents"] == 4000 - 4000 * 800 // 10000  # 补偿部分同样抽佣
    wr = client.get("/api/v1/wallet", headers=auth(requester)).json()
    assert wr["available_cents"] == 16000 and wr["escrow_cents"] == 0


def test_task031_auto_accept_after_timeout(client, requester, worker):
    import sqlalchemy as sa

    from app.core.db import engine

    topup(client, requester, 20000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    # 时间旅行：把交付时间改到 4 天前
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE tasks SET delivered_at = datetime('now', '-4 days') WHERE id = :id"),
            {"id": task["id"]},
        )
    r = client.post("/api/v1/tasks/jobs/auto-accept", headers=JOB_HEADERS)
    assert r.json()["auto_accepted"] == 1
    detail = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert detail["status"] == "completed"


def test_state_machine_rejects_illegal_transition(client, requester, worker):
    task = publish_task(client, requester)
    # 未成交直接交付非法
    r = client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    assert r.status_code == 403  # 非执行者
    # 未托管时任务是 matched，不能验收
    topup(client, requester, 20000)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    app_id = r.json()["id"]
    client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    r = client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    assert r.status_code == 409  # matched → pending_acceptance 非法


def test_fund_requires_balance(client, requester, worker):
    task = publish_task(client, requester)
    r = client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    app_id = r.json()["id"]
    contract_id = client.post(
        f"/api/v1/applications/{app_id}/accept", headers=auth(requester)
    ).json()["contract_id"]
    for u in (requester, worker):
        client.post(f"/api/v1/contracts/{contract_id}/sign", headers=auth(u))
    r = client.post(f"/api/v1/contracts/{contract_id}/fund", headers=auth(requester))
    assert r.status_code == 400  # 余额不足（SC-003）
