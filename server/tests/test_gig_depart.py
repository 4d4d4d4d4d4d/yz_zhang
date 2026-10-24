"""SCN-134 顺路单可以设出发时间（203 号 spec，V227）。

V220 起顺路单只按「现在 → 有空截止」筛名额：明早上班想顺路带一单，今晚看不了（要么看到一堆三天后的，要么开着「有空」只剩眼下的）。
现在可以带出发时间（北京时间）：只看出发后几小时内对得上的名额；不带时行为不变。
"""
from datetime import timedelta

from tests.conftest import auth
from tests.test_client_shape_alignment import _assert_shape
from tests.test_gig import HOME
from tests.test_gig_shifts import _slots, _today

API = "/api/v1/gig"


def _along(client, h, place, **params):
    return client.get(f"{API}/along", params={"from_lat": HOME[0], "from_lng": HOME[1], "to_place": place["id"], **params}, headers=h)


def test_depart_time_picks_slots_that_fit_after_departure(client, requester, worker):
    ids = _slots(requester)
    h = auth(worker)
    client.put(f"{API}/available", json={"lat": HOME[0], "lng": HOME[1], "radius_km": 5, "hours": 2}, headers=h)
    place = client.post(f"{API}/places", json={"name": "公司", "lat": 31.2300, "lng": 121.4900}, headers=h).json()
    day3 = (_today() + timedelta(days=3)).isoformat()
    r = _along(client, h, place, depart_at=f"{day3}T08:30", within_hours=2)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {x["task_id"] for x in body["items"]} == {ids["later"], ids["plain"]}, "按出发时间筛，不再按「现在有空」那一段"
    assert (body["depart_at"], body["within_hours"]) == (f"{day3}T08:30", 2)
    _assert_shape(body, "GigAlong")
    early = _along(client, h, place, depart_at=f"{day3}T05:00", within_hours=3).json()
    assert {x["task_id"] for x in early["items"]} == {ids["plain"]}, "05:00 出发 3 小时内到不了 09:00 开始的名额"
    wide = _along(client, h, place, depart_at=f"{day3}T05:00", within_hours=5).json()
    assert ids["later"] in {x["task_id"] for x in wide["items"]}, "放宽到 5 小时就够得着"
    plain = _along(client, h, place).json()
    assert {x["task_id"] for x in plain["items"]} == {ids["today"], ids["plain"]}, "不带出发时间行为不变"
    assert (plain["depart_at"], plain["within_hours"]) == (None, None)


def test_depart_time_with_offset_and_the_rules(client, requester, worker):
    ids = _slots(requester)
    h = auth(worker)
    place = client.post(f"{API}/places", json={"name": "公司", "lat": 31.2300, "lng": 121.4900}, headers=h).json()
    day3 = (_today() + timedelta(days=3)).isoformat()
    utc = _along(client, h, place, depart_at=f"{day3}T01:30+00:00", within_hours=1).json()
    assert ids["later"] in {x["task_id"] for x in utc["items"]}, "带时区的按时区换算（UTC 01:30 = 北京 09:30）"
    for value, code in [("明早八点", "gig_depart_invalid"), ((_today() - timedelta(days=1)).isoformat() + "T09:00", "gig_depart_past"),
                        ((_today() + timedelta(days=9)).isoformat() + "T09:00", "gig_depart_too_far")]:
        r = _along(client, h, place, depart_at=value)
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, value
    assert _along(client, h, place, depart_at=f"{day3}T08:30", within_hours=13).status_code == 422
