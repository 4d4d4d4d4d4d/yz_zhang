"""SCN-121 缺人的那天一键补招（196 号 spec，V224）。

「5 个人干 3 天」：按天汇总（V201）已经看得出哪天缺人，但补招只能一个个名额去改预算，再推也推不出去。
现在在那一天上一键补招：还在招的名额再推一次（叫醒「现在有空」的人和订阅这个类目的人），可选每个名额加价；
加价走已发布任务本来的规则（只许上调、通知已报名的人，钱在签约托管时才冻结）。同一天 6 小时内只补招一次。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.gig import service as gsvc
from app.modules.notification.models import Notification
from app.modules.task.models import ProgressLog, Task
from tests.conftest import auth, register, verify_user
from tests.test_multiday_slots import _post, _today

API = "/api/v1/tasks"


def _parent(client, requester, people=2, days=2, offset=2):
    start = _today() + timedelta(days=offset)
    t = _post(client, requester, people_needed=people, days=days, start_date=start.isoformat()).json()
    return t, [(start + timedelta(days=i)).isoformat() for i in range(days)]


def test_reboost_raises_the_open_slots_of_that_day_and_pushes_them_again(client, requester, worker):
    t, d = _parent(client, requester, offset=0)   # 从今天开始：今天的名额与「接下来两小时有空」对得上（V220）
    day1 = [s["id"] for s in t["slots"][:2]]
    with SessionLocal() as db:   # 第 1 天的第一个名额已经招到人了：只补另一个
        db.get(Task, day1[0]).executor_id = worker["id"]
        db.commit()
    applicant = register(client, "13800000391", "帮手甲")
    verify_user(client, applicant, "帮手甲")
    assert client.post(f"{API}/{day1[1]}/applications", json={}, headers=auth(applicant)).status_code == 201
    free = register(client, "13800000392", "有空的人")
    client.put("/api/v1/gig/available", json={"lat": 31.23, "lng": 121.47, "radius_km": 5}, headers=auth(free))
    before = {s["id"]: s["budget_cents"] for s in t["slots"]}
    r = client.post(f"{API}/{t['id']}/days/{d[0]}/reboost", json={"raise_cents": 1000}, headers=auth(requester))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["slot_ids"] == [day1[1]] and out["budget_cents"] == [before[day1[1]] + 1000]
    with SessionLocal() as db:
        assert db.get(Task, day1[0]).budget_cents == before[day1[0]], "招到人的名额不动"
        assert db.get(Task, t["id"]).budget_cents == t["budget_cents"] + 1000, "母任务预算同步"
        note = db.query(Notification).filter(Notification.user_id == applicant["id"], Notification.title == "报名的任务有更新").one()
        assert "上调了预算" in note.body, "已报名的人知道加价了"
        assert db.query(Notification).filter(Notification.user_id == free["id"], Notification.title == gsvc.PUSH_TITLE).count() >= 1
        log = db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "reboost").one()
        assert d[0] in log.content and "加价 10.00 元" in log.content


def test_only_push_again_and_the_cooldown(client, requester):
    t, d = _parent(client, requester)
    r = client.post(f"{API}/{t['id']}/days/{d[1]}/reboost", json={}, headers=auth(requester))
    assert r.status_code == 200 and r.json()["raise_cents"] == 0
    assert r.json()["budget_cents"] == [s["budget_cents"] for s in t["slots"][2:]], "只再推一次：预算不变"
    r = client.post(f"{API}/{t['id']}/days/{d[1]}/reboost", json={"raise_cents": 500}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "reboost_too_soon"
    assert "小时内刚补招过" in r.json()["detail"]["message"]
    assert client.post(f"{API}/{t['id']}/days/{d[0]}/reboost", json={}, headers=auth(requester)).status_code == 200, "别的日子不受影响"
    with SessionLocal() as db:   # 6 小时以后可以再推
        for row in db.query(ProgressLog).filter(ProgressLog.task_id == t["id"], ProgressLog.kind == "reboost"):
            row.created_at = utcnow() - timedelta(hours=7)
        db.commit()
    assert client.post(f"{API}/{t['id']}/days/{d[1]}/reboost", json={}, headers=auth(requester)).status_code == 200


def test_rules(client, requester, worker):
    t, d = _parent(client, requester, people=1, days=2)
    r = client.post(f"{API}/{t['id']}/days/{d[0]}/reboost", json={}, headers=auth(worker))
    assert r.status_code == 403
    single = _post(client, requester).json()
    r = client.post(f"{API}/{single['id']}/days/{d[0]}/reboost", json={}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_multi_day"
    past = (_today() - timedelta(days=1)).isoformat()
    r = client.post(f"{API}/{t['id']}/days/{past}/reboost", json={}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "day_passed"
    with SessionLocal() as db:
        db.get(Task, t["slots"][0]["id"]).executor_id = worker["id"]
        db.commit()
    r = client.post(f"{API}/{t['id']}/days/{d[0]}/reboost", json={}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "day_full"
    r = client.post(f"{API}/{t['id']}/days/{d[1]}/reboost", json={"raise_cents": -1}, headers=auth(requester))
    assert r.status_code == 422, "只许上调"


def test_subscribers_are_told_it_is_still_open_not_new(client, requester):
    sub = register(client, "13800000393", "订阅的人")
    client.post("/api/v1/subscriptions", json={"category": "跑腿", "city": "上海"}, headers=auth(sub))
    t, d = _parent(client, requester, people=1, days=2)
    client.post(f"{API}/{t['id']}/days/{d[0]}/reboost", json={}, headers=auth(requester))
    with SessionLocal() as db:
        bodies = [n.body for n in db.query(Notification).filter(Notification.user_id == sub["id"],
                                                                Notification.title == "订阅类目有新任务")]
    assert any(b.endswith("还在招人") for b in bodies), bodies


def test_parent_budget_grows_by_the_raise_times_the_open_slots(client, requester):
    t, d = _parent(client, requester, people=2, days=2)   # 每天两个名额都还在招
    r = client.post(f"{API}/{t['id']}/days/{d[0]}/reboost", json={"raise_cents": 500}, headers=auth(requester))
    assert len(r.json()["slot_ids"]) == 2
    with SessionLocal() as db:
        assert db.get(Task, t["id"]).budget_cents == t["budget_cents"] + 2 * 500
        assert sum(db.get(Task, s["id"]).budget_cents for s in t["slots"]) == t["budget_cents"] + 1000, "名额预算之和与母任务一致"
