"""SRCH-001 统一搜索 / TASK-006 周期任务 / LAW-002 文书 / ACC-031 数据导出"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


# ---------- 统一搜索 ----------
def test_srch001_grouped_results(client, requester, worker):
    publish_task(client, requester, title="周末深度保洁")
    client.post("/api/v1/contents", json={"body": "保洁小技巧分享"}, headers=auth(requester))
    client.post("/api/v1/circles", json={"name": "保洁联盟", "kind": "skill", "skill_tag": "保洁"},
                headers=auth(requester))
    client.patch("/api/v1/users/me", json={"nickname": "保洁阿姨王姐"}, headers=auth(worker))
    r = client.get("/api/v1/search", params={"q": "保洁"}, headers=auth(requester))
    body = r.json()
    assert body["tasks"][0]["title"] == "周末深度保洁"
    assert body["contents"][0]["body"].startswith("保洁小技巧")
    assert body["circles"][0]["name"] == "保洁联盟"
    assert any(u["nickname"] == "保洁阿姨王姐" for u in body["users"])
    # 圈层任务不出现在搜索（可见范围约束）
    c = body["circles"][0]
    client.post(
        "/api/v1/tasks",
        json={"title": "保洁圈内单", "category": "保洁", "budget_cents": 10000,
              "is_remote": True, "visibility": "circle", "circle_id": c["id"]},
        headers=auth(requester),
    )
    body = client.get("/api/v1/search", params={"q": "圈内单"}, headers=auth(requester)).json()
    assert body["tasks"] == []


# ---------- 周期任务 ----------
def test_task006_recurring_respawns_next_period(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester, title="每周开荒保洁", recurrence="weekly")
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    # 闭环后自动生成下一期（招募中、同预算、标记来源）
    tasks = client.get("/api/v1/tasks", params={"q": "每周开荒保洁"}).json()
    respawned = [t for t in tasks if t["status"] == "published"]
    assert len(respawned) == 1
    assert respawned[0]["recurred_from_id"] == task["id"]
    assert respawned[0]["budget_cents"] == task["budget_cents"]
    # 发布者收到续期通知
    notes = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("周期任务已续期" == n["title"] for n in notes)
    # 非法周期值被拒
    r = client.post(
        "/api/v1/tasks",
        json={"title": "错误周期", "category": "保洁", "budget_cents": 1000,
              "is_remote": True, "recurrence": "hourly"},
        headers=auth(requester),
    )
    assert r.status_code == 400


def test_task006_non_recurring_does_not_respawn(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester, title="一次性保洁")
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    tasks = client.get("/api/v1/tasks", params={"q": "一次性保洁"}).json()
    assert tasks == []


# ---------- 文书生成 ----------
def test_law002_demand_letter_filled_from_contract(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester, title="橱柜安装")
    match_and_fund(client, requester, worker, task)
    r = client.post(
        "/api/v1/legal/documents",
        json={"kind": "demand_letter", "task_id": task["id"], "demand": "请于 3 日内完成安装"},
        headers=auth(requester),
    )
    body = r.json()
    assert "催告函" in body["text"] and "橱柜安装" in body["text"] and "200.00" in body["text"]
    assert "咨询执业律师" in body["disclaimer"]
    # 非当事人被拒
    outsider = register(client, "13200000001")
    r = client.post(
        "/api/v1/legal/documents",
        json={"kind": "demand_letter", "task_id": task["id"]},
        headers=auth(outsider),
    )
    assert r.status_code == 403


# ---------- 数据导出 ----------
def test_acc031_personal_data_export(client, requester, worker):
    topup(client, requester, 40000)
    task = publish_task(client, requester, title="导出测试单")
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    client.post(f"/api/v1/tasks/{task['id']}/reviews", json={"stars": 5}, headers=auth(requester))
    client.post("/api/v1/contents", json={"body": "我的动态"}, headers=auth(requester))
    data = client.get("/api/v1/users/me/export", headers=auth(requester)).json()
    assert data["real_name"] == "张三"
    assert any(t["title"] == "导出测试单" and t["role"] == "creator" for t in data["tasks"])
    assert any(e["kind"] == "escrow_hold" for e in data["ledger"])
    assert data["contents"][0]["body"] == "我的动态"
    assert data["reviews_written"][0]["stars"] == 5
