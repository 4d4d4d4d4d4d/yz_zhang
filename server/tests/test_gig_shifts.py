"""SCN-129 「现在有空」推单与顺路单也按名额时段过滤（192 号 spec，V220）。

名额写着「哪天几点到几点」（北京时间，V205）。此前附近、顺路、新单推送都只看截止时间：
昨天的名额还挂在「附近」里，「接下来两小时有空」的人收到下周三的推送。现在：时段已经过去的不出现；
开着「现在有空」时，只出现与「现在 → 有空截止」对得上的名额；卡片带上哪天几点。
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.db import SessionLocal
from app.modules.gig import service as svc
from app.modules.notification.models import Notification
from app.modules.task.models import Task
from tests.conftest import auth
from tests.test_gig import HOME, _task

API = "/api/v1/gig"
CN = ZoneInfo("Asia/Shanghai")


def _today():
    return datetime.now(CN).date()


def _slots(requester):
    today = _today()
    return {
        "today": _task(requester["id"], "今天全天的名额", 31.2310, 121.4710, work_date=today, shift_start="00:00", shift_end="23:59"),
        "ended": _task(requester["id"], "昨天的名额", 31.2310, 121.4710, work_date=today - timedelta(days=1),
                       shift_start="09:00", shift_end="18:00"),
        "later": _task(requester["id"], "三天后的名额", 31.2310, 121.4710, work_date=today + timedelta(days=3),
                       shift_start="09:00", shift_end="18:00"),
        "plain": _task(requester["id"], "不按天的单", 31.2310, 121.4710),
    }


def test_slot_window_is_beijing_time_converted_to_utc():
    t = Task(work_date=date(2030, 1, 7), shift_start="09:00", shift_end="18:30")
    assert svc.slot_window(t) == (datetime(2030, 1, 7, 1, 0), datetime(2030, 1, 7, 10, 30))
    t = Task(work_date=date(2030, 1, 7), shift_start="", shift_end="")
    assert svc.slot_window(t) == (datetime(2030, 1, 6, 16, 0), datetime(2030, 1, 7, 16, 0)), "没写时段按北京时间整天"
    assert svc.slot_window(Task()) is None


def test_nearby_without_availability_hides_only_slots_that_are_over(client, requester, worker):
    ids = _slots(requester)
    items = client.get(f"{API}/nearby", params={"lat": HOME[0], "lng": HOME[1]}, headers=auth(worker)).json()["items"]
    got = {x["task_id"] for x in items}
    assert got == {ids["today"], ids["later"], ids["plain"]}, "时段已经过去的名额不再出现"
    later = next(x for x in items if x["task_id"] == ids["later"])
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(later, "GigTaskCard")
    assert (later["work_date"], later["shift_start"], later["shift_end"]) == (
        (_today() + timedelta(days=3)).isoformat(), "09:00", "18:00"), "卡片写明哪天几点"
    plain = next(x for x in items if x["task_id"] == ids["plain"])
    assert (plain["work_date"], plain["shift_start"]) == (None, "")


def test_with_availability_only_slots_that_fit_the_free_window_show_up(client, requester, worker):
    ids = _slots(requester)
    h = auth(worker)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1], "radius_km": 5, "hours": 2}, headers=h)
    got = {x["task_id"] for x in client.get(f"{API}/nearby", headers=h).json()["items"]}
    assert got == {ids["today"], ids["plain"]}, "三天后的名额与接下来两小时对不上"
    place = client.post(f"{API}/places", json={"name": "公司", "lat": 31.2300, "lng": 121.4900}, headers=h).json()
    along = client.get(f"{API}/along", params={"from_lat": HOME[0], "from_lng": HOME[1], "to_place": place["id"]},
                       headers=h).json()["items"]
    assert {x["task_id"] for x in along} == {ids["today"], ids["plain"]}, "顺路单同一条规则"
    client.delete(f"{API}/available", headers=h)
    along = client.get(f"{API}/along", params={"from_lat": HOME[0], "from_lng": HOME[1], "to_place": place["id"]},
                       headers=h).json()["items"]
    assert {x["task_id"] for x in along} == {ids["today"], ids["later"], ids["plain"]}, "没开「有空」只去掉过去的"


def test_new_slot_is_pushed_only_when_it_fits_the_free_window(client, requester, worker):
    h = auth(worker)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1], "radius_km": 3, "hours": 2}, headers=h)
    today = _today()

    def publish(title, **kw):
        tid = _task(requester["id"], title, 31.2310, 121.4710, status="draft", **kw)
        with SessionLocal() as db:
            from app.modules.task import service as tsvc

            tsvc.transition(db, db.get(Task, tid), "published")
            db.commit()

    publish("今天的名额", work_date=today, shift_start="00:00", shift_end="23:59")
    publish("下周的名额", work_date=today + timedelta(days=7), shift_start="09:00", shift_end="12:00")
    publish("不按天的单")
    with SessionLocal() as db:
        bodies = [n.body for n in db.query(Notification).filter(Notification.user_id == worker["id"],
                                                                Notification.title == svc.PUSH_TITLE)]
    assert len(bodies) == 2 and not any("下周的名额" in b for b in bodies)
