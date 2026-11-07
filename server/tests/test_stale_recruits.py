"""AI-DEC-023 的安全一半：招募多天没人报名时提醒发单人、一键再推一次（320 号 spec，V347）。

没人报名的单会一直停在那里（母任务下的子任务尤其，整单跟着卡住）。全自动重新招募要碰预算，要发单人事先授权，
这一批不做；只做不碰钱的两件事：每天提醒（同一单每 3 天最多一次），任务页「再推一次」（可选加价，6 小时一次）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.notification.models import Notification
from app.modules.task.models import Task
from app.modules.task.stale import remind_stale_recruits
from tests.conftest import JOB_HEADERS, auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"


def _age(task_id: int, days: float):
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        t.created_at = utcnow() - timedelta(days=days)
        db.commit()


def _told(user_id: int, title_part: str) -> int:
    with SessionLocal() as db:
        return db.query(Notification).filter(Notification.user_id == user_id,
                                             Notification.title.like(f"%{title_part}%")).count()


def test_publishers_are_reminded_once_every_three_days_only_for_tasks_nobody_applied_to(client, requester):
    lonely = _post(client, requester, title="没人报名的单甲", description="x").json()
    _post(client, requester, title="刚发的单乙", description="x")
    wanted = _post(client, requester, title="有人报名的单丙", description="x").json()
    _age(lonely["id"], 4)
    _age(wanted["id"], 4)
    client.post(f"{API}/tasks/{wanted['id']}/applications", json={}, headers=auth(make_verified(client, "13600003471")))
    r = client.post(f"{API}/tasks/jobs/remind-stale-recruits", headers=JOB_HEADERS)
    assert r.status_code == 200 and r.json()["reminded"] >= 1
    assert _told(requester["id"], "没人报名的单甲」招募 4 天还没人报名") == 1
    assert _told(requester["id"], "刚发的单乙") == 0, "不到 3 天不提醒"
    assert _told(requester["id"], "有人报名的单丙") == 0, "有人报名就不提醒"
    with SessionLocal() as db:
        remind_stale_recruits(db, utcnow() + timedelta(days=1))
        db.commit()
    assert _told(requester["id"], "没人报名的单甲") == 1, "3 天内不重复提醒"
    with SessionLocal() as db:
        remind_stale_recruits(db, utcnow() + timedelta(days=3, hours=1))
        db.commit()
    assert _told(requester["id"], "没人报名的单甲") == 2, "过了 3 天再提醒一次"
    assert client.post(f"{API}/tasks/jobs/remind-stale-recruits").status_code in (401, 403), "要任务令牌"


def test_reboost_pushes_again_with_an_optional_raise_and_a_cooldown(client, requester):
    t = _post(client, requester, title="再推一次的单", description="x", budget_cents=10000).json()
    w = make_verified(client, "13600003472")
    assert client.post(f"{API}/tasks/{t['id']}/reboost", json={}, headers=auth(w)).status_code == 403, "只有发单人"
    r = client.post(f"{API}/tasks/{t['id']}/reboost", json={"raise_cents": 2000}, headers=auth(requester))
    assert r.status_code == 200 and r.json() == {"task_id": t["id"], "raise_cents": 2000, "budget_cents": 12000}, r.text
    again = client.post(f"{API}/tasks/{t['id']}/reboost", json={}, headers=auth(requester))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "reboost_too_soon"
    kinds = [x["kind"] for x in client.get(f"{API}/tasks/{t['id']}/progress", headers=auth(requester)).json()]
    assert kinds.count("reboost") == 1, "留痕"
    multi = _post(client, requester, title="三天的活", description="x", days=3,
                  start_date=(utcnow() + timedelta(days=3)).date().isoformat()).json()
    r = client.post(f"{API}/tasks/{multi['id']}/reboost", json={}, headers=auth(requester))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "use_day_reboost", "一单多天的按天补招"
    client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    # 不在招募中（这里用取消；成交后同理）
    client.post(f"{API}/tasks/{t['id']}/cancel", headers=auth(requester))
    gone = client.post(f"{API}/tasks/{t['id']}/reboost", json={}, headers=auth(requester))
    assert gone.status_code == 409 and gone.json()["detail"]["code"] == "not_recruiting"


def _as_project_with_child(root_id: int, title: str) -> int:
    """把一单改成项目根，并在下面挂一个已发布、没人报名的子任务（拆解确认后的样子）。"""
    with SessionLocal() as db:
        root = db.get(Task, root_id)
        root.task_type = "project"
        child = Task(creator_id=root.creator_id, parent_id=root.id, title=title, description="x", category=root.category,
                     task_type="simple", budget_cents=3000, is_remote=True, status="published",
                     created_at=utcnow() - timedelta(days=5))
        db.add(child)
        db.commit()
        return child.id


def test_slots_are_reminded_once_per_order_and_parents_are_never_reminded_themselves(client, requester):
    start = (utcnow() + timedelta(days=3)).date().isoformat()
    gig = _post(client, requester, title="三天两人的快闪", description="x", people_needed=2, days=3, start_date=start).json()
    root = _post(client, requester, title="装修项目根", description="x").json()
    child_id = _as_project_with_child(root["id"], "装修项目·买瓷砖")
    with SessionLocal() as db:
        for t in db.query(Task).filter((Task.id.in_([gig["id"], root["id"]])) | (Task.parent_id == gig["id"])):
            t.created_at = utcnow() - timedelta(days=4)
        db.commit()
    client.post(f"{API}/tasks/jobs/remind-stale-recruits", headers=JOB_HEADERS)
    assert _told(requester["id"], "「三天两人的快闪」有 6 个名额招募 4 天还没人报名") == 1, "六个名额合成一条"
    assert _told(requester["id"], "三天两人的快闪 · ") == 0, "不逐个名额刷屏"
    assert _told(requester["id"], "「三天两人的快闪」招募") == 0, "母任务自己不提醒"
    assert _told(requester["id"], "「装修项目根」") == 0, "项目根自己不提醒"
    assert _told(requester["id"], "「装修项目·买瓷砖」招募 5 天还没人报名") == 1, "项目的子任务照常提醒"
    client.post(f"{API}/tasks/jobs/remind-stale-recruits", headers=JOB_HEADERS)
    assert _told(requester["id"], "有 6 个名额") == 1, "3 天内不重复"
    # 带子任务的母任务不能「再推一次」：加价加不到名额、子任务上
    for pid in (root["id"], _post(client, requester, title="一天三人", description="x", people_needed=3).json()["id"]):
        r = client.post(f"{API}/tasks/{pid}/reboost", json={"raise_cents": 1000}, headers=auth(requester))
        assert r.status_code == 400 and r.json()["detail"]["code"] == "use_day_reboost", r.text
    r = client.post(f"{API}/tasks/{child_id}/reboost", json={}, headers=auth(requester))
    assert r.status_code == 200, "项目的子任务可以再推"
