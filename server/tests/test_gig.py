"""GIG-100~109 接单者服务包（125 号 spec）：现在有空、附近、顺路、报价参考、新单推送。

用户原话：「普通接单用户就想要如何能够就近帮助打扫卫生，顺路送个单等，这些都需要 AI 来帮助实现。」
"""
import json
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.gig import service as svc
from app.modules.gig.models import GigAvailability, GigPlace
from app.modules.knowledge.models import KnowledgeCard
from app.modules.notification.models import Notification
from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.task.models import Task
from tests.conftest import auth, make_admin

API = "/api/v1/gig"
HOME = (31.2300, 121.4700)       # 上海人民广场附近
OFFICE = (31.2300, 121.5300)     # 正东约 5.7 公里
GIG_SEED = json.loads((psvc.SEEDS / "gig-nearby.json").read_text(encoding="utf-8"))


def _task(creator_id, title, lat, lng, category="保洁", budget=20000, **kw):
    with SessionLocal() as db:
        t = Task(creator_id=creator_id, title=title, description="", category=category, budget_cents=budget,
                 status=kw.pop("status", "published"), visibility=kw.pop("visibility", "public"),
                 is_remote=kw.pop("is_remote", False), lat=lat, lng=lng, city="上海", address_hint="人民广场", **kw)
        db.add(t)
        db.commit()
        return t.id


# ------------------------------------------------------------------ 现在有空（GIG-101）
def test_availability_is_coarse_expires_and_can_be_turned_off(client, worker):
    h = auth(worker)
    assert client.get(f"{API}/available", headers=h).json()["available"] is False
    r = client.put(f"{API}/available", json={"lat": 31.23456, "lng": 121.47891, "radius_km": 3, "hours": 2,
                                             "categories": ["保洁", "保洁", " "]}, headers=h).json()
    assert r["available"] and r["radius_km"] == 3 and r["categories"] == ["保洁"]
    with SessionLocal() as db:
        a = db.get(GigAvailability, worker["id"])
        assert (a.lat, a.lng) == (31.23, 121.48)                       # 只存约 1 公里精度
        a.until = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get(f"{API}/available", headers=h).json()["available"] is False
    with SessionLocal() as db:
        assert db.get(GigAvailability, worker["id"]) is None            # 读的时候顺手删掉了位置
    client.put(f"{API}/available", json={"lat": 31.2, "lng": 121.4}, headers=h)
    assert client.delete(f"{API}/available", headers=h).json()["available"] is False
    with SessionLocal() as db:
        assert db.get(GigAvailability, worker["id"]) is None
    assert client.put(f"{API}/available", json={"lat": 31.2, "lng": 121.4, "hours": 24}, headers=h).status_code == 422


def test_purge_job_deletes_expired_locations(client, worker, requester):
    from tests.conftest import JOB_HEADERS

    with SessionLocal() as db:
        db.add(GigAvailability(user_id=worker["id"], until=utcnow() - timedelta(hours=1), lat=31.2, lng=121.4))
        db.add(GigAvailability(user_id=requester["id"], until=utcnow() + timedelta(hours=1), lat=31.2, lng=121.4))
        db.commit()
    assert client.post(f"{API}/jobs/purge-expired", headers=JOB_HEADERS).json() == {"purged": 1}
    assert client.post(f"{API}/jobs/purge-expired").status_code in (401, 403)


# ------------------------------------------------------------------ 附近（GIG-102）
def test_nearby_filters_and_sorts(client, requester, worker):
    near = _task(requester["id"], "两居室保洁", 31.2310, 121.4710, budget=15000)
    near_rich = _task(requester["id"], "三居室保洁", 31.2312, 121.4712, budget=30000)
    _task(requester["id"], "很远的保洁", 31.4000, 121.4700)                 # 约 19 公里
    _task(requester["id"], "线上设计", 31.2310, 121.4710, category="设计", is_remote=True)
    _task(requester["id"], "已过期", 31.2310, 121.4710, deadline=utcnow() - timedelta(hours=1))
    _task(requester["id"], "草稿", 31.2310, 121.4710, status="draft")
    _task(worker["id"], "我自己发的", 31.2310, 121.4710)
    _task(requester["id"], "维修", 31.2311, 121.4711, category="维修")
    h = auth(worker)
    r = client.get(f"{API}/nearby", headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "gig_need_location"
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1], "radius_km": 5, "categories": ["保洁"]}, headers=h)
    items = client.get(f"{API}/nearby", headers=h).json()["items"]
    assert [i["task_id"] for i in items] == [near_rich, near]               # 同一距离档里报酬高的在前
    assert items[0]["net_cents"] == 27600 and items[0]["distance_m"] < 500  # 扣 8% 服务费
    # 半径可以单独给（类目仍按「有空」里选的）；自己发的单永远不出现
    wide = client.get(f"{API}/nearby", params={"lat": HOME[0], "lng": HOME[1], "radius_km": 30}, headers=h).json()
    assert {i["title"] for i in wide["items"]} == {"两居室保洁", "三居室保洁", "很远的保洁"}
    # 带坐标时不需要「有空」：没开「有空」的人也能查，且没有类目限制
    other = client.get(f"{API}/nearby", params={"lat": HOME[0], "lng": HOME[1]}, headers=auth(requester)).json()
    assert [i["title"] for i in other["items"]] == ["我自己发的"]          # 他自己发的都不出现，只看得到 worker 发的那单


