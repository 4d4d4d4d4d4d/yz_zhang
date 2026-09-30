"""NTF-005 通知未读徽章 + 一键全部已读 + 列表分页（应用红点标准能力）。"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _generate_notices(client, requester, worker, n=3):
    """通过发布→报名→成交→改价等动作给 worker 产生若干通知。"""
    topup(client, requester, 60000 * n)
    for i in range(n):
        t = publish_task(client, requester, budget_cents=20000, title=f"通知源{i}")
        cid = match_and_fund(client, requester, worker, t)
        # 改价通知（发给对方 worker）
        oid = client.post(f"/api/v1/contracts/{cid}/change-orders",
                          json={"new_amount_cents": 30000, "reason": "加量"},
                          headers=auth(requester)).json().get("id")
        if oid:
            client.post(f"/api/v1/contracts/{cid}/change-orders/{oid}/accept", headers=auth(worker))


def test_unread_count_and_mark_all_read(client, requester, worker):
    _generate_notices(client, requester, worker, n=3)

    before = client.get("/api/v1/notifications/unread-count", headers=auth(worker)).json()["unread"]
    assert before >= 3

    # 单条已读递减
    first = client.get("/api/v1/notifications", headers=auth(worker)).json()[0]["id"]
    client.post(f"/api/v1/notifications/{first}/read", headers=auth(worker))
    mid = client.get("/api/v1/notifications/unread-count", headers=auth(worker)).json()["unread"]
    assert mid == before - 1

    # 一键全部已读 → 计数归零
    r = client.post("/api/v1/notifications/read-all", headers=auth(worker))
    assert r.json()["marked"] == mid
    assert client.get("/api/v1/notifications/unread-count", headers=auth(worker)).json()["unread"] == 0
    # 幂等：再次全读标记 0 条
    assert client.post("/api/v1/notifications/read-all", headers=auth(worker)).json()["marked"] == 0


def test_unread_count_isolated_per_user(client, requester, worker):
    _generate_notices(client, requester, worker, n=2)
    stranger = register(client, "30000000001", "路人")
    assert client.get("/api/v1/notifications/unread-count", headers=auth(stranger)).json()["unread"] == 0
    assert client.get("/api/v1/notifications/unread-count", headers=auth(worker)).json()["unread"] >= 2


def test_notifications_paginated(client, requester, worker):
    _generate_notices(client, requester, worker, n=4)
    p1 = client.get("/api/v1/notifications?limit=2&offset=0", headers=auth(worker)).json()
    p2 = client.get("/api/v1/notifications?limit=2&offset=2", headers=auth(worker)).json()
    assert len(p1) == 2 and len(p2) == 2
    assert not (set(n["id"] for n in p1) & set(n["id"] for n in p2))
