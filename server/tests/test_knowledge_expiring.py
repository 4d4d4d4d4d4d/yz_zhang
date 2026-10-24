"""SCN-161 防诈骗知识按通报定期更新（289 号 spec，V316）。

骗术常换：防诈骗那条知识写了有效期（按季度复核），到期前 30 天就进场景雷达，让运营赶在过期前
对照最新通报更新；已过期的照旧标「已过有效期」（V148），两句话分开说。
"""
from datetime import date, timedelta

from app.modules.packs import service
from tests.conftest import auth
from tests.test_packs import SEED, _def, _publish
from tests.test_v286_packs import _load

API = "/api/v1"


def _radar_evidence(client, a):
    radar = client.get(f"{API}/admin/packs/radar", headers=auth(a)).json()
    return [x["evidence"] for x in radar if x["source"] == "pack_gap" and x["key"] == "collab-basics"]


def test_knowledge_due_within_30_days_is_on_the_radar_before_it_expires(client, admins):
    today = date.today()
    ks = SEED["knowledge"]
    due = {**ks[0], "valid_until": (today + timedelta(days=service.EXPIRING_DAYS)).isoformat()}
    later = {**ks[1], "valid_until": (today + timedelta(days=service.EXPIRING_DAYS + 1)).isoformat()}
    gone = {**ks[2], "valid_until": (today - timedelta(days=1)).isoformat()}
    _publish(client, admins, _def(knowledge=[due, later, gone, *ks[3:]]))
    ev = _radar_evidence(client, admins[0])
    assert len(ev) == 1, ev
    assert f"1 条知识 30 天内到期：{due['title']}" in ev[0] and "对照最新通报或法规更新" in ev[0]
    assert later["title"] not in ev[0], "31 天后才到期的不提"
    assert f"1 条知识已过有效期：{gone['title']}" in ev[0], "过期的照旧单独说"
    assert ev[0].count(gone["title"]) == 1, "已过期的不再算「即将到期」"


def test_no_due_knowledge_means_no_signal(client, admins):
    far = [{**k, "valid_until": (date.today() + timedelta(days=200)).isoformat()} for k in SEED["knowledge"]]
    _publish(client, admins, _def(knowledge=far))
    assert _radar_evidence(client, admins[0]) == []


def test_anti_fraud_knowledge_carries_a_review_date_and_says_where_to_check():
    k = {x["key"]: x for x in _load("elder-phone-teaching")["knowledge"]}["anti-fraud"]
    assert k["valid_until"], "防诈骗知识要写有效期（按季度复核）"
    assert "最新通报" in k["source"] and "96110" in k["body"]


# ---------------------------------------------------------------- SCN-163（292 号 spec，V319）
JOB = f"{API}/packs/jobs/remind-expiring"


def _reminders():
    from app.core.db import SessionLocal
    from app.modules.notification.models import Notification

    with SessionLocal() as db:
        return [(n.user_id, n.body) for n in db.query(Notification).filter(Notification.title.like("场景包「%」有知识快到期了"))]


def test_author_is_told_directly_once_a_week_while_knowledge_is_due(client, admins):
    from app.core.db import SessionLocal
    from app.modules.account.models import utcnow
    from app.modules.packs.models import ScenarioPack
    from tests.conftest import JOB_HEADERS

    ks = SEED["knowledge"]
    due = {**ks[0], "valid_until": (date.today() + timedelta(days=10)).isoformat()}
    pub = _publish(client, admins, _def(knowledge=[due, *ks[1:]]))
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}
    got = _reminders()
    assert [u for u, _ in got] == [admins[0]["id"]], "只提醒写这个包的人，不提醒批的人"
    assert f"「{due['title']}」{due['valid_until']} 到期" in got[0][1] and "建新版本" in got[0][1]
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "一周只提醒一次"
    with SessionLocal() as db:
        db.get(ScenarioPack, pub["id"]).expiry_reminded_at = utcnow() - timedelta(days=8)
        db.commit()
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}, "过了一周还没更新就再提醒"
    assert client.post(JOB).status_code == 403, "没有 job 密钥被拒"


def test_nothing_due_means_no_reminder(client, admins):
    from tests.conftest import JOB_HEADERS

    far = [{**k, "valid_until": (date.today() + timedelta(days=service.EXPIRING_DAYS + 1)).isoformat()} for k in SEED["knowledge"]]
    gone = {**SEED["knowledge"][0], "valid_until": (date.today() - timedelta(days=1)).isoformat()}
    _publish(client, admins, _def(knowledge=[gone, *far[1:]]))
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "已过期的走雷达与回答里的标注，不算「快到期」"
    soon = {**SEED["knowledge"][0], "valid_until": (date.today() + timedelta(days=5)).isoformat()}
    draft = client.post(f"{API}/admin/packs", json={"definition": _def(knowledge=[soon, *far[1:]])}, headers=auth(admins[0]))
    assert draft.status_code == 201, draft.text
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 0}, "还没上线的草稿不提醒"



def test_when_the_author_no_longer_runs_ops_every_ops_admin_is_told(client, admins):
    from app.core.db import SessionLocal
    from app.modules.account.models import User
    from tests.conftest import JOB_HEADERS
    from tests.test_ticket_assign_reply import _admin

    due = {**SEED["knowledge"][0], "valid_until": (date.today() + timedelta(days=1)).isoformat()}
    _publish(client, admins, _def(knowledge=[due, *SEED["knowledge"][1:]]))
    with SessionLocal() as db:
        db.get(User, admins[0]["id"]).admin_roles = ["finance"]
        db.get(User, admins[1]["id"]).admin_roles = ["finance"]
        db.commit()
    ops = _admin(client, "13800390001", ["ops"])
    fin = _admin(client, "13800390002", ["finance"])
    assert client.post(JOB, headers=JOB_HEADERS).json() == {"reminded": 1}
    got = {u for u, _ in _reminders()}
    assert ops["id"] in got and admins[0]["id"] not in got and fin["id"] not in got
