"""SCN-137 补招时顺带邀请那天有空、做过这类活的人（206 号 spec，V231）。

V224 的补招只是再推一次：叫醒「现在有空」的人和订阅这个类目的人。但最可能来的，是**做过这类活、那天正好有空**的人——
他们不一定开着「有空」，也不一定订阅了。现在补招可以顺带给几个这样的人发邀约（按推荐排序、按 V207 的时段撮合挑人）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.matching.models import Invitation
from app.modules.notification.models import Notification
from app.modules.task.models import ProgressLog
from tests.conftest import auth
from tests.test_availability import _person
from tests.test_gig import _task
from tests.test_multiday_slots import _post, _today

API = "/api/v1/tasks"


def _slots(client, u, wd, frm, to):
    client.patch("/api/v1/users/me", json={"weekly_slots": [{"d": wd, "from": frm, "to": to}]}, headers=auth(u))


def test_reboost_invites_people_who_did_this_kind_of_work_and_are_free_that_day(client, requester):
    start = _today() + timedelta(days=3)
    t = _post(client, requester, people_needed=2, days=2, start_date=start.isoformat(), shift_start="09:00", shift_end="18:00").json()
    wd = start.weekday()
    good = _person(client, "13900037001", "做过也有空")
    good2 = _person(client, "13900037002", "也做过也有空")
    busy = _person(client, "13900037003", "做过但那天没空")
    partial = _person(client, "13900037004", "做过但只有上午")
    novice = _person(client, "13900037005", "有空但没做过")
    other = _person(client, "13900037006", "做过别的类目")
    applied = _person(client, "13900037007", "已经报了名")
    for u in (good, good2, partial, novice, other, applied):
        _slots(client, u, wd, "08:00" if u is not partial else "09:00", "20:00" if u is not partial else "12:00")
    _slots(client, busy, (wd + 1) % 7, "08:00", "20:00")
    for u in (good, good2, busy, partial, applied):
        _task(requester["id"], "做完的跑腿", 31.23, 121.47, category="跑腿", status="completed", executor_id=u["id"])
    _task(requester["id"], "做完的保洁", 31.23, 121.47, category="保洁", status="completed", executor_id=other["id"])
    day1 = [s["id"] for s in t["slots"][:2]]
    client.post(f"{API}/{day1[1]}/applications", json={}, headers=auth(applied))
    r = client.post(f"{API}/{t['id']}/days/{start.isoformat()}/reboost", json={"invite": 3}, headers=auth(requester))
    assert r.status_code == 200, r.text
    got = r.json()["invited"]
    assert {x["user_id"] for x in got} == {good["id"], good2["id"]}, "只邀做过这个类目、那天时段整段盖住、还没报名的人"
    assert all(x["task_id"] == day1[0] for x in got), "邀约落在那天第一个还在招的名额上"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "ReboostDayResult")
    _assert_shape(got[0], "ReboostInvite")
    with SessionLocal() as db:
        assert db.query(Invitation).filter(Invitation.invitee_id == good["id"], Invitation.task_id == day1[0]).count() == 1
        note = db.query(Notification).filter(Notification.user_id == good["id"], Notification.title == "收到任务邀约").one()
        assert "还缺人" in note.body and "08:00" not in note.body, "通知里不写对方的日程"
        log = db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "reboost").one()
        assert "邀请了 2 个" in log.content


def test_invite_is_capped_and_never_repeats(client, requester):
    start = _today() + timedelta(days=3)
    t = _post(client, requester, people_needed=1, days=2, start_date=start.isoformat()).json()
    people = [_person(client, f"1390003710{i}", f"帮手{i}") for i in range(3)]
    for u in people:
        _slots(client, u, start.weekday(), "10:00", "12:00")          # 名额没写时段：那天有空就行
        _task(requester["id"], "做完的跑腿", 31.23, 121.47, category="跑腿", status="completed", executor_id=u["id"])
    busy = _person(client, "13900037109", "那天没空")           # 做过，但那个星期几没设时段
    _slots(client, busy, (start.weekday() + 1) % 7, "10:00", "12:00")
    _task(requester["id"], "做完的跑腿", 31.23, 121.47, category="跑腿", status="completed", executor_id=busy["id"])
    url = f"{API}/{t['id']}/days/{start.isoformat()}/reboost"
    assert len(client.post(url, json={"invite": 2}, headers=auth(requester)).json()["invited"]) == 2
    assert client.post(url, json={"invite": 6}, headers=auth(requester)).status_code == 422, "一次最多邀 5 个"
    assert client.post(url, json={}, headers=auth(requester)).json()["detail"]["code"] == "reboost_too_soon"
    with SessionLocal() as db:   # 冷却过后再补招：已邀过的人不再打扰
        log = db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "reboost").one()
        log.created_at -= timedelta(hours=7)
        db.commit()
    again = client.post(url, json={"invite": 5}, headers=auth(requester)).json()["invited"]
    assert len(again) == 1 and again[0]["user_id"] != busy["id"], "名额没写时段：那天有空才邀"
    plain = client.post(f"{API}/{t['id']}/days/{(start + timedelta(days=1)).isoformat()}/reboost", json={}, headers=auth(requester))
    assert plain.json()["invited"] == [], "不勾邀请就不邀"
