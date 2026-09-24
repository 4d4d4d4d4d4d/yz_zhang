"""CRED-002 双盲互评完整规则（业界惯例：Upwork 双盲 + 14 天窗口）。

防报复性差评的两个关键点：
1. 双方都评完或窗口到期前，评价对所有人（除作者/管理员）隐藏——
   含第三方，否则换个账号即可偷看，盲评失效；
2. 窗口到期：单方评价自动公开，且不可再补评（防无限期雪藏与秋后算账）。
"""
from datetime import timedelta

import sqlalchemy as sa

from app.core.config import settings
from app.core.db import engine
from app.modules.account.models import utcnow

from .conftest import auth, register, topup, verify_user
from .test_task_flow import match_and_fund, publish_task


def _complete(client, requester, worker, title="盲评单"):
    topup(client, requester, 20000)
    task = publish_task(client, requester, title=title)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    return task


def _backdate_completed(task_id: int, days: float) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE tasks SET completed_at = :d WHERE id = :t"),
                     {"d": utcnow() - timedelta(days=days), "t": task_id})


def test_blind_until_both_submitted_including_strangers(client, requester, worker):
    task = _complete(client, requester, worker)
    stranger = register(client, "20000000001", "路人")

    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 2, "comment": "沟通不畅"}, headers=auth(requester))

    # 作者可见自己的
    mine = client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(requester)).json()
    assert len(mine) == 1 and mine[0]["revealed"] is False
    # 对方看不到（盲窗内）
    assert client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(worker)).json() == []
    # 第三方也看不到——堵住换号偷看
    assert client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(stranger)).json() == []

    # 对方提交后 → 双向公开，第三方也可见
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 5, "comment": "雇主很好"}, headers=auth(worker))
    for u in (requester, worker, stranger):
        rows = client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(u)).json()
        assert len(rows) == 2 and all(r["revealed"] for r in rows)


def test_window_expiry_reveals_single_review_and_blocks_late_submit(client, requester, worker):
    task = _complete(client, requester, worker, title="窗口到期单")
    client.post(f"/api/v1/tasks/{task['id']}/reviews",
                json={"stars": 4, "comment": "整体不错"}, headers=auth(worker))
    # 窗口内：发布者看不到
    assert client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(requester)).json() == []

    _backdate_completed(task["id"], settings.REVIEW_WINDOW_DAYS + 0.5)

    # 到期：单方评价自动公开
    rows = client.get(f"/api/v1/tasks/{task['id']}/reviews", headers=auth(requester)).json()
    assert len(rows) == 1 and rows[0]["revealed"] is True and rows[0]["stars"] == 4
    # 到期后不可再补评（防看到差评后报复）
    r = client.post(f"/api/v1/tasks/{task['id']}/reviews",
                    json={"stars": 1, "comment": "报复"}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "review_window_closed"
