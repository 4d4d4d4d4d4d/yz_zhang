"""SCN-118 一个人一次报多天（177 号 spec，V204）。

「5 个人干 3 天」：同一个帮手三天都能来，以前要在三个名额上各报一次。现在在母任务上选几天，一次报完；
每天只报一个名额，哪天报不了逐日说清；每个名额仍是独立的报名（发单人逐个选人、逐天签约）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.task.models import Application, Task
from tests.conftest import auth, register, verify_user
from tests.test_multiday_slots import _post, _today

API = "/api/v1/tasks"


def _parent(client, requester, people=2, days=3):
    start = _today() + timedelta(days=2)
    t = _post(client, requester, people_needed=people, days=days, start_date=start.isoformat()).json()
    return t, [start + timedelta(days=i) for i in range(days)]


def test_one_application_per_chosen_day_on_an_open_slot(client, requester, worker):
    t, d = _parent(client, requester)
    r = client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[2].isoformat(), d[0].isoformat(), d[0].isoformat()],
                                                         "message": "三天里这两天都能来"}, headers=auth(worker))
    assert r.status_code == 201, r.text
    out = r.json()
    assert [a["date"] for a in out["applied"]] == [d[0].isoformat(), d[2].isoformat()], "按日期排、同一天只报一次"
    assert out["skipped"] == []
    with SessionLocal() as db:
        rows = db.query(Application).filter(Application.applicant_id == 2).all()
        assert len(rows) == 2 and all(r.message == "三天里这两天都能来" for r in rows)
        dates = sorted(db.get(Task, r.task_id).work_date for r in rows)
        assert dates == [d[0], d[2]]
    # 发单人在每个名额上照常看到这份报名、逐个选人
    first = out["applied"][0]["task_id"]
    apps = client.get(f"{API}/{first}/applications", headers=auth(requester)).json()
    assert len(apps) == 1


def test_days_already_applied_full_or_missing_are_explained_and_the_rest_go_through(client, requester, worker):
    t, d = _parent(client, requester, people=1)
    slot_day1 = t["slots"][0]["id"]
    assert client.post(f"{API}/{slot_day1}/applications", json={}, headers=auth(worker)).status_code == 201
    with SessionLocal() as db:   # 第 2 天的名额停招了
        db.get(Task, t["slots"][1]["id"]).status = "cancelled"
        db.commit()
    missing = d[2] + timedelta(days=5)
    r = client.post(f"{API}/{t['id']}/apply-days",
                    json={"dates": [x.isoformat() for x in d] + [missing.isoformat()]}, headers=auth(worker)).json()
    assert [a["date"] for a in r["applied"]] == [d[2].isoformat()]
    assert {s["date"]: s["reason"] for s in r["skipped"]} == {
        d[0].isoformat(): "这一天你已经报过了",
        d[1].isoformat(): "这一天的名额已经招满或停招了",
        missing.isoformat(): "这单没有这一天",
    }
    r = client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(worker))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_day_available"
    assert "你已经报过了" in r.json()["detail"]["message"]


def test_second_person_gets_the_next_open_slot_of_the_same_day(client, requester, worker):
    t, d = _parent(client, requester, people=2, days=2)
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(worker))
    other = register(client, "13800000377", "帮手乙")
    verify_user(client, other, "王五")
    r = client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(other)).json()
    # 报名不占名额（发单人还没选人），两个人都落在同一天的第一个还在招的名额上，由发单人挑
    assert r["applied"][0]["task_id"] == t["slots"][0]["id"]


def test_same_rules_as_a_single_application(client, requester, worker):
    t, d = _parent(client, requester)
    r = client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "self_apply"
    single = _post(client, requester).json()
    r = client.post(f"{API}/{single['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_multi_day"
    r = client.post(f"{API}/{t['slots'][0]['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_multi_day", "名额本身不是母任务"
    unverified = register(client, "13800000378", "没实名")
    r = client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0].isoformat()]}, headers=auth(unverified))
    assert r.status_code == 403
