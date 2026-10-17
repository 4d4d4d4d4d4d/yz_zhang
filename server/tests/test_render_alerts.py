"""APP-097 有一页坏的人多了，提醒运营（186 号 spec，V214）。

184 号让运营能在后台看到哪页常坏，但得有人去看。每小时数一次：同一端同一页近 24 小时坏过的不同登录用户
到阈值（默认 5 人）就给运营发站内信；同一页 24 小时内只提醒一次；没登录的上报不算人数（页面名可以编造）。
"""
from datetime import timedelta

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.analytics.models import AnalyticsEvent
from app.modules.notification.models import Notification
from tests.conftest import JOB_HEADERS, auth, make_admin, register

API = "/api/v1"
JOB = f"{API}/analytics/jobs/render-alerts"


def _people(client, n, start=0):
    return [register(client, f"139000310{start + i:02d}", f"用户{start + i}") for i in range(n)]


def _break(client, users, page="/wallet", platform="web", kind="TypeError"):
    for u in users:
        r = client.post(f"{API}/client-errors", json={"platform": platform, "page": page, "kind": kind}, headers=auth(u))
        assert r.status_code == 201


def _admin(client, phone, name, roles):
    a = make_admin(client, phone, name)
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = roles
        db.commit()
    return a


def _inbox(uid):
    with SessionLocal() as db:
        return [(n.title, n.body) for n in db.query(Notification).filter(Notification.user_id == uid, Notification.title == "有一页坏的人多了")]


def test_ops_is_told_once_when_enough_people_hit_the_same_page(client):
    ops = _admin(client, "13900031901", "运营", ["ops"])
    support = _admin(client, "13900031902", "客服", ["support"])
    users = _people(client, 5)
    _break(client, users[:4])
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"alerted": []}, "4 人还不到阈值"
    _break(client, users[4:], kind="RangeError")      # 第 5 个人撞上的是另一类错：同一页，人数合起来数
    out = client.post(JOB, headers=JOB_HEADERS).json()["alerted"]
    assert out == [{"platform": "web", "page": "/wallet", "people": 5, "notified": 1}]
    (title, body), = _inbox(ops["id"])
    assert "网页「/wallet」近 24 小时有 5 位用户遇到页面出错（RangeError、TypeError）" in body
    assert "去管理后台「页面出错」" in body, "说清怎么办"
    assert _inbox(support["id"]) == [], "只提醒运营，不打扰客服"
    _break(client, _people(client, 3, start=5))
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"alerted": []}, "同一页 24 小时内只提醒一次"
    assert len(_inbox(ops["id"])) == 1


def test_people_are_counted_per_platform_and_page_and_anonymous_reports_do_not_count(client, monkeypatch):
    monkeypatch.setattr(settings, "RENDER_ALERT_PEOPLE", 2)
    ops = _admin(client, "13900031903", "运营", ["ops"])
    a, b = _people(client, 2)
    _break(client, [a], page="/wallet")
    _break(client, [b], page="/workbench")             # 不同页
    _break(client, [b], page="/wallet", platform="app")  # 不同端
    for _ in range(3):                                  # 没登录的上报：页面名可以随便编，不算人
        client.post(f"{API}/client-errors", json={"platform": "web", "page": "/wallet", "kind": "TypeError"})
    _break(client, [a], kind="RangeError")              # 同一个人换一类错：仍是一个人
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"alerted": []}
    _break(client, [b], page="/wallet")
    assert [r["page"] for r in client.post(JOB, headers=JOB_HEADERS).json()["alerted"]] == ["/wallet"]
    assert len(_inbox(ops["id"])) == 1


def test_old_reports_fall_out_of_the_window_and_a_new_wave_alerts_again(client, monkeypatch):
    monkeypatch.setattr(settings, "RENDER_ALERT_PEOPLE", 2)
    ops = _admin(client, "13900031904", "运营", ["ops"])
    _break(client, _people(client, 2))
    assert len(client.post(JOB, headers=JOB_HEADERS).json()["alerted"]) == 1
    with SessionLocal() as db:   # 一天多以前的上报与提醒都不算了
        for row in db.query(AnalyticsEvent).filter(AnalyticsEvent.name.like("render_%")):
            row.created_at = utcnow() - timedelta(hours=25)
        db.commit()
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"alerted": []}, "旧的上报不再算人"
    _break(client, _people(client, 2, start=2))
    assert len(client.post(JOB, headers=JOB_HEADERS).json()["alerted"]) == 1, "新的一波照样提醒"
    assert len(_inbox(ops["id"])) == 2


def test_without_a_dedicated_ops_admin_the_super_admin_is_told(client, monkeypatch):
    monkeypatch.setattr(settings, "RENDER_ALERT_PEOPLE", 1)
    boss = _admin(client, "13900031905", "超管", ["super"])
    support = _admin(client, "13900031906", "客服", ["support"])
    banned = _admin(client, "13900031907", "停用的运营", ["ops"])
    with SessionLocal() as db:
        db.get(User, banned["id"]).is_banned = True
        db.commit()
    _break(client, _people(client, 1))
    assert client.post(JOB, headers=JOB_HEADERS).json()["alerted"][0]["notified"] == 1
    assert len(_inbox(boss["id"])) == 1 and _inbox(support["id"]) == [] and _inbox(banned["id"]) == []


def test_the_job_needs_the_job_token_and_does_not_show_up_in_the_render_error_summary(client, monkeypatch):
    monkeypatch.setattr(settings, "RENDER_ALERT_PEOPLE", 1)
    assert client.post(JOB).status_code in (401, 403)
    ops = _admin(client, "13900031908", "运营", ["ops"])
    _break(client, _people(client, 1))
    client.post(JOB, headers=JOB_HEADERS)
    rows = client.get(f"{API}/admin/client-errors", headers=auth(ops)).json()
    assert [(r["page"], r["count"]) for r in rows] == [("/wallet", 1)], "「已提醒」的记号不算一次页面出错"


def test_the_summary_says_which_pages_ops_was_told_about_and_the_threshold(client, monkeypatch):
    """APP-101（V217）后台表上标出这一页提醒过运营没有，并给出阈值。"""
    monkeypatch.setattr(settings, "RENDER_ALERT_PEOPLE", 2)
    ops = _admin(client, "13900031909", "运营", ["ops"])
    _break(client, _people(client, 2), page="/wallet")
    _break(client, _people(client, 1, start=2), page="/workbench")
    client.post(JOB, headers=JOB_HEADERS)
    rows = {r["page"]: r for r in client.get(f"{API}/admin/client-errors", headers=auth(ops)).json()}
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows["/wallet"], "ClientErrorRow")
    assert rows["/wallet"]["alerted_at"] is not None and rows["/workbench"]["alerted_at"] is None
    assert {r["alert_people"] for r in rows.values()} == {2}
    with SessionLocal() as db:   # 提醒在查询窗口之外：不再标
        for row in db.query(AnalyticsEvent).filter(AnalyticsEvent.name.like("render_alerted:%")):
            row.created_at = utcnow() - timedelta(days=8)
        db.commit()
    rows = {r["page"]: r for r in client.get(f"{API}/admin/client-errors", headers=auth(ops)).json()}
    assert rows["/wallet"]["alerted_at"] is None
