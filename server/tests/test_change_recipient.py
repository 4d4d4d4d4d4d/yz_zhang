"""SCN-123 发单后改服务对象（197 号 spec，V223）。

替爸妈发的单，临时换成爸爸在家、或者阿姨换了电话：以前只能取消重发（已报名、已签约的都白费）。
现在发单人直接改称呼与到场联系方式；换人、改联系方式都要重新确认「问过本人」，同意时间刷新；
多天单同步到没结束的名额；接单的人收到通知（只写称呼）；已结束或纠纷中的不能改。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from app.modules.task.models import ProgressLog, Task
from tests.conftest import auth, topup
from tests.test_multiday_slots import _post as _post_multi, _today
from tests.test_on_behalf import ON_BEHALF, _post
from tests.test_task_flow import match_and_fund

API = "/api/v1/tasks"
NEW = {"recipient_label": "我爸", "onsite_contact": "李叔 13900002222", "recipient_consented": True}


def test_poster_changes_the_recipient_and_the_executor_is_told(client, requester, worker):
    t = _post(client, requester, **ON_BEHALF).json()
    topup(client, requester, 40000)
    match_and_fund(client, requester, worker, t)
    with SessionLocal() as db:
        db.get(Task, t["id"]).recipient_consent_at -= timedelta(days=1)
        first = db.get(Task, t["id"]).recipient_consent_at
        db.commit()
    r = client.patch(f"{API}/{t['id']}/recipient", json=NEW, headers=auth(requester))
    assert r.status_code == 200, r.text
    assert (r.json()["recipient_label"], r.json()["onsite_contact"]) == ("我爸", "李叔 13900002222")
    seen = client.get(f"{API}/{t['id']}", headers=auth(worker)).json()
    assert (seen["recipient_label"], seen["onsite_contact"]) == ("我爸", "李叔 13900002222")
    with SessionLocal() as db:
        assert db.get(Task, t["id"]).recipient_consent_at > first, "重新问过本人：同意时间刷新"
        note = db.query(Notification).filter(Notification.user_id == worker["id"], Notification.title == "服务对象有变化").one()
        assert "「我爸」" in note.body and "13900002222" not in note.body, "通知里不放联系方式"
        log = db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.content.contains("改了服务对象")).one()
        assert "13900002222" not in log.content


def test_consent_is_asked_again_and_only_the_poster_of_an_on_behalf_task_may_change(client, requester, worker):
    t = _post(client, requester, **ON_BEHALF).json()
    r = client.patch(f"{API}/{t['id']}/recipient", json={**NEW, "recipient_consented": False}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "recipient_consent_required"
    r = client.patch(f"{API}/{t['id']}/recipient", json={**NEW, "recipient_label": "  "}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "recipient_label_required"
    assert client.patch(f"{API}/{t['id']}/recipient", json=NEW, headers=auth(worker)).status_code == 403
    mine = _post(client, requester).json()
    r = client.patch(f"{API}/{mine['id']}/recipient", json=NEW, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_on_behalf"
    r = client.patch(f"{API}/{t['id']}/recipient", json={**NEW, "robot": True}, headers=auth(requester))
    assert r.status_code == 422, "多收字段一律不收"


def test_finished_or_disputed_tasks_are_locked(client, requester):
    t = _post(client, requester, **ON_BEHALF).json()
    for status in ("completed", "cancelled", "disputed"):
        with SessionLocal() as db:
            db.get(Task, t["id"]).status = status
            db.commit()
        r = client.patch(f"{API}/{t['id']}/recipient", json=NEW, headers=auth(requester))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "recipient_locked", status


def test_multi_day_slots_follow_unless_they_are_over(client, requester):
    start = _today() + timedelta(days=2)
    t = _post_multi(client, requester, people_needed=1, days=3, start_date=start.isoformat(), **ON_BEHALF).json()
    ids = [s["id"] for s in t["slots"]]
    with SessionLocal() as db:
        db.get(Task, ids[0]).status = "completed"
        db.commit()
    assert client.patch(f"{API}/{t['id']}/recipient", json=NEW, headers=auth(requester)).status_code == 200
    with SessionLocal() as db:
        labels = [db.get(Task, i).recipient_label for i in ids]
    assert labels == ["我妈", "我爸", "我爸"], "做完的那天保留当时的服务对象"
