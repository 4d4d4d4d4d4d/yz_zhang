"""TASK-017 任务详情的「我与此任务的关系」上下文：已报名/已收藏/报名数。

避免糟糕体验：worker 报名后详情仍显示「报名」按钮，点了才被 already_applied 拒。
"""
from .conftest import auth, register, topup, verify_user
from .test_task_flow import publish_task


def test_my_application_status_and_bookmark_flags(client, requester, worker):
    task = publish_task(client, requester, title="上下文单")

    # 未报名未收藏
    d = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert d["my_application_status"] is None and d["bookmarked"] is False

    client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/bookmark", headers=auth(worker))
    d = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert d["my_application_status"] == "pending" and d["bookmarked"] is True

    # 取消收藏后回落
    client.delete(f"/api/v1/tasks/{task['id']}/bookmark", headers=auth(worker))
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()["bookmarked"] is False


def test_applications_count_only_for_creator(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title="报名数单")
    client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(worker))
    other = register(client, "31000000001", "候选乙")
    verify_user(client, other, "候选乙")
    client.post(f"/api/v1/tasks/{task['id']}/applications", json={}, headers=auth(other))

    # 发布者看到报名数
    dc = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(requester)).json()
    assert dc["applications_count"] == 2
    # 非发布者看不到该字段
    dw = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert "applications_count" not in dw


def test_status_reflects_acceptance(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title="成交上下文单")
    app_id = client.post(f"/api/v1/tasks/{task['id']}/applications", json={},
                         headers=auth(worker)).json()["id"]
    client.post(f"/api/v1/applications/{app_id}/accept", headers=auth(requester))
    d = client.get(f"/api/v1/tasks/{task['id']}", headers=auth(worker)).json()
    assert d["my_application_status"] == "accepted"