# ------------------------------------------------------------------ 顺路（GIG-103）
def test_along_ranks_by_added_detour(client, requester, worker):
    on_route = _task(requester["id"], "路中间的单", 31.2300, 121.5000)       # 正好在路上：几乎不绕
    slight = _task(requester["id"], "稍微绕一点", 31.2380, 121.5000)         # 偏北约 0.9 公里
    far_off = _task(requester["id"], "绕很远", 31.2800, 121.5000)            # 偏北约 5.6 公里
    h = auth(worker)
    home = client.post(f"{API}/places", json={"name": "家", "lat": HOME[0], "lng": HOME[1]}, headers=h).json()
    office = client.post(f"{API}/places", json={"name": "公司", "lat": OFFICE[0], "lng": OFFICE[1]}, headers=h).json()
    r = client.get(f"{API}/along", params={"from_place": home["id"], "to_place": office["id"], "max_detour_km": 2}, headers=h).json()
    ids = [i["task_id"] for i in r["items"]]
    assert ids == [on_route, slight] and far_off not in ids
    # 偏离路线 0.9 公里，多走的只有约 0.27 公里（2×√(2.85²+0.89²) − 2×2.85）；偏离 5.6 公里则多走约 6.5 公里
    assert r["items"][0]["detour_m"] < 50 and 200 < r["items"][1]["detour_m"] < 350 and r["to"] == "公司"
    # 用当前位置做起点
    cur = client.get(f"{API}/along", params={"from_lat": HOME[0], "from_lng": HOME[1], "to_place": office["id"]}, headers=h).json()
    assert cur["items"][0]["task_id"] == on_route
    assert client.get(f"{API}/along", params={"to_place": office["id"]}, headers=h).json()["detail"]["code"] == "gig_need_location"
    # 别人的地点：404
    assert client.get(f"{API}/along", params={"from_place": home["id"], "to_place": office["id"]}, headers=auth(requester)).status_code == 404
    assert client.delete(f"{API}/places/{home['id']}", headers=auth(requester)).status_code == 404


def test_places_are_coarse_and_capped(client, worker, monkeypatch):
    from app.modules.gig import router as gr

    h = auth(worker)
    p = client.post(f"{API}/places", json={"name": "家", "lat": 31.23456, "lng": 121.47891}, headers=h).json()
    assert (p["lat"], p["lng"]) == (31.23, 121.48)
    monkeypatch.setattr(gr, "MAX_PLACES", 1)
    r = client.post(f"{API}/places", json={"name": "公司", "lat": 31.2, "lng": 121.5}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "gig_places_full"
    assert client.get(f"{API}/places", headers=h).json() == [p]
    assert client.delete(f"{API}/places/{p['id']}", headers=h).json() == {"deleted": True}


# ------------------------------------------------------------------ 报价参考（GIG-104）
def test_quote_uses_closed_deals_and_shows_net(client, requester, worker):
    with SessionLocal() as db:
        for price in (10000, 20000, 30000):
            db.add(KnowledgeCard(category="保洁", city="上海", title="保洁", outcome="completed", price_actual_cents=price))
        db.commit()
    tid = _task(requester["id"], "两居室保洁", 31.23, 121.47, budget=25000)
    r = client.post(f"{API}/quote", json={"task_id": tid}, headers=auth(worker)).json()
    assert r["sample_size"] == 3 and r["p50_cents"] == 20000 and r["suggested_cents"] == 25000 and r["net_cents"] == 23000
    assert "比中位高 25%" in r["basis"][1] and "不是承诺价" in r["disclaimer"]
    low = _task(requester["id"], "低价保洁", 31.23, 121.47, budget=15000)
    r = client.post(f"{API}/quote", json={"task_id": low}, headers=auth(worker)).json()
    assert r["suggested_cents"] == 20000 and "比中位低 25%" in r["basis"][1]
    none = client.post(f"{API}/quote", json={"category": "宠物照看", "city": "上海"}, headers=auth(worker)).json()
    assert none["sample_size"] == 0 and none["suggested_cents"] is None and "还没有足够的成交数据" in none["basis"][0]
    # 别人的草稿与私有任务：404
    draft = _task(requester["id"], "草稿", 31.23, 121.47, status="draft")
    assert client.post(f"{API}/quote", json={"task_id": draft}, headers=auth(worker)).status_code == 404
    assert client.post(f"{API}/quote", json={"task_id": draft}, headers=auth(requester)).status_code == 200
    assert client.post(f"{API}/quote", json={}, headers=auth(worker)).json()["detail"]["code"] == "gig_quote_needs_subject"


# ------------------------------------------------------------------ 新单推送（GIG-105）
def test_new_task_pushes_to_available_people_in_range_with_a_cap(client, requester, worker):
    h = auth(worker)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1], "radius_km": 3, "categories": ["保洁"]}, headers=h)

    def publish(title, lat, lng, category="保洁"):
        tid = _task(requester["id"], title, lat, lng, category=category, status="draft")
        with SessionLocal() as db:
            from app.modules.task import service as tsvc

            tsvc.transition(db, db.get(Task, tid), "published")
            db.commit()

    publish("附近保洁", 31.2310, 121.4710)
    publish("附近维修", 31.2310, 121.4710, category="维修")                 # 类目不对
    publish("远处保洁", 31.4000, 121.4700)                                    # 超出半径
    with SessionLocal() as db:
        pushes = db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == svc.PUSH_TITLE).all()
        assert len(pushes) == 1 and "附近保洁" in pushes[0].body and "到手约" in pushes[0].body
        assert db.query(Notification).filter(Notification.user_id == requester["id"], Notification.title == svc.PUSH_TITLE).count() == 0
    for n in range(svc.MAX_PUSH_PER_WINDOW + 2):
        publish(f"保洁{n}", 31.2310, 121.4710)
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == svc.PUSH_TITLE).count() == svc.MAX_PUSH_PER_WINDOW
    # 关掉「有空」之后不再推
    client.delete(f"{API}/available", headers=h)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1]}, headers=h)
    client.delete(f"{API}/available", headers=h)
    publish("关掉之后", 31.2310, 121.4710)
    with SessionLocal() as db:
        assert db.query(Notification).filter(Notification.body.contains("关掉之后")).count() == 0


