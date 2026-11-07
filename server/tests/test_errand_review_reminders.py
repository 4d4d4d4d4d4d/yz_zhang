"""SCN-220 发单复核等太久提醒运营（338 号 spec，V365）。

336 号的复核申请一提交就通知运营；在等超过 24 小时还没处理，每天催一次（一条一天最多一次），处理了就不再催。
后台列表写明时限、超过的标出来。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.notification.models import Notification
from app.modules.task.models import ErrandReview
from tests.conftest import JOB_HEADERS, auth, make_admin

API = "/api/v1"
JOB = f"{API}/tasks/jobs/remind-errand-reviews"
R = f"{API}/tasks/errand-reviews"
A = f"{API}/admin/errand-reviews"


def _age(review_id: int, hours: int, reminded_hours_ago: int | None = None):
    with SessionLocal() as db:
        r = db.get(ErrandReview, review_id)
        r.created_at = utcnow() - timedelta(hours=hours)
        r.reminded_at = None if reminded_hours_ago is None else utcnow() - timedelta(hours=reminded_hours_ago)
        db.commit()


def _bodies(user_id: int) -> list[str]:
    with SessionLocal() as db:
        return [n.body for n in db.query(Notification).filter(Notification.user_id == user_id,
                                                                 Notification.title == "发单复核等待处理")]


def test_reviews_waiting_over_24h_remind_ops_once_a_day_until_decided(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    ops = make_admin(client, "13600003651", "运营")
    a = client.post(R, json={"title": "刷单", "description": "店铺刷单", "explanation": "其实是找人试用写真实体验"},
                    headers=auth(requester)).json()
    b = client.post(R, json={"title": "刷好评", "description": "x", "explanation": "其实是收集真实用户反馈"},
                    headers=auth(requester)).json()
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "刚提交的不催"
    _age(a["id"], 30)
    _age(b["id"], 10)
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}, "只催等了 24 小时以上的"
    body = _bodies(ops["id"])[0]
    assert f"#{a['id']}" in body and f"#{b['id']}" not in body and "最久 30 小时" in body
    listed = {r["id"]: r for r in client.get(A, headers=auth(ops)).json()}
    _assert_shape(listed[a["id"]], "ErrandReviewAdminItem")
    assert listed[a["id"]]["overdue"] is True and listed[a["id"]]["sla_hours"] == 24
    assert listed[b["id"]]["overdue"] is False
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "一天最多催一次"
    _age(a["id"], 55, reminded_hours_ago=25)
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}, "过了一天再催"
    client.post(f"{A}/{a['id']}/reject", json={"note": "就是刷单，平台不能接"}, headers=auth(ops))
    _age(a["id"], 80, reminded_hours_ago=30)
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "处理了就不再催"
    decided = {r["id"]: r for r in client.get(f"{A}?status=all", headers=auth(ops)).json()}
    assert decided[a["id"]]["overdue"] is False, "处理过的不标超时"
    assert client.post(JOB).status_code in (401, 403)
