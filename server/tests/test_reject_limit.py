"""TASK-033 验收驳回上限：防发布方无限返工变相欠薪。

超过上限后不得再单方驳回，须验收或走纠纷仲裁；执行者每次被驳回都收到通知。
"""
from app.core.config import settings

from .conftest import auth, topup
from .test_task_flow import match_and_fund, publish_task


def _deliver(client, worker, task_id):
    client.post(f"/api/v1/tasks/{task_id}/deliver", headers=auth(worker))


def test_reject_capped_and_forces_arbitration(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title="返工单")
    match_and_fund(client, requester, worker, task)

    # 连续驳回至上限
    for i in range(settings.MAX_REJECT_ROUNDS):
        _deliver(client, worker, task["id"])
        r = client.post(f"/api/v1/tasks/{task['id']}/reject-delivery",
                        json={"reason": f"还需修改{i}"}, headers=auth(requester))
        assert r.status_code == 200, r.text

    # 再次交付后，第 N+1 次驳回被拒
    _deliver(client, worker, task["id"])
    r = client.post(f"/api/v1/tasks/{task['id']}/reject-delivery",
                    json={"reason": "继续挑刺"}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "reject_limit_reached"

    # 出路一：发布方验收放款（正常收尾）
    accept = client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    assert accept.status_code == 200 and accept.json()["status"] == "completed"


def test_worker_can_escalate_to_dispute_at_cap(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title="返工争议单")
    match_and_fund(client, requester, worker, task)
    for i in range(settings.MAX_REJECT_ROUNDS):
        _deliver(client, worker, task["id"])
        client.post(f"/api/v1/tasks/{task['id']}/reject-delivery",
                    json={"reason": f"改{i}"}, headers=auth(requester))

    # 出路二：执行者发起纠纷（合约仍 funded，可仲裁）
    r = client.post(f"/api/v1/tasks/{task['id']}/disputes",
                    json={"reason": "发布方反复驳回拒不验收，申请仲裁"}, headers=auth(worker))
    assert r.status_code == 201


def test_worker_notified_on_each_rejection(client, requester, worker):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title="通知返工单")
    match_and_fund(client, requester, worker, task)
    _deliver(client, worker, task["id"])
    client.post(f"/api/v1/tasks/{task['id']}/reject-delivery",
                json={"reason": "边角未清洁"}, headers=auth(requester))

    notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("交付被驳回" in n["title"] for n in notices)