# ------------------------------------------------------------------ 接单者服务包（V150）
def test_gig_seed_is_valid():
    d, problems = schema.validate(GIG_SEED)
    assert d is not None and not problems, problems
    assert {"money", "share_personal"} <= set(d.assistants[0].human_gates)


def test_gig_assistant_uses_my_availability_and_deals(client, requester, worker):
    a, b = make_admin(client, "13900000301", "运营甲"), make_admin(client, "13900000302", "运营乙")
    pid = client.post("/api/v1/admin/packs", json={"definition": GIG_SEED}, headers=auth(a)).json()["id"]
    client.post(f"/api/v1/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"/api/v1/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200
    ask = "/api/v1/packs/gig-nearby/assistants/gig-assistant/ask"
    h = auth(worker)
    r = client.post(ask, json={"q": "附近有什么单"}, headers=h).json()
    assert any("还没打开「现在有空」" in c["snippet"] for c in r["citations"])
    _task(requester["id"], "两居室保洁", 31.2310, 121.4710, budget=15000)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1]}, headers=h)
    r = client.post(ask, json={"q": "附近有什么单"}, headers=h).json()
    tool = next(c for c in r["citations"] if c["kind"] == "tool")
    assert "两居室保洁" in tool["snippet"] and "到手约 ¥138" in tool["snippet"]
    q = client.post(ask, json={"q": "保洁一般报多少钱"}, headers=h).json()
    assert any(c["title"] == "「保洁」报价参考" for c in q["citations"])


# ------------------------------------------------------------------ 注销（GIG-109）
def test_erase_removes_location_data(client, worker):
    from app.modules.account.deletion import erase_personal_data

    h = auth(worker)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1]}, headers=h)
    client.post(f"{API}/places", json={"name": "家", "lat": HOME[0], "lng": HOME[1]}, headers=h)
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, worker["id"]))
        db.commit()
        assert db.get(GigAvailability, worker["id"]) is None and db.query(GigPlace).count() == 0


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape

    _task(requester["id"], "两居室保洁", 31.2300, 121.5000)
    h = auth(worker)
    on = client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1], "radius_km": 10}, headers=h).json()
    got = client.get(f"{API}/available", headers=h).json()
    home = client.post(f"{API}/places", json={"name": "家", "lat": HOME[0], "lng": HOME[1]}, headers=h).json()
    office = client.post(f"{API}/places", json={"name": "公司", "lat": OFFICE[0], "lng": OFFICE[1]}, headers=h).json()
    places = client.get(f"{API}/places", headers=h).json()
    near = client.get(f"{API}/nearby", headers=h).json()
    along = client.get(f"{API}/along", params={"from_place": home["id"], "to_place": office["id"]}, headers=h).json()
    quote = client.post(f"{API}/quote", json={"category": "保洁"}, headers=h).json()
    off = client.delete(f"{API}/available", headers=h).json()
    assert near["items"] and along["items"]
    for x in (on, got, off):
        _assert_shape(x, "GigAvailabilityView")
    first_place, first_near, first_along = places[0], near["items"][0], along["items"][0]
    _assert_shape(home, "GigPlaceRow")
    _assert_shape(first_place, "GigPlaceRow")
    _assert_shape(near, "GigNearby")
    _assert_shape(first_near, "GigTaskCard")
    _assert_shape(along, "GigAlong")
    _assert_shape(first_along, "GigTaskCard")
    _assert_shape(quote, "GigQuote")
    _assert_inline_shape(client.delete(f"{API}/places/{office['id']}", headers=h).json(), "deleteGigPlace")
