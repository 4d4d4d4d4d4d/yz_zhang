"""SCN-126 发单人一次选同一个人的多天（181 号 spec，V208）。

帮手一次报了三天（177 号），发单人还要逐个名额选三次。现在按人看谁报了哪几天，一次选上；每个名额各一份合约，
签署与托管照旧逐份由人确认。顺带修：选了一个人后，同一天还有空名额时，其他人的报名挪过去而不是被拒。
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
    return t, [(start + timedelta(days=i)).isoformat() for i in range(days)]


def _helper(client, phone, name):
    u = register(client, phone, name)
    verify_user(client, u, name)
    return u


def test_poster_sees_who_applied_for_which_days_and_accepts_a_person_at_once(client, requester, worker):
    t, d = _parent(client, requester)
    other = _helper(client, "13800000381", "帮手乙")
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[1]]}, headers=auth(other))   # 先报、但只报一天
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": d}, headers=auth(worker))
    people = client.get(f"{API}/{t['id']}/applicants", headers=auth(requester)).json()
    assert [p["applicant_id"] for p in people] == [worker["id"], other["id"]], "报的天数多的在前"
    assert [x["date"] for x in people[0]["days"]] == d and people[0]["nickname"] == "执行者"
    r = client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(requester))
    assert r.status_code == 200, r.text
    out = r.json()
    assert [a["date"] for a in out["accepted"]] == d and out["skipped"] == []
    assert len({a["contract_id"] for a in out["accepted"]}) == 3, "每个名额一份合约"
    with SessionLocal() as db:
        assert all(db.get(Task, a["task_id"]).executor_id == worker["id"] for a in out["accepted"])
        # 帮手乙报的第 2 天：原本和执行者落在同一个名额上，现在挪到那天的第二个名额，仍在等发单人选
        mine = db.query(Application).filter(Application.applicant_id == other["id"]).one()
        assert mine.status == "pending" and mine.task_id == t["slots"][3]["id"]


def test_without_a_free_slot_that_day_the_others_are_rejected_as_before(client, requester, worker):
    t, d = _parent(client, requester, people=1, days=2)
    other = _helper(client, "13800000382", "帮手丙")
    for u in (worker, other):
        client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0]]}, headers=auth(u))
    client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(requester))
    with SessionLocal() as db:
        assert db.query(Application).filter(Application.applicant_id == other["id"]).one().status == "rejected"


def test_days_that_cannot_be_accepted_are_explained(client, requester, worker):
    from app.core.config import settings

    t, d = _parent(client, requester, people=1, days=3)
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": d}, headers=auth(worker))
    old = settings.MAX_ACTIVE_TASKS
    settings.MAX_ACTIVE_TASKS = 2
    try:
        out = client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(requester)).json()
    finally:
        settings.MAX_ACTIVE_TASKS = old
    assert [a["date"] for a in out["accepted"]] == d[:2]
    assert out["skipped"][0]["date"] == d[2] and "上限" in out["skipped"][0]["reason"]
    r = client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(requester))
    assert r.status_code == 200 and r.json()["accepted"][0]["date"] == d[2], "上限放开后剩下那天还能选"
    r = client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "nothing_to_accept"


def test_only_the_poster(client, requester, worker):
    t, d = _parent(client, requester)
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": d}, headers=auth(worker))
    assert client.get(f"{API}/{t['id']}/applicants", headers=auth(worker)).status_code == 403
    r = client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(worker))
    assert r.status_code == 403


def test_moved_application_skips_slots_that_are_closed_or_already_applied_by_that_person(client, requester, worker):
    t, d = _parent(client, requester, people=4, days=2)
    day1 = [x["id"] for x in t["slots"][:4]]          # 第 1 天的四个名额
    other = _helper(client, "13800000383", "帮手丁")
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0]]}, headers=auth(other))      # 落在名额 1
    assert client.post(f"{API}/{day1[2]}/applications", json={}, headers=auth(other)).status_code == 201  # 名额 3 也报了
    with SessionLocal() as db:                                                                    # 名额 2 停招了
        db.get(Task, day1[1]).status = "cancelled"
        db.commit()
    client.post(f"{API}/{t['id']}/apply-days", json={"dates": [d[0]]}, headers=auth(worker))
    client.post(f"{API}/{t['id']}/accept-person", json={"applicant_id": worker["id"]}, headers=auth(requester))
    with SessionLocal() as db:
        rows = db.query(Application).filter(Application.applicant_id == other["id"], Application.status == "pending").all()
        assert sorted(r.task_id for r in rows) == [day1[2], day1[3]], "跳过停招的名额 2 与自己已报的名额 3，挪到名额 4"
