"""SPACE-024 / AI-DEC-021 合作驾驶舱（120 号 spec）：树、关键路径、预算账、预警；只给发布方。"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.cockpit import critical_path
from app.modules.task.models import Task
from tests.conftest import auth, topup
from tests.test_decompose_tree import _propose
from tests.test_task_flow import match_and_fund


def _confirmed(client, requester):
    t, dec = _propose(client, requester, category="软件开发", title="公司官网", description="响应式官网")
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 200, r.text
    return t


def test_cockpit_shows_budget_alerts_and_critical_path(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    topup(client, requester, 2_000_000)
    t = _confirmed(client, requester)
    cp = client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(requester)).json()
    _assert_shape(cp, "Cockpit")
    _assert_shape(cp["budget"], "CockpitBudget")
    _assert_shape(cp["nodes"][0], "CockpitNode")
    assert cp["steps_total"] == 5 and cp["steps_done"] == 0
    assert cp["budget"]["planned_cents"] == t["budget_cents"] and cp["budget"]["committed_cents"] == 0
    # 关键路径是一条依赖链：相邻两步，后一步依赖前一步
    path = cp["critical_path"]
    assert len(path) >= 2
    by = {n["id"]: n for n in cp["nodes"]}
    assert all(path[i] in by[path[i + 1]]["depends_on"] for i in range(len(path) - 1))
    first = next(n for n in cp["nodes"] if n["id"] == cp["critical_path"][0])
    second = next(n for n in cp["nodes"] if n["id"] == cp["critical_path"][1])
    assert second["blocked_by"] == [first["id"]] and second["on_critical_path"]
    # 第一步成交托管 → 账上「已托管」；逾期 → 预警
    child = client.get(f"/api/v1/tasks/{first['id']}", headers=auth(requester)).json()
    match_and_fund(client, requester, worker, child)
    with SessionLocal() as db:
        row = db.get(Task, first["id"])
        row.deadline = utcnow() - timedelta(hours=2)
        db.commit()
    cp = client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(requester)).json()
    assert cp["budget"]["committed_cents"] == first["budget_cents"]
    assert cp["budget"]["remaining_cents"] == t["budget_cents"] - first["budget_cents"]
    node = next(n for n in cp["nodes"] if n["id"] == first["id"])
    assert node["executor_id"] == worker["id"] and node["executor_nickname"] and node["overdue"]
    assert any(a["kind"] == "overdue" and a["task_id"] == first["id"] for a in cp["alerts"])
    _assert_shape(cp["alerts"][0], "CockpitAlert")


def test_cockpit_is_for_the_publisher_only(client, requester, worker):
    t = _confirmed(client, requester)
    assert client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(worker)).status_code == 403
    assert client.get("/api/v1/tasks/999999/cockpit", headers=auth(requester)).status_code == 404
    # 公开的进度接口不变（只增不减）
    assert client.get(f"/api/v1/tasks/{t['id']}/tree", headers=auth(worker)).status_code == 200


def test_critical_path_counts_only_unfinished_steps():
    def n(i, deps, status="draft"):
        return Task(id=i, depends_on=deps, status=status, title=str(i))

    # 1 → 2 → 4，3 独立；1 已完成：剩余最长链是 2 → 4
    nodes = [n(1, [], "completed"), n(2, [1]), n(3, []), n(4, [2])]
    assert critical_path(nodes) == [2, 4]
    # 长链大半已完成（还剩 1 步）vs 短链两步都没做：关键路径是短链——数的是「还剩几步」
    nodes = [n(1, [], "completed"), n(2, [1], "completed"), n(3, [2]), n(4, []), n(5, [4])]
    assert critical_path(nodes) == [4, 5]
    # 全完成：没有关键路径
    assert critical_path([n(1, [], "completed")]) == []
    # 环（脏数据）不死循环
    assert critical_path([n(1, [2]), n(2, [1])]) in ([1, 2], [2, 1])


def test_schedule_conflicts_are_flagged_and_clear_when_fixed(client, requester):
    """AI-DEC-021b（368 号 spec）：后一步的截止不晚于它要等的前一步、某一步晚于整件事的截止，都进「需要你出手」。"""
    from tests.test_client_shape_alignment import _assert_shape

    t = _confirmed(client, requester)
    url = f"/api/v1/tasks/{t['id']}/cockpit"
    cp = client.get(url, headers=auth(requester)).json()
    first, second = cp["critical_path"][0], cp["critical_path"][1]
    others = [n["id"] for n in cp["nodes"] if not n["is_container"] and n["id"] not in (first, second)]
    assert not any(a["kind"] in ("schedule_conflict", "past_parent_deadline") for a in cp["alerts"])
    now = utcnow()
    with SessionLocal() as db:
        db.get(Task, first).deadline = now + timedelta(days=5)
        db.get(Task, second).deadline = now + timedelta(days=5)      # 同一天也不行：前一步做完才能开始
        db.get(Task, t["id"]).deadline = now + timedelta(days=10)
        db.get(Task, others[0]).deadline = now + timedelta(days=12)  # 晚于整件事
        db.commit()
    cp = client.get(url, headers=auth(requester)).json()
    by = {n["id"]: n for n in cp["nodes"]}
    assert by[second]["schedule_conflicts"] == [first] and by[first]["schedule_conflicts"] == []
    _assert_shape(by[second], "CockpitNode")
    conflict = [a for a in cp["alerts"] if a["kind"] == "schedule_conflict"]
    assert [a["task_id"] for a in conflict] == [second] and by[first]["title"] in conflict[0]["text"]
    late = [a for a in cp["alerts"] if a["kind"] == "past_parent_deadline"]
    assert [a["task_id"] for a in late] == [others[0]] and "整件事" in late[0]["text"]
    # 改对以后预警消失；前一步已经做完的，也不再算冲突
    with SessionLocal() as db:
        db.get(Task, second).deadline = now + timedelta(days=8)
        db.get(Task, others[0]).deadline = now + timedelta(days=9)
        db.commit()
    cp = client.get(url, headers=auth(requester)).json()
    assert not any(a["kind"] in ("schedule_conflict", "past_parent_deadline") for a in cp["alerts"])
    with SessionLocal() as db:
        db.get(Task, second).deadline = now + timedelta(days=2)
        db.commit()
    assert any(a["kind"] == "schedule_conflict" for a in client.get(url, headers=auth(requester)).json()["alerts"])
    with SessionLocal() as db:
        db.get(Task, first).status = "completed"
        db.commit()
    cp = client.get(url, headers=auth(requester)).json()
    assert not any(a["kind"] == "schedule_conflict" for a in cp["alerts"])
    assert {n["id"]: n for n in cp["nodes"]}[second]["schedule_conflicts"] == []
