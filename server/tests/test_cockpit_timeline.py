"""AI-DEC-021c（384 号 spec）驾驶舱的时间线：步骤带工期估计（天），按依赖排出起止，算出整件事预计哪天做完。"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.cockpit import timeline
from app.modules.task.models import Task
from tests.conftest import auth
from tests.test_cockpit import _confirmed
from tests.test_decompose_tree import _patch, _propose

NOW = utcnow()


def _n(i, deps, est=None, status="draft", deadline=None):
    return Task(id=i, depends_on=deps, status=status, title=str(i), est_days=est, deadline=deadline)


def _rows(plan):
    return {r["task_id"]: r for r in plan["rows"]}


def test_steps_start_after_what_they_wait_for_and_the_finish_is_the_latest_end():
    # 1(2 天) → 2(3 天)；3(1 天) 独立：2 从 1 做完开始，整件事第 5 天做完
    plan = timeline([_n(1, [], 2), _n(2, [1], 3), _n(3, [], 1)], NOW)
    r = _rows(plan)
    assert r[1]["start"] == NOW and r[1]["end"] == NOW + timedelta(days=2)
    assert r[2]["start"] == NOW + timedelta(days=2) and r[2]["end"] == NOW + timedelta(days=5)
    assert r[3]["start"] == NOW and r[3]["end"] == NOW + timedelta(days=1)
    assert plan["projected_finish"] == NOW + timedelta(days=5) and plan["unknown_steps"] == []
    # 要等两步：从晚的那步做完开始
    r = _rows(timeline([_n(1, [], 2), _n(2, [], 4), _n(3, [1, 2], 1)], NOW))
    assert r[3]["start"] == NOW + timedelta(days=4)


def test_finished_steps_do_not_hold_anyone_up_and_get_no_bar():
    plan = timeline([_n(1, [], 9, status="completed"), _n(2, [1], 3), _n(4, [], 9, status="cancelled")], NOW)
    r = _rows(plan)
    assert r[1]["basis"] == "done" and r[1]["start"] is None and r[4]["basis"] == "done"
    assert r[2]["start"] == NOW and plan["projected_finish"] == NOW + timedelta(days=3)


def test_a_deadline_stands_in_when_there_is_no_estimate_and_unknowns_propagate():
    due = NOW + timedelta(days=6)
    plan = timeline([_n(1, [], None, deadline=due), _n(2, [1], 2)], NOW)
    r = _rows(plan)
    assert r[1]["basis"] == "deadline" and r[1]["end"] == due
    assert r[2]["start"] == due and plan["projected_finish"] == due + timedelta(days=2)
    # 既没工期也没截止：这一步排不出来，等它的那一步也排不出来，整件事的完成日不给
    plan = timeline([_n(1, [], None), _n(2, [1], 2), _n(3, [], 1)], NOW)
    r = _rows(plan)
    assert r[1]["basis"] == "unknown" and r[2]["basis"] == "unknown" and r[3]["basis"] == "estimate"
    assert plan["projected_finish"] is None and plan["unknown_steps"] == [1, 2]
    # 截止已经过了、又没有工期：也排不出来（逾期由原来的预警管）
    assert _rows(timeline([_n(1, [], None, deadline=NOW - timedelta(days=1))], NOW))[1]["basis"] == "unknown"


def test_a_step_that_cannot_make_its_own_deadline_is_late():
    plan = timeline([_n(1, [], 4), _n(2, [1], 3, deadline=NOW + timedelta(days=6))], NOW)
    assert _rows(plan)[2]["late"] and not _rows(plan)[1]["late"]
    plan = timeline([_n(1, [], 4), _n(2, [1], 2, deadline=NOW + timedelta(days=6))], NOW)
    assert not _rows(plan)[2]["late"]
    # 环（脏数据）不死循环
    assert len(timeline([_n(1, [2], 1), _n(2, [1], 1)], NOW)["rows"]) == 2


def test_cockpit_carries_the_timeline_and_warns_when_the_whole_thing_runs_late(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    t = _confirmed(client, requester)
    url = f"/api/v1/tasks/{t['id']}/cockpit"
    cp = client.get(url, headers=auth(requester)).json()
    _assert_shape(cp["timeline"], "CockpitTimeline")
    leaves = [n["id"] for n in cp["nodes"] if not n["is_container"]]
    # 没填工期：排不出来，不给完成日，也不乱报预警
    assert cp["timeline"]["projected_finish"] is None and set(cp["timeline"]["unknown_steps"]) == set(leaves)
    assert not any(a["kind"] in ("projected_late", "estimate_past_deadline") for a in cp["alerts"])
    # 发单人在发布前给每一步填工期（任务编辑接口）
    for i in leaves:
        r = client.patch(f"/api/v1/tasks/{i}", json={"est_days": 2}, headers=auth(requester))
        assert r.status_code == 200 and r.json()["est_days"] == 2, r.text
    cp = client.get(url, headers=auth(requester)).json()
    _assert_shape(cp["timeline"]["rows"][0], "CockpitTimelineRow")
    rows = {r["task_id"]: r for r in cp["timeline"]["rows"]}
    path = cp["critical_path"]
    assert rows[path[1]]["start"] == rows[path[0]]["end"]
    assert cp["timeline"]["projected_finish"] is not None and cp["timeline"]["unknown_steps"] == []
    assert {n["id"]: n for n in cp["nodes"]}[path[0]]["est_days"] == 2
    # 整件事截止只给 3 天，而依赖链要 2 天 × 链长：预警「整件事会晚」
    with SessionLocal() as db:
        db.get(Task, t["id"]).deadline = utcnow() + timedelta(days=3)
        db.get(Task, path[1]).deadline = utcnow() + timedelta(days=3)
        db.commit()
    cp = client.get(url, headers=auth(requester)).json()
    late = [a for a in cp["alerts"] if a["kind"] == "projected_late"]
    assert [a["task_id"] for a in late] == [t["id"]] and "整件事会晚于截止" in late[0]["text"]
    step = [a for a in cp["alerts"] if a["kind"] == "estimate_past_deadline"]
    assert [a["task_id"] for a in step] == [path[1]] and {r["task_id"]: r for r in cp["timeline"]["rows"]}[path[1]]["late"]
    # 截止放宽到够用：两条预警都消失
    with SessionLocal() as db:
        db.get(Task, t["id"]).deadline = utcnow() + timedelta(days=60)
        db.get(Task, path[1]).deadline = utcnow() + timedelta(days=30)
        db.commit()
    cp = client.get(url, headers=auth(requester)).json()
    assert not any(a["kind"] in ("projected_late", "estimate_past_deadline") for a in cp["alerts"])


def test_estimates_are_set_while_decomposing_and_carried_to_the_steps(client, requester):
    t, dec = _propose(client, requester, category="软件开发", title="公司官网", description="响应式官网")
    first = dec["nodes"][0]
    assert first["est_days"] is None
    for bad in (0, 366):
        assert _patch(client, requester, dec, first["id"], est_days=bad).status_code == 422
    r = _patch(client, requester, dec, first["id"], est_days=4)
    assert r.status_code == 200, r.text
    dec = r.json()
    assert dec["nodes"][0]["est_days"] == 4
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 200, r.text
    child = next(c for c in r.json()["children"] if c["title"].endswith(first["title"]))
    assert child["est_days"] == 4
    assert all(c["est_days"] is None for c in r.json()["children"] if c["id"] != child["id"])
    # 任务编辑接口也拦超范围的值
    assert client.patch(f"/api/v1/tasks/{child['id']}", json={"est_days": 0}, headers=auth(requester)).status_code == 422
