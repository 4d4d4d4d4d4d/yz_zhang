"""NTF-072 公告阅读率按发出后的时间看（261 号 spec，V288）。

159 号的阅读率只有一个总数：看不出是一小时内就有人点开，还是三天后才陆续有人看到——
后者说明推送没起作用、要换时间段或换标题。现在记下第一次点开的时间，按 1 小时 / 1 天 / 3 天 / 7 天看累计。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import Announcement
from app.modules.notification.models import Notification
from tests.conftest import auth, make_admin, register
from tests.test_announcements import URL, _inbox, _ops

API = "/api/v1"


def test_mark_read_records_the_first_open_time_only(client):
    ops = _ops(client, "13800350001")
    u = register(client, "13800350011", "甲")
    client.post(URL, json={"title": "规则调整", "body": "详见帮助中心"}, headers=auth(ops))
    nid = _inbox(client, u)[0]["id"]
    client.post(f"{API}/notifications/{nid}/read", headers=auth(u))
    with SessionLocal() as db:
        first = db.get(Notification, nid).read_at
        assert first is not None
        db.get(Notification, nid).read_at = first - timedelta(hours=1)
        db.commit()
    client.post(f"{API}/notifications/{nid}/read", headers=auth(u))
    with SessionLocal() as db:
        assert db.get(Notification, nid).read_at == first - timedelta(hours=1), "再点一次不改第一次点开的时间"
    client.post(URL, json={"title": "第二条", "body": ""}, headers=auth(ops))
    assert client.post(f"{API}/notifications/read-all", headers=auth(u)).status_code == 200
    with SessionLocal() as db:
        assert all(n.read_at is not None for n in db.query(Notification).filter(Notification.user_id == u["id"]))


def test_curve_counts_cumulative_opens_by_time_after_sending(client):
    ops = _ops(client, "13800350002")
    us = [register(client, f"1380035002{i}", f"用户{i}") for i in range(4)]
    a = client.post(URL, json={"title": "春节客服安排", "body": "除夕到初三值班"}, headers=auth(ops)).json()
    sent = utcnow() - timedelta(days=2)
    with SessionLocal() as db:
        db.get(Announcement, a["id"]).sent_at = sent
        db.get(Announcement, a["id"]).delivered = 10    # 比率的分母是送达人数（与列表同口径），不是还留着的通知条数
        rows = {n.user_id: n for n in db.query(Notification).filter(Notification.announcement_id == a["id"])}
        for u, after in zip(us[:3], (timedelta(minutes=30), timedelta(hours=5), None)):
            rows[u["id"]].is_read = True
            rows[u["id"]].read_at = sent + after if after is not None else None      # 第三个：老版本时点开的，时间不详
        db.commit()
    c = client.get(f"{URL}/{a['id']}/read-curve", headers=auth(ops)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(c, "AnnouncementReadCurve")
    assert (c["read"], c["untimed"], c["delivered"]) == (3, 1, 10)
    assert [(p["label"], p["read"], p["reached"]) for p in c["points"]] == [
        ("1 小时", 1, True), ("1 天", 2, True), ("3 天", 2, False), ("7 天", 2, False)]
    assert c["points"][0]["read_rate"] == 0.1 and c["points"][1]["read_rate"] == 0.2
    assert "时间不详" in c["note"]
    total = client.get(URL, headers=auth(ops)).json()[0]
    assert total["read"] == c["read"], "与列表里的总阅读数同一口径"


def test_curve_for_unsent_missing_and_roles(client):
    ops = _ops(client, "13800350003")
    later = (utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = client.post(URL, json={"title": "定时", "body": "", "scheduled_at": later}, headers=auth(ops)).json()
    c = client.get(f"{URL}/{s['id']}/read-curve", headers=auth(ops)).json()
    assert c["points"] == [] and c["note"] == "这条公告还没发出"
    assert client.get(f"{URL}/999999/read-curve", headers=auth(ops)).status_code == 404
    fin = make_admin(client, "13800350004", "财务")
    with SessionLocal() as db:
        db.get(User, fin["id"]).admin_roles = ["finance"]
        db.commit()
    assert client.get(f"{URL}/{s['id']}/read-curve", headers=auth(fin)).status_code == 403


def test_ntf073_opened_via_push_is_counted_separately(client):
    """NTF-073（268 号 spec）从推送点进来的单独计数：推送带公告 id，App 点进来报一次；只记第一次从哪里点开。"""
    from app.core.events import OutboxEvent

    ops = _ops(client, "13800350005")
    us = [register(client, f"1380035006{i}", f"用户{i}") for i in range(3)]
    a = client.post(URL, json={"title": "活动通知", "body": "周末有活动"}, headers=auth(ops)).json()
    import json

    from app.modules.notification.service import notify

    with SessionLocal() as db:
        notify(db, us[0]["id"], "system", "不是公告的通知", "")
        db.commit()
    with SessionLocal() as db:
        ev = [json.loads(e.payload) for e in db.query(OutboxEvent).filter(OutboxEvent.event == "notification.created")]
        mine = [p for p in ev if p.get("user_id") == us[0]["id"] and p.get("category") == "announcement"]
        assert mine and mine[-1]["announcement_id"] == a["id"], "公告的推送带上公告 id"
        others = [p for p in ev if p.get("category") != "announcement"]
        assert others and all("announcement_id" not in p for p in others), "别的通知不多字段"
    r = client.post(f"{API}/notifications/push-opened", json={"announcement_id": a["id"]}, headers=auth(us[0]))
    assert r.status_code == 200 and r.json()["recorded"] is True
    assert client.post(f"{API}/notifications/push-opened", json={"announcement_id": a["id"]},
                       headers=auth(us[0])).json()["recorded"] is False, "再点一次不改第一次"
    nid = _inbox(client, us[1])[0]["id"]
    client.post(f"{API}/notifications/{nid}/read", params={"via": "center"}, headers=auth(us[1]))
    assert client.post(f"{API}/notifications/push-opened", json={"announcement_id": a["id"]},
                       headers=auth(us[1])).json()["recorded"] is False, "已经在通知中心点开过：不算推送带来的"
    nid2 = _inbox(client, us[2])[0]["id"]
    assert client.post(f"{API}/notifications/{nid2}/read", params={"via": "bad"}, headers=auth(us[2])).status_code == 422
    client.post(f"{API}/notifications/{nid2}/read", params={"via": "push"}, headers=auth(us[2]))
    with SessionLocal() as db:
        vias = {n.user_id: n.read_via for n in db.query(Notification).filter(Notification.announcement_id == a["id"])}
    assert (vias[us[0]["id"]], vias[us[1]["id"]], vias[us[2]["id"]]) == ("push", "center", "push")
    c = client.get(f"{URL}/{a['id']}/read-curve", headers=auth(ops)).json()
    assert (c["read"], c["read_via_push"]) == (3, 2)
    other = register(client, "13800350069", "外人")          # 公告发出之后才注册：没收到
    assert client.post(f"{API}/notifications/push-opened", json={"announcement_id": a["id"]},
                       headers=auth(other)).status_code == 404, "没收到这条公告的人报不了"
