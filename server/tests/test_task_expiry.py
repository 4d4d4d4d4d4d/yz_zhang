"""TASK-015 过期任务自动下架：deadline 过后仍无人成交的 published 任务自动关闭。

补的是"发布时校验了 deadline、发布后却从不执行"的缺口——僵尸挂单永占广场。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.db import engine
from app.modules.account.models import utcnow

from .conftest import auth, register, verify_user
from .test_task_flow import match_and_fund, publish_task


def _publish_with_future_deadline(client, requester, title, days=3):
    future = (utcnow() + timedelta(days=days)).isoformat()
    return client.post("/api/v1/tasks", json={
        "title": title, "category": "跑腿", "budget_cents": 10000,
        "is_remote": True, "deadline": future, "publish_now": True,
    }, headers=auth(requester)).json()


def _backdate_deadline(task_id: int, days_ago: float = 0.1) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET deadline = :d WHERE id = :t"),
                     {"d": utcnow() - timedelta(days=days_ago), "t": task_id})


def test_expired_unmatched_task_auto_closed(client, requester, worker):
    expired = _publish_with_future_deadline(client, requester, "过期挂单")
    # 有一个报名者，但一直没成交
    client.post(f"/api/v1/tasks/{expired['id']}/applications", json={}, headers=auth(worker))
    _backdate_deadline(expired["id"])

    # 一个仍在有效期内的任务，不应被动
    fresh = _publish_with_future_deadline(client, requester, "有效挂单")

    r = client.post("/api/v1/tasks/jobs/expire-tasks")
    assert r.json()["expired"] == 1

    assert client.get(f"/api/v1/tasks/{expired['id']}",
                      headers=auth(requester)).json()["status"] == "cancelled"
    assert client.get(f"/api/v1/tasks/{fresh['id']}",
                      headers=auth(requester)).json()["status"] == "published"

    # 发布者与报名者都收到通知
    boss_notices = client.get("/api/v1/notifications", headers=auth(requester)).json()
    assert any("过期下架" in n["title"] for n in boss_notices)
    worker_notices = client.get("/api/v1/notifications", headers=auth(worker)).json()
    assert any("已下架" in n["title"] for n in worker_notices)

    # 幂等：重跑无新过期
    assert client.post("/api/v1/tasks/jobs/expire-tasks").json()["expired"] == 0


def test_matched_task_not_expired(client, requester, worker):
    """已成交的任务即使过了 deadline 也不被下架（进入履约不受招募截止约束）。"""
    from .conftest import topup

    topup(client, requester, 20000)
    task = _publish_with_future_deadline(client, requester, "已成交单")
    match_and_fund(client, requester, worker, task)  # → matched
    _backdate_deadline(task["id"])

    assert client.post("/api/v1/tasks/jobs/expire-tasks").json()["expired"] == 0
    # 未被下架（仍处于履约态，非 cancelled）
    assert client.get(f"/api/v1/tasks/{task['id']}",
                      headers=auth(requester)).json()["status"] in ("matched", "in_progress")


def test_task_without_deadline_never_expires(client, requester):
    task = publish_task(client, requester, title="无截止任务")  # 无 deadline
    assert client.post("/api/v1/tasks/jobs/expire-tasks").json()["expired"] == 0
    assert client.get(f"/api/v1/tasks/{task['id']}",
                      headers=auth(requester)).json()["status"] == "published"
