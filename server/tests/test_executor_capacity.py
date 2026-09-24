"""TASK-011 执行者并发接单上限（零工平台惯例：防过度接单导致履约违约）。

在途单 = matched / in_progress / pending_acceptance；达上限后：
报名被拒、发布者选人被拒、接受邀约被拒；完成一单即释放额度。
"""
import pytest

from app.core.config import settings

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


@pytest.fixture(autouse=True)
def small_cap(monkeypatch):
    monkeypatch.setattr(settings, "MAX_ACTIVE_TASKS", 2)


def test_capacity_blocks_apply_accept_and_frees_on_completion(client, requester, worker):
    topup(client, requester, 100000)

    # 占满 2 个在途额度
    tasks = [publish_task(client, requester, title=f"在途{i}") for i in range(2)]
    for t in tasks:
        match_and_fund(client, requester, worker, t)

    # 第 3 单：报名即被拒
    t3 = publish_task(client, requester, title="超额单")
    r = client.post(f"/api/v1/tasks/{t3['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "capacity_full"

    # 完成一单释放额度 → 报名恢复
    client.post(f"/api/v1/tasks/{tasks[0]['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{tasks[0]['id']}/accept-delivery", headers=auth(requester))
    r = client.post(f"/api/v1/tasks/{t3['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 201


def test_capacity_rechecked_at_accept_time(client, requester, worker):
    """报名时未满、成交时已满 → 选人被拒（上限以成交时点为准）。"""
    topup(client, requester, 100000)

    # 只占 1 个额度时先报名第 2、3 单
    t1 = publish_task(client, requester, title="首单")
    match_and_fund(client, requester, worker, t1)
    t2 = publish_task(client, requester, title="次单")
    t3 = publish_task(client, requester, title="末单")
    a2 = client.post(f"/api/v1/tasks/{t2['id']}/applications", json={}, headers=auth(worker)).json()["id"]
    a3 = client.post(f"/api/v1/tasks/{t3['id']}/applications", json={}, headers=auth(worker)).json()["id"]

    # 选人成交第 2 单 → 在途满 2
    assert client.post(f"/api/v1/applications/{a2}/accept", headers=auth(requester)).status_code == 200
    # 第 3 单成交时复核 → 拒绝
    r = client.post(f"/api/v1/applications/{a3}/accept", headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "capacity_full"


def test_capacity_blocks_invitation_accept(client, requester, worker):
    topup(client, requester, 100000)
    for i in range(2):
        t = publish_task(client, requester, title=f"占额{i}")
        match_and_fund(client, requester, worker, t)

    t_inv = publish_task(client, requester, title="邀约单")
    inv = client.post(f"/api/v1/tasks/{t_inv['id']}/invitations",
                      json={"user_id": worker["id"], "message": "来帮忙"},
                      headers=auth(requester)).json()
    r = client.post(f"/api/v1/invitations/{inv['id']}/accept", headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "capacity_full"
