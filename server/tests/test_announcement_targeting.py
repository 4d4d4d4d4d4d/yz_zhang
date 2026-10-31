"""NTF-066 公告按城市 / 人群定向，NTF-067 阅读率（159 号 spec）。

151 号的公告只能发全体或仅已实名：上海的线下活动通知发到了全国，「接单规则调整」发给了只发单的人。
发出去以后也不知道有多少人看了。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit
from app.modules.task.models import Application, Task
from tests.conftest import auth, make_admin, register

API = "/api/v1"
URL = f"{API}/admin/announcements"


def _ops(client):
    a = make_admin(client, "13800320001", "运营")
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = ["ops"]
        db.commit()
    return a


def _inbox(client, user):
    rows = client.get(f"{API}/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n for n in items if n["category"] == "announcement"]


def _people(client):
    sh = register(client, "13800320011", "上海发单的")
    bj = register(client, "13800320012", "北京接单的")
    old = register(client, "13800320013", "很久没来的")
    with SessionLocal() as db:
        db.get(User, sh["id"]).city = "上海"
        db.get(User, bj["id"]).city = "北京"
        db.get(User, old["id"]).city = "上海"
        t = Task(creator_id=sh["id"], title="搬家", description="", category="跑腿", budget_cents=10000,
                 status="published", visibility="public")
        db.add(t)
        db.flush()
        db.add(Application(task_id=t.id, applicant_id=bj["id"]))
        old_task = Task(creator_id=old["id"], title="旧单", description="", category="跑腿", budget_cents=10000,
                        status="published", visibility="public", created_at=utcnow() - timedelta(days=400))
        db.add(old_task)
        db.commit()
    return sh, bj, old


def test_city_and_audience_narrow_the_preview_and_the_send(client):
    ops = _ops(client)
    sh, bj, old = _people(client)
    p = client.post(f"{URL}/preview", json={"title": "上海线下见面会", "body": "周六", "city": "上海"}, headers=auth(ops)).json()
    assert p["audience"] == 2 and p["city"] == "上海" and p["audience_kind"] == "all"
    pub = client.post(f"{URL}/preview", json={"title": "发单技巧", "body": "x", "audience": "publishers"}, headers=auth(ops)).json()
    assert pub["audience"] == 1, "只算近 180 天发过单的"
    wk = client.post(f"{URL}/preview", json={"title": "接单规则调整", "body": "x", "audience": "workers"}, headers=auth(ops)).json()
    assert wk["audience"] == 1
    none = client.post(f"{URL}/preview", json={"title": "火星见面会", "body": "x", "city": "火星"}, headers=auth(ops)).json()
    assert none["audience"] == 0 and any("一个人都发不到" in w for w in none["warnings"])
    bad = client.post(f"{URL}/preview", json={"title": "测试", "audience": "vip"}, headers=auth(ops))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "bad_audience"
    r = client.post(URL, json={"title": "上海发单的人看过来", "body": "x", "city": "上海", "audience": "publishers"}, headers=auth(ops)).json()
    assert r["delivered"] == 1
    assert [n["title"] for n in _inbox(client, sh)] == ["上海发单的人看过来"]
    assert _inbox(client, bj) == [] and _inbox(client, old) == []
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "announcement_send").one()
        assert "上海" in a.detail and "发过单" in a.detail


def test_read_rate_counts_people_who_opened_it(client):
    ops = _ops(client)
    sh, bj, _old = _people(client)
    r = client.post(URL, json={"title": "全站通知", "body": "x"}, headers=auth(ops)).json()
    n = next(x for x in _inbox(client, sh) if x["title"] == "全站通知")
    assert client.post(f"{API}/notifications/{n['id']}/read", headers=auth(sh)).status_code == 200
    row = next(x for x in client.get(URL, headers=auth(ops)).json() if x["id"] == r["id"])
    assert row["read"] == 1 and row["read_rate"] == round(1 / r["delivered"], 3)
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "AnnouncementRow")
    sched = client.post(URL, json={"title": "定时的", "body": "x",
                                   "scheduled_at": (utcnow() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                        headers=auth(ops)).json()
    srow = next(x for x in client.get(URL, headers=auth(ops)).json() if x["id"] == sched["id"])
    assert srow["read"] == 0 and srow["read_rate"] is None, "还没发出的没有阅读率"


def test_scheduled_targeting_is_kept_until_it_goes_out(client):
    from app.modules.admin.models import Announcement
    from tests.conftest import JOB_HEADERS

    ops = _ops(client)
    sh, bj, _old = _people(client)
    r = client.post(URL, json={"title": "北京接单的人看过来", "body": "x", "city": "北京", "audience": "workers",
                               "scheduled_at": (utcnow() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")},
                    headers=auth(ops)).json()
    with SessionLocal() as db:
        db.get(Announcement, r["id"]).scheduled_at = utcnow() - timedelta(minutes=1)
        db.commit()
    client.post(f"{API}/admin/jobs/send-scheduled-announcements", headers=JOB_HEADERS)
    assert [n["title"] for n in _inbox(client, bj)] == ["北京接单的人看过来"] and _inbox(client, sh) == []
