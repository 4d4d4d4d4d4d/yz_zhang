"""SCN-192 发单人对一次上门回报确认或提出异议（317 号 spec，V344）。

上门收废品称了多少、上门做了什么，以前只有接单人的一面之词：回报交上来，发单人心里有数却没地方「签个字」，
到验收时才翻旧账。现在每一次回报发单人可以当场确认（留个凭据），或写清哪里不对提出异议（通知接单人）；
两者互斥，后一次表态盖过前一次。不碰钱、不等于验收。
"""
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth, register
from tests.test_task_visits import API, _visit_task


def _two_visits(client, requester, worker):
    t = _visit_task(client, requester, worker)
    a = client.post(f"{API}/{t['id']}/visits", json={"done": ["喂食"], "note": "纸箱 12.4 斤，见秤面照片"},
                    headers=auth(worker)).json()
    b = client.post(f"{API}/{t['id']}/visits", json={"done": ["换水"]}, headers=auth(worker)).json()
    return t, a["id"], b["id"]


def test_the_poster_confirms_or_objects_and_the_latest_word_wins(client, requester, worker):
    t, a, b = _two_visits(client, requester, worker)
    v = client.post(f"{API}/{t['id']}/visits/{a}/confirm", headers=auth(requester))
    assert v.status_code == 200, v.text
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v.json(), "TaskVisits")
    rows = {x["id"]: x for x in v.json()["visits"]}
    assert rows[a]["confirmed_at"] and "objection" not in rows[a]
    assert "confirmed_at" not in rows[b] and "objection" not in rows[b], "没表态的不出这两个字段"
    _assert_shape(rows[a], "TaskVisit")

    o = client.post(f"{API}/{t['id']}/visits/{a}/object", json={"reason": " 秤面照片看不清，实际不到 12 斤 "},
                    headers=auth(requester)).json()
    row = {x["id"]: x for x in o["visits"]}[a]
    assert row["objection"] == "秤面照片看不清，实际不到 12 斤" and "confirmed_at" not in row, "异议撤回之前的确认"
    with SessionLocal() as db:
        n = db.query(Notification).filter(Notification.user_id == worker["id"],
                                          Notification.title == "发单人对一次上门回报有异议").one()
        assert "实际不到 12 斤" in n.body
    again = client.post(f"{API}/{t['id']}/visits/{a}/confirm", headers=auth(requester)).json()
    row = {x["id"]: x for x in again["visits"]}[a]
    assert row["confirmed_at"] and "objection" not in row, "再确认就撤回异议"
    listed = {x["id"]: x for x in client.get(f"{API}/{t['id']}/visits", headers=auth(worker)).json()["visits"]}
    assert listed[a]["confirmed_at"], "接单人也看得到"


def test_only_the_poster_of_this_task_and_only_visit_reports(client, requester, worker):
    t, a, _b = _two_visits(client, requester, worker)
    r = client.post(f"{API}/{t['id']}/visits/{a}/confirm", headers=auth(worker))
    assert r.status_code == 403, "接单人不能替发单人确认"
    outsider = register(client, "13800344001", "路人")
    assert client.post(f"{API}/{t['id']}/visits/{a}/object", json={"reason": "乱说的"}, headers=auth(outsider)).status_code == 403
    assert client.post(f"{API}/{t['id']}/visits/{a}/object", json={"reason": "x"}, headers=auth(requester)).status_code == 422, "异议要写清"
    other, oa, _ = _two_visits(client, requester, worker)
    assert client.post(f"{API}/{t['id']}/visits/{oa}/confirm", headers=auth(requester)).status_code == 404, "别的任务的回报不认"
    client.post(f"{API}/{t['id']}/progress", json={"content": "普通进展"}, headers=auth(worker))
    nid = next(x["id"] for x in client.get(f"{API}/{t['id']}/progress", headers=auth(requester)).json() if x["kind"] != "visit")
    assert client.post(f"{API}/{t['id']}/visits/{nid}/confirm", headers=auth(requester)).status_code == 404, "不是上门回报的不认"
    assert client.post(f"{API}/{t['id']}/visits/999999/confirm", headers=auth(requester)).status_code == 404


def test_the_scrap_template_asks_for_a_photo_of_the_scale_and_a_confirmation():
    from app.modules.packs import schema
    from tests.test_v286_packs import _load

    d, _ = schema.validate(_load("scrap-recycling"))
    t = d.task_templates[0]
    assert "秤面读数拍照" in t.visit_checklist and "对得上" in t.description
