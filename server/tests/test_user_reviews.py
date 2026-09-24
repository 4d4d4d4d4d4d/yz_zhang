"""CRED-006 用户口碑页：收到的评价可读，且严格遵守双盲揭晓规则。

此前评语/标签只写不读（主页仅 rating_avg），选人看不到「为什么是这个分」。
关键安全点：不能成为绕过 /tasks/{id}/reviews 双盲保护的旁路。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import engine
from app.modules.account.models import utcnow

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _complete(client, requester, worker, title):
    topup(client, requester, 30000)
    task = publish_task(client, requester, title=title, budget_cents=20000)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    return task


def test_blind_window_reviews_hidden_then_revealed(client, requester, worker):
    task = _complete(client, requester, worker, "口碑单一")

    # 仅发布者评了执行者 → 盲窗内，任何人都不应从用户维度看到
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 5, "comment": "很专业", "tags": ["准时", "专业"]},
                headers=auth(requester))
    got = client.get(f"/api/v1/users/{worker['id']}/reviews").json()
    assert got["total"] == 0 and got["items"] == []  # 双盲未揭晓，不泄露

    # 执行者回评 → 双方评完，揭晓
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 4, "comment": "雇主爽快"}, headers=auth(worker))
    got = client.get(f"/api/v1/users/{worker['id']}/reviews").json()
    assert got["total"] == 1
    assert got["items"][0]["stars"] == 5 and got["items"][0]["comment"] == "很专业"
    assert got["tag_counts"] == {"准时": 1, "专业": 1}


def test_window_expiry_reveals_single_sided_review(client, requester, worker):
    task = _complete(client, requester, worker, "口碑单二")
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 3, "comment": "一般般"}, headers=auth(requester))
    assert client.get(f"/api/v1/users/{worker['id']}/reviews").json()["total"] == 0

    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET completed_at = :d WHERE id = :t"),
                     {"d": utcnow() - timedelta(days=settings.REVIEW_WINDOW_DAYS + 1),
                      "t": task["id"]})
    got = client.get(f"/api/v1/users/{worker['id']}/reviews").json()
    assert got["total"] == 1 and got["items"][0]["stars"] == 3


def test_tag_aggregation_and_pagination(client, requester, worker):
    for i in range(3):
        task = _complete(client, requester, worker, f"口碑聚合{i}")
        client.post(f"/api/v1/tasks/{task['id']}/reviews",
                    json={"stars": 5, "comment": f"好评{i}", "tags": ["准时"]},
                    headers=auth(requester))
        client.post(f"/api/v1/tasks/{task['id']}/reviews",
                    json={"stars": 5}, headers=auth(worker))  # 回评以揭晓

    got = client.get(f"/api/v1/users/{worker['id']}/reviews").json()
    assert got["total"] == 3 and got["tag_counts"]["准时"] == 3

    p1 = client.get(f"/api/v1/users/{worker['id']}/reviews?limit=2&offset=0").json()
    p2 = client.get(f"/api/v1/users/{worker['id']}/reviews?limit=2&offset=2").json()
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    ids = [i["task_id"] for i in p1["items"] + p2["items"]]
    assert len(set(ids)) == 3  # 页间不重


def test_empty_for_user_without_reviews(client, requester):
    fresh = register(client, "34000000001", "新用户")
    got = client.get(f"/api/v1/users/{fresh['id']}/reviews").json()
    assert got == {"total": 0, "tag_counts": {}, "items": []}
