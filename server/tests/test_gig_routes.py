"""SCN-140 常用路线到点前推顺路的名额（208 号 spec，V236）。

V227 让顺路单可以带出发时间，但每天都要自己打开看。上下班这种固定路线，存一次就行：
哪几天、几点从「家」去「公司」——出发前一小时内推一次顺路的名额（一天一次、最多列 3 单，没有就不打扰）。
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.db import SessionLocal
from app.modules.gig import service as svc
from app.modules.gig.models import GigRoute
from app.modules.notification.models import Notification
from tests.conftest import JOB_HEADERS, auth
from tests.test_gig import _task

API = "/api/v1/gig"
CN = ZoneInfo("Asia/Shanghai")


def _places(client, h):
    home = client.post(f"{API}/places", json={"name": "家", "lat": 31.2300, "lng": 121.4700}, headers=h).json()
    office = client.post(f"{API}/places", json={"name": "公司", "lat": 31.2300, "lng": 121.4900}, headers=h).json()
    return home, office


def _utc(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=CN).astimezone(timezone.utc).replace(tzinfo=None)


def test_routes_crud_and_rules(client, requester, worker):
    h = auth(worker)
    home, office = _places(client, h)
    r = client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "08:30"}, headers=h)
    assert r.status_code == 201, r.text
    route = r.json()
    assert (route["from_name"], route["to_name"], route["weekdays"], route["within_hours"]) == ("家", "公司", [0, 1, 2, 3, 4], 3)
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(route, "GigRouteView")
    assert [x["id"] for x in client.get(f"{API}/routes", headers=h).json()] == [route["id"]]
    for body, code in [({"to_place": home["id"]}, "gig_route_same_place"), ({"weekdays": []}, "gig_route_no_days"),
                       ({"weekdays": [0, 7]}, "gig_route_no_days"), ({"depart_hm": "8:30"}, "gig_route_time_invalid")]:
        r = client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "08:30", **body}, headers=h)
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, body
    others = client.post(f"{API}/places", json={"name": "别人家", "lat": 31.2, "lng": 121.4}, headers=auth(requester)).json()
    assert client.post(f"{API}/routes", json={"from_place": others["id"], "to_place": office["id"], "depart_hm": "08:30"},
                       headers=h).status_code == 404, "别人的地点用不了"
    assert client.delete(f"{API}/routes/{route['id']}", headers=auth(requester)).status_code == 404, "别人的路线删不了"
    for _ in range(4):
        client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "18:00"}, headers=h)
    r = client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "19:00"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "gig_routes_full"
    client.delete(f"{API}/places/{home['id']}", headers=h)
    assert client.get(f"{API}/routes", headers=h).json() == [], "地点删了，用到它的路线一起删"


def test_push_once_within_an_hour_before_departure(client, requester, worker):
    h = auth(worker)
    home, office = _places(client, h)
    day = datetime.now(CN).date() + timedelta(days=3)
    client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "08:30",
                                       "weekdays": [day.weekday()], "within_hours": 2}, headers=h)
    fits = _task(requester["id"], "早上的名额", 31.2310, 121.4800, work_date=day, shift_start="09:00", shift_end="12:00")
    _task(requester["id"], "下午的名额", 31.2310, 121.4800, work_date=day, shift_start="14:00", shift_end="18:00")
    _task(requester["id"], "绕远的名额", 31.3000, 121.6000, work_date=day, shift_start="09:00", shift_end="12:00")
    with SessionLocal() as db:
        assert svc.push_routes(db, now=_utc(day, 7, 0)) == {"checked": 0, "pushed": 0}, "离出发还有一个半小时：先不推"
        assert svc.push_routes(db, now=_utc(day - timedelta(days=1), 8, 0)) == {"checked": 0, "pushed": 0}, "不是设的星期几"
        assert svc.push_routes(db, now=_utc(day, 8, 0)) == {"checked": 1, "pushed": 1}
        assert svc.push_routes(db, now=_utc(day, 8, 10)) == {"checked": 0, "pushed": 0}, "一天只推一次"
        db.commit()
        note = db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == "顺路单").one()
        assert "08:30 从「家」去「公司」，顺路有 1 单：早上的名额" == note.body
        assert db.query(GigRoute).one().last_pushed_on == day
    assert fits


def test_no_matching_slot_means_no_notification_and_the_job_endpoint_runs(client, requester, worker):
    h = auth(worker)
    home, office = _places(client, h)
    day = datetime.now(CN).date() + timedelta(days=3)
    client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "08:30",
                                       "weekdays": [day.weekday()]}, headers=h)
    with SessionLocal() as db:
        assert svc.push_routes(db, now=_utc(day, 8, 0)) == {"checked": 1, "pushed": 0}
        db.commit()
        assert db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == "顺路单").count() == 0
    r = client.post(f"{API}/jobs/route-push", headers=JOB_HEADERS)
    assert r.status_code == 200 and set(r.json()) == {"checked", "pushed"}
    assert client.post(f"{API}/jobs/route-push").status_code in (401, 403)


def test_routes_are_exported_and_deleted_with_the_account(client, worker):
    h = auth(worker)
    home, office = _places(client, h)
    client.post(f"{API}/routes", json={"from_place": home["id"], "to_place": office["id"], "depart_hm": "08:30"}, headers=h)
    gig = client.get("/api/v1/users/me/export", headers=h).json()["gig"]
    assert [p["name"] for p in gig["places"]] == ["家", "公司"] and gig["routes"][0]["depart_hm"] == "08:30"
    from app.modules.account.models import User
    from app.modules.account.deletion import erase_personal_data

    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, worker["id"]))
        db.commit()
        assert db.query(GigRoute).filter(GigRoute.owner_id == worker["id"]).count() == 0
