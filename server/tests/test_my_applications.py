"""MATCH-010 我的报名：等待选人的报名可追踪（/tasks/mine?role=working 只含已成交单）。"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import publish_task


def test_my_applications_lists_with_task_status(client, requester, worker):
    topup(client, requester, 40000)
    t1 = publish_task(client, requester, title="报名单一")
    t2 = publish_task(client, requester, title="报名单二")
    a1 = client.post(f"/api/v1/tasks/{t1['id']}/applications", json={"bid_cents": 9000},
                     headers=auth(worker)).json()["id"]
    client.post(f"/api/v1/tasks/{t2['id']}/applications", json={}, headers=auth(worker))

    rows = client.get("/api/v1/users/me/applications", headers=auth(worker)).json()
    assert len(rows) == 2
    by_task = {r["task_id"]: r for r in rows}
    assert by_task[t1["id"]]["bid_cents"] == 9000
    assert by_task[t1["id"]]["task_title"] == "报名单一"
    assert all(r["status"] == "pending" and r["task_status"] == "published" for r in rows)

    # 选中 t1 → 该报名 accepted；t2 是另一任务，仍 pending（互不影响）
    client.post(f"/api/v1/applications/{a1}/accept", headers=auth(requester))
    accepted = client.get("/api/v1/users/me/applications?status=accepted", headers=auth(worker)).json()
    assert [r["task_id"] for r in accepted] == [t1["id"]]
    pending = client.get("/api/v1/users/me/applications?status=pending", headers=auth(worker)).json()
    assert [r["task_id"] for r in pending] == [t2["id"]]


def test_my_applications_isolated_and_requires_auth(client, requester, worker):
    assert client.get("/api/v1/users/me/applications").status_code == 403
    t = publish_task(client, requester, title="隔离单")
    client.post(f"/api/v1/tasks/{t['id']}/applications", json={}, headers=auth(worker))
    # requester 没报名过，列表为空
    assert client.get("/api/v1/users/me/applications", headers=auth(requester)).json() == []


def test_my_applications_paginated(client, requester, worker):
    for i in range(5):
        t = publish_task(client, requester, title=f"分页报名{i}")
        client.post(f"/api/v1/tasks/{t['id']}/applications", json={}, headers=auth(worker))
    p1 = client.get("/api/v1/users/me/applications?limit=2&offset=0", headers=auth(worker)).json()
    p2 = client.get("/api/v1/users/me/applications?limit=2&offset=2", headers=auth(worker)).json()
    assert len(p1) == 2 and len(p2) == 2
    assert not (set(r["application_id"] for r in p1) & set(r["application_id"] for r in p2))
