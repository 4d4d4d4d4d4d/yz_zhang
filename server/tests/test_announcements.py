"""NTF-064 全站公告：预览、定时与撤回（151 号 spec）。

此前公告按下就发、发错了收不回来，只能再发一条更正——两条互相矛盾的通知并排躺在每个人的通知中心里。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit, Announcement
from tests.conftest import JOB_HEADERS, auth, make_admin, register, verify_user

API = "/api/v1"
URL = f"{API}/admin/announcements"


def _ops(client, phone="13800260001"):
    a = make_admin(client, phone, "运营")
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = ["ops"]
        db.commit()
    return a


def _inbox(client, user):
    rows = client.get(f"{API}/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n for n in items if n["category"] == "announcement"]


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_preview_counts_audience_without_sending(client):
    ops = _ops(client)
    u1 = register(client, "13800260011", "甲")
    register(client, "13800260012", "乙")
    r = client.post(f"{URL}/preview", json={"title": "提现规则调整：本周起提现到账更快，手续费不变，详情见帮助中心", "body": ""}, headers=auth(ops))
    assert r.status_code == 200, r.text
    p = r.json()
    with SessionLocal() as db:
        everyone = db.query(User).filter(User.is_deleted.is_(False), User.is_banned.is_(False)).count()
    assert p["audience"] == everyone
    assert any("锁屏" in w for w in p["warnings"]) and any("正文是空的" in w for w in p["warnings"])
    assert any("已实名" in w for w in p["warnings"]), "资金类公告没提醒是否只发已实名用户"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(p, "AnnouncementPreview")
    assert _inbox(client, u1) == [], "预览不该发出去"
    with SessionLocal() as db:
        assert db.query(Announcement).count() == 0
    v = client.post(f"{URL}/preview", json={"title": "只给实名", "body": "x", "verified_only": True}, headers=auth(ops)).json()
    assert v["audience"] < everyone


def test_immediate_send_keeps_old_response_and_is_recorded_and_audited(client):
    ops = _ops(client)
    u = register(client, "13800260021", "甲")
    r = client.post(URL, json={"title": "春节客服安排", "body": "除夕到初三值班"}, headers=auth(ops)).json()
    assert r["delivered"] >= 1 and r["status"] == "sent" and r["scheduled_at"] is None
    assert [n["title"] for n in _inbox(client, u)] == ["春节客服安排"]
    rows = client.get(URL, headers=auth(ops)).json()
    assert rows[0]["id"] == r["id"] and rows[0]["delivered"] == r["delivered"] and rows[0]["created_by"] == ops["id"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows[0], "AnnouncementRow")
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "announcement_send").one()
        assert a.admin_id == ops["id"] and "送达" in a.detail


def test_scheduled_announcement_waits_then_the_job_sends_it_once(client):
    ops = _ops(client)
    u = register(client, "13800260031", "甲")
    at = utcnow() + timedelta(hours=2)
    r = client.post(URL, json={"title": "系统维护通知", "body": "今晚 2 点", "scheduled_at": _iso(at)}, headers=auth(ops)).json()
    assert r["status"] == "scheduled" and r["delivered"] == 0 and r["scheduled_at"]
    job = f"{API}/admin/jobs/send-scheduled-announcements"
    assert client.post(job, headers=JOB_HEADERS).json()["sent"] == []
    assert _inbox(client, u) == []
    with SessionLocal() as db:
        db.get(Announcement, r["id"]).scheduled_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.post(job, headers=JOB_HEADERS).json()["sent"] == [r["id"]]
    assert client.post(job, headers=JOB_HEADERS).json()["sent"] == []
    assert [n["title"] for n in _inbox(client, u)] == ["系统维护通知"]
    row = [x for x in client.get(URL, headers=auth(ops)).json() if x["id"] == r["id"]][0]
    assert row["status"] == "sent" and row["delivered"] >= 1 and row["sent_at"]


def test_schedule_must_be_in_the_future_and_within_30_days(client):
    ops = _ops(client)
    past = client.post(URL, json={"title": "过去", "scheduled_at": _iso(utcnow() - timedelta(minutes=5))}, headers=auth(ops))
    assert past.status_code == 400 and past.json()["detail"]["code"] == "schedule_in_past"
    far = client.post(URL, json={"title": "太远", "scheduled_at": _iso(utcnow() + timedelta(days=31))}, headers=auth(ops))
    assert far.status_code == 400 and far.json()["detail"]["code"] == "schedule_too_far"


def test_cancel_a_scheduled_one_and_it_never_goes_out(client):
    ops = _ops(client)
    u = register(client, "13800260041", "甲")
    r = client.post(URL, json={"title": "发错时间了", "scheduled_at": _iso(utcnow() + timedelta(hours=1))}, headers=auth(ops)).json()
    c = client.post(f"{URL}/{r['id']}/cancel", json={"reason": "改到下周"}, headers=auth(ops))
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and c.json()["close_reason"] == "改到下周"
    with SessionLocal() as db:
        db.get(Announcement, r["id"]).scheduled_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.post(f"{API}/admin/jobs/send-scheduled-announcements", headers=JOB_HEADERS).json()["sent"] == []
    assert _inbox(client, u) == []
    again = client.post(f"{URL}/{r['id']}/cancel", json={}, headers=auth(ops))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "announcement_not_scheduled"


def test_revoke_rewrites_delivered_notifications_with_the_reason(client):
    ops = _ops(client)
    u = register(client, "13800260051", "甲")
    other = register(client, "13800260052", "乙")
    r = client.post(URL, json={"title": "平台佣金下调到 1%", "body": "即日起"}, headers=auth(ops)).json()
    # 同一个人别的通知不受影响
    client.post(URL, json={"title": "另一条公告", "body": "保留"}, headers=auth(ops))
    no_reason = client.post(f"{URL}/{r['id']}/revoke", json={"reason": " "}, headers=auth(ops))
    assert no_reason.status_code == 400 and no_reason.json()["detail"]["code"] == "revoke_reason_required"
    v = client.post(f"{URL}/{r['id']}/revoke", json={"reason": "数字写错了，实际是 3%"}, headers=auth(ops))
    assert v.status_code == 200, v.text
    assert v.json()["status"] == "revoked" and v.json()["notifications_updated"] == r["delivered"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(v.json(), "AnnouncementRevoked")
    for who in (u, other):
        titles = {n["title"]: n["body"] for n in _inbox(client, who)}
        assert titles["【已撤回】平台佣金下调到 1%"] == "这条公告已撤回：数字写错了，实际是 3%"
        assert "平台佣金下调到 1%" not in titles and titles["另一条公告"] == "保留"
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "announcement_revoke").one()
        assert "数字写错了" in a.detail
    twice = client.post(f"{URL}/{r['id']}/revoke", json={"reason": "再撤一次"}, headers=auth(ops))
    assert twice.status_code == 409 and twice.json()["detail"]["code"] == "announcement_not_sent"


def test_only_ops_can_manage_announcements(client):
    fin = make_admin(client, "13800260061", "财务")
    with SessionLocal() as db:
        db.get(User, fin["id"]).admin_roles = ["finance"]
        db.commit()
    for method, url, body in [("post", f"{URL}/preview", {"title": "测试"}), ("get", URL, None),
                              ("post", f"{URL}/1/cancel", {}), ("post", f"{URL}/1/revoke", {"reason": "测试"})]:
        r = getattr(client, method)(url, headers=auth(fin), **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (url, r.status_code)
    u = register(client, "13800260062", "甲")
    verify_user(client, u)
    assert client.post(f"{URL}/preview", json={"title": "测试"}, headers=auth(u)).status_code == 403
