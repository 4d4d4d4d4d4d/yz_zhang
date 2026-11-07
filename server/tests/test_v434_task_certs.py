"""SCN-294b（407 号 spec，V434）发单人按这一单加选资质：类目列出可加的（optional_certs），发单时勾上，报名的人要都有。

- 「无人机航拍」可加「民用无人机操控员执照」（小型及以上机要，消费级轻型机多数不要）；
- 「展台搭建」可加「高处作业操作证」「低压电工作业操作证」（2 米以上作业、接电）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.service import DRONE_PILOT_CERT, ELECTRICIAN_CERT, HEIGHT_WORK_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"


def _cats(client):
    return {c["name"]: c for c in client.get(f"{API}/categories").json()}


def test_categories_list_what_can_be_added(client):
    cats = _cats(client)
    assert cats["无人机航拍"]["optional_certs"] == [DRONE_PILOT_CERT]
    assert cats["展台搭建"]["optional_certs"] == [HEIGHT_WORK_CERT, ELECTRICIAN_CERT]
    assert "optional_certs" not in cats["跑腿"]          # 没有可加的不带这个字段（与以前一样）


def test_only_offered_certs_can_be_added(client, requester):
    r = _post(client, requester, title="展台搭建", description="36 平米", category="展台搭建", task_certs=["律师"])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "task_cert_not_offered", r.text
    assert HEIGHT_WORK_CERT in r.json()["detail"]["message"]
    r = _post(client, requester, task_certs=[HEIGHT_WORK_CERT])          # 跑腿没有可加的
    assert r.status_code == 400 and "没有可以另外加" in r.json()["detail"]["message"]


def test_added_cert_gates_applications_and_is_public(client, requester):
    ops = make_admin(client, "13600043401", "审核")
    t = _post(client, requester, title="展台背板 3 米高", description="要上梯子", category="展台搭建",
              task_certs=[HEIGHT_WORK_CERT, " ", HEIGHT_WORK_CERT]).json()
    assert t["task_certs"] == [HEIGHT_WORK_CERT]                       # 去空、去重
    w = make_verified(client, "13600043402")
    assert client.get(f"{API}/tasks/{t['id']}", headers=auth(w)).json()["task_certs"] == [HEIGHT_WORK_CERT]
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and no.json()["detail"]["code"] == "certification_required", no.text
    assert no.json()["detail"]["message"].startswith(f"这一单需「{HEIGHT_WORK_CERT}」")
    app_id = apply_cert(client, w, name=HEIGHT_WORK_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201


def test_without_added_certs_nothing_changes(client, requester):
    t = _post(client, requester, title="展位布置", description="只摆展品，不上高", category="展台搭建").json()
    assert t["task_certs"] == []
    w = make_verified(client, "13600043403")
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201


def test_multi_slot_tasks_carry_the_added_certs(client, requester):
    r = _post(client, requester, title="航拍两个机位", description="小型机", category="无人机航拍",
              task_certs=[DRONE_PILOT_CERT], people_needed=2)
    assert r.status_code in (200, 201), r.text
    from app.modules.task.models import Task

    with SessionLocal() as db:
        slots = db.query(Task).filter(Task.parent_id == r.json()["id"]).all()
        assert len(slots) == 2 and all(s.task_certs == [DRONE_PILOT_CERT] for s in slots)


def test_admin_sets_optional_certs_and_seed_backfills_without_overwriting(client):
    from app.modules.task.models import Category
    from app.modules.task.service import seed_categories

    ops = make_admin(client, "13600043404", "运营")
    cid = _cats(client)["跑腿"]["id"]
    r = client.patch(f"{API}/admin/categories/{cid}?optional_certs=驾驶证（三年以上驾龄）、驾驶证（三年以上驾龄）", headers=auth(ops))
    assert r.status_code == 200 and r.json()["optional_certs"] == ["驾驶证（三年以上驾龄）"], r.text
    with SessionLocal() as db:   # 老库里的类目没有可加选的：种子补上；运营改过的不动
        db.query(Category).filter(Category.name == "无人机航拍").one().optional_certs = []
        db.query(Category).filter(Category.name == "展台搭建").one().optional_certs = ["运营自己定的"]
        db.commit()
        seed_categories(db)
        db.commit()
        assert db.query(Category).filter(Category.name == "无人机航拍").one().optional_certs == [DRONE_PILOT_CERT]
        assert db.query(Category).filter(Category.name == "展台搭建").one().optional_certs == ["运营自己定的"]
