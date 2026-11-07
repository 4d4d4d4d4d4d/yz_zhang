"""SCN-294c（414 号 spec，V441）发布后改加选资质。

407 号起发单人可以按这一单加选资质，但只能在发单时选；发出去才发现「这张证其实用不上、把人全挡了」，
只能撤单重发。413 号又告诉了他「几个人只差这一张」——得让他能去掉。
加上要小心：已报名的人里有没这张证的，悄悄加上等于替他把人挡掉。
"""
from app.core.db import SessionLocal
from app.modules.task.service import ELECTRICIAN_CERT, HEIGHT_WORK_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v435_recommend_certs import _approve

API = "/api/v1"


def _edit(client, who, tid, certs):
    return client.patch(f"{API}/tasks/{tid}", json={"task_certs": certs}, headers=auth(who))


def test_publisher_can_drop_an_added_cert_and_then_anyone_can_apply(client, requester):
    w = make_verified(client, "13600044101")
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 400   # 没证报不了
    r = _edit(client, requester, t["id"], [])
    assert r.status_code == 200, r.text
    assert r.json()["task_certs"] == []
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201


def test_only_offered_certs_and_cleaned(client, requester):
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建").json()
    bad = _edit(client, requester, t["id"], ["民用无人机操控员执照"])
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "task_cert_not_offered"
    ok = _edit(client, requester, t["id"], [f" {HEIGHT_WORK_CERT} ", HEIGHT_WORK_CERT, ""])
    assert ok.status_code == 200 and ok.json()["task_certs"] == [HEIGHT_WORK_CERT]


def test_adding_is_refused_while_a_pending_applicant_lacks_it(client, requester):
    ops = make_admin(client, "13600044102", "审核")
    w = make_verified(client, "13600044103")
    t = _post(client, requester, title="展台布置", description="先只摆展品", category="展台搭建").json()
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    r = _edit(client, requester, t["id"], [ELECTRICIAN_CERT])
    assert r.status_code == 409 and r.json()["detail"]["code"] == "task_certs_locked"
    msg = r.json()["detail"]["message"]
    assert "1 个报名的人没有「低压电工作业操作证」" in msg and "先谢绝" in msg
    assert client.get(f"{API}/tasks/{t['id']}", headers=auth(requester)).json()["task_certs"] == []
    _approve(client, ops, w, ELECTRICIAN_CERT)            # 他补交了证件，审核通过
    assert _edit(client, requester, t["id"], [ELECTRICIAN_CERT]).status_code == 200


def test_dropping_is_allowed_even_with_pending_applicants(client, requester):
    ops = make_admin(client, "13600044104", "审核")
    w = make_verified(client, "13600044105")
    _approve(client, ops, w, HEIGHT_WORK_CERT)
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    assert _edit(client, requester, t["id"], []).json()["task_certs"] == []


def test_multi_slot_open_slots_follow_the_parent(client, requester):
    from app.modules.task.models import Task

    r = _post(client, requester, title="展台两个人", description="背板 3 米", category="展台搭建",
              task_certs=[HEIGHT_WORK_CERT], people_needed=2).json()
    assert _edit(client, requester, r["id"], []).status_code == 200
    with SessionLocal() as db:
        slots = db.query(Task).filter(Task.parent_id == r["id"]).all()
        assert len(slots) == 2 and all(s.task_certs == [] for s in slots)


def test_only_the_publisher_and_only_before_work_starts(client, requester):
    other = make_verified(client, "13600044106")
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    assert _edit(client, other, t["id"], []).status_code == 403
