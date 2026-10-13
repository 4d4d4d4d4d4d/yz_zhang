"""SPACE-023 可用时段、少量接单与回复时长进入撮合（118 号 spec）。

只回答「截止前有没有空」，不把别人的日程给发布方看；回复时长样本够 5 次才说。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.matching.service import has_slot_between
from tests.conftest import auth, register, verify_user


def _person(client, phone, nick):
    u = register(client, phone, nick)
    verify_user(client, u, name=nick)
    return u


def _bj(y, m, d, hh, mm=0):
    """北京时间 → UTC 朴素值。"""
    return datetime(y, m, d, hh, mm, tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize("slots, start, end, expect", [
    ([{"d": 0, "from": "09:00", "to": "18:00"}], _bj(2026, 10, 12, 8), _bj(2026, 10, 12, 10), True),   # 周一 9-18 与 8-10 有交集
    ([{"d": 0, "from": "09:00", "to": "18:00"}], _bj(2026, 10, 12, 18), _bj(2026, 10, 12, 23), False),  # 刚好错开
    ([{"d": 5, "from": "09:00", "to": "12:00"}], _bj(2026, 10, 13, 0), _bj(2026, 10, 15, 0), False),   # 周二到周四没有周六
    ([{"d": 5, "from": "09:00", "to": "12:00"}], _bj(2026, 10, 13, 0), _bj(2026, 10, 18, 0), True),    # 到下周日就有
    ([{"d": 6, "from": "20:00", "to": "24:00"}], _bj(2026, 10, 18, 23), _bj(2026, 10, 19, 1), True),   # 到午夜
    ([], _bj(2026, 10, 13, 0), _bj(2026, 10, 20, 0), False),
])
def test_has_slot_between_in_beijing_time(slots, start, end, expect):
    assert has_slot_between(slots, start, end) is expect


def test_slots_and_limited_capacity_round_trip_and_bad_slots_are_422(client, requester):
    h = auth(requester)
    r = client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": 5, "from": "09:00", "to": "12:00"}],
                                               "limited_capacity": True}, headers=h)
    assert r.status_code == 200, r.text
    me = client.get("/api/v1/users/me", headers=h).json()
    assert me["weekly_slots"] == [{"d": 5, "from": "09:00", "to": "12:00"}] and me["limited_capacity"] is True
    assert client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": 1, "from": "18:00", "to": "09:00"}]},
                        headers=h).status_code == 422
    assert client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": 7, "from": "09:00", "to": "10:00"}]},
                        headers=h).status_code == 422
    # 原有字段不受影响（只增不减）
    assert client.patch("/api/v1/users/me", json={"available_times": "周末全天"}, headers=h).status_code == 200


def test_free_before_deadline_is_said_but_a_busy_schedule_is_never_shown(client, requester):
    """截止前有空的写进理由；没空的只降权、不写——不替他公开日程。"""
    free = _person(client, "13900019001", "有空的")
    busy = _person(client, "13900019002", "没空的")
    now_bj = datetime.now(timezone(timedelta(hours=8)))
    today = now_bj.weekday()
    client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": d, "from": "00:00", "to": "24:00"} for d in range(7)]},
                 headers=auth(free))
    # 没空的：只在 3 天后那一天有空，而截止在 1 天内
    client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": (today + 3) % 7, "from": "09:00", "to": "10:00"}]},
                 headers=auth(busy))
    from tests.test_task_flow import CLEAN_TASK

    deadline = (utcnow() + timedelta(hours=20)).isoformat() + "Z"
    t = client.post("/api/v1/tasks", json={**CLEAN_TASK, "deadline": deadline}, headers=auth(requester)).json()
    recs = {r["user_id"]: r for r in client.get(f"/api/v1/tasks/{t['id']}/recommendations", headers=auth(requester)).json()}
    assert "截止前有空（按本人设的时段）" in recs[free["id"]]["reasons"]
    assert not any("空" in x or "时段" in x for x in recs[busy["id"]]["reasons"])
    assert recs[free["id"]]["score"] > recs[busy["id"]]["score"]


def test_reply_time_needs_five_responses_before_it_is_shown(client, requester):
    from app.modules.matching.models import Invitation
    from tests.test_task_flow import CLEAN_TASK

    fast = _person(client, "13900019003", "回得快")
    t = client.post("/api/v1/tasks", json=CLEAN_TASK, headers=auth(requester)).json()

    def seed(n):
        with SessionLocal() as db:
            for i in range(n):
                created = utcnow() - timedelta(days=10, hours=i)
                db.add(Invitation(task_id=10_000 + i + n * 100, inviter_id=requester["id"], invitee_id=fast["id"],
                                  status="declined", created_at=created, responded_at=created + timedelta(minutes=50)))
            db.commit()

    seed(4)
    recs = {r["user_id"]: r for r in client.get(f"/api/v1/tasks/{t['id']}/recommendations", headers=auth(requester)).json()}
    assert not any("回复邀约" in x for x in recs[fast["id"]]["reasons"])         # 4 次不够
    seed(1)
    recs = {r["user_id"]: r for r in client.get(f"/api/v1/tasks/{t['id']}/recommendations", headers=auth(requester)).json()}
    assert "通常 1 小时内回复邀约" in recs[fast["id"]]["reasons"]


def test_limited_capacity_is_said_and_ranked_a_little_lower(client, requester):
    from tests.test_task_flow import CLEAN_TASK

    a = _person(client, "13900019004", "甲一")
    b = _person(client, "13900019005", "乙二")
    client.patch("/api/v1/users/me", json={"limited_capacity": True}, headers=auth(b))
    t = client.post("/api/v1/tasks", json=CLEAN_TASK, headers=auth(requester)).json()
    recs = {r["user_id"]: r for r in client.get(f"/api/v1/tasks/{t['id']}/recommendations", headers=auth(requester)).json()}
    assert "这阵子少量接单" in recs[b["id"]]["reasons"] and recs[b["id"]]["score"] < recs[a["id"]]["score"]


def test_responding_to_an_invitation_records_when(client, requester, worker):
    from app.modules.matching.models import Invitation
    from tests.test_task_flow import CLEAN_TASK

    t = client.post("/api/v1/tasks", json=CLEAN_TASK, headers=auth(requester)).json()
    inv = client.post(f"/api/v1/tasks/{t['id']}/invitations", json={"user_id": worker["id"], "message": "来吗"},
                      headers=auth(requester))
    assert inv.status_code == 201, inv.text
    client.post(f"/api/v1/invitations/{inv.json()['id']}/decline", headers=auth(worker))
    with SessionLocal() as db:
        row = db.get(Invitation, inv.json()["id"])
        assert row.responded_at is not None and row.responded_at >= row.created_at
