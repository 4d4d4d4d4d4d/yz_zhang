"""SCN-138 发布后改某一天的时段（202 号 spec，V234）。

快闪店周日改成 10 点开门：以前只能在每个名额上逐个改，或者取消重发。现在在那一天上改一次：
还在招的名额时段与标题一起改，已报名的人收到通知；已经有人接的名额不动（时间是签过的条款，要走变更单），逐个说明。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from app.modules.task.models import Task
from tests.conftest import auth, register, verify_user
from tests.test_multiday_slots import _post, _today

API = "/api/v1/tasks"


def _parent(client, requester, people=2, days=2):
    start = _today() + timedelta(days=2)
    t = _post(client, requester, people_needed=people, days=days, start_date=start.isoformat(),
              shift_start="09:00", shift_end="18:00").json()
    return t, [(start + timedelta(days=i)) for i in range(days)]


def test_open_slots_of_that_day_change_and_taken_ones_are_explained(client, requester, worker):
    t, d = _parent(client, requester)
    day2 = [s["id"] for s in t["slots"][2:]]
    with SessionLocal() as db:
        db.get(Task, day2[0]).executor_id = worker["id"]
        db.get(Task, day2[0]).status = "matched"
        db.commit()
    applicant = register(client, "13800000394", "帮手乙")
    verify_user(client, applicant, "帮手乙")
    client.post(f"{API}/{day2[1]}/applications", json={}, headers=auth(applicant))
    r = client.patch(f"{API}/{t['id']}/days/{d[1].isoformat()}/shift", json={"shift_start": "10:00", "shift_end": "16:00"},
                     headers=auth(requester))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["changed"] == [day2[1]] and out["kept"][0]["task_id"] == day2[0] and "变更单" in out["kept"][0]["reason"]
    md = f"{d[1].month:02d}-{d[1].day:02d}"
    with SessionLocal() as db:
        s = db.get(Task, day2[1])
        assert (s.shift_start, s.shift_end) == ("10:00", "16:00") and f"（{md} 10:00–16:00）" in s.title
        taken = db.get(Task, day2[0])
        assert (taken.shift_start, taken.shift_end) == ("09:00", "18:00"), "有人接的不动"
        assert all(db.get(Task, x["id"]).shift_start == "09:00" for x in t["slots"][:2]), "别的日子不动"
        note = db.query(Notification).filter(Notification.user_id == applicant["id"], Notification.title == "报名的任务有更新").one()
        assert "改了时段：10:00–16:00" in note.body


def test_clearing_the_shift_of_a_day(client, requester):
    t, d = _parent(client, requester, people=1)
    r = client.patch(f"{API}/{t['id']}/days/{d[0].isoformat()}/shift", json={}, headers=auth(requester))
    md = f"{d[0].month:02d}-{d[0].day:02d}"
    with SessionLocal() as db:
        s = db.get(Task, r.json()["changed"][0])
        assert (s.shift_start, s.title.count(f"（{md}）")) == ("", 1)


def test_rules(client, requester, worker):
    t, d = _parent(client, requester, people=1)
    url = f"{API}/{t['id']}/days/{d[0].isoformat()}/shift"
    assert client.patch(url, json={"shift_start": "10:00", "shift_end": "16:00"}, headers=auth(worker)).status_code == 403
    for body, code in [({"shift_start": "10:00"}, "shift_incomplete"), ({"shift_start": "1000", "shift_end": "16:00"}, "shift_invalid"),
                       ({"shift_start": "16:00", "shift_end": "10:00"}, "shift_order")]:
        r = client.patch(url, json=body, headers=auth(requester))
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, body
    past = (_today() - timedelta(days=1)).isoformat()
    assert client.patch(f"{API}/{t['id']}/days/{past}/shift", json={}, headers=auth(requester)).json()["detail"]["code"] == "day_passed"
    missing = (d[1] + timedelta(days=5)).isoformat()
    assert client.patch(f"{API}/{t['id']}/days/{missing}/shift", json={}, headers=auth(requester)).json()["detail"]["code"] == "day_full"
    single = _post(client, requester).json()
    r = client.patch(f"{API}/{single['id']}/days/{d[0].isoformat()}/shift", json={}, headers=auth(requester))
    assert r.json()["detail"]["code"] == "not_multi_day"


def test_a_day_whose_slots_all_ended_says_so(client, requester):
    t, d = _parent(client, requester, people=1)
    with SessionLocal() as db:
        db.get(Task, t["slots"][0]["id"]).status = "completed"
        db.commit()
    r = client.patch(f"{API}/{t['id']}/days/{d[0].isoformat()}/shift", json={}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "day_full"
