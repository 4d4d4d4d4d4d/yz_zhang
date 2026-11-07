"""AI-DEC-021d（386 号 spec）开工以后接单人报「还要几天」，驾驶舱时间线按它重排。"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.task.cockpit import timeline
from app.modules.task.models import ProgressLog, Task
from tests.conftest import auth, topup
from tests.test_cockpit import _confirmed
from tests.test_task_flow import match_and_fund

NOW = utcnow()


def _n(i, deps, est=None, status="in_progress", deadline=None):
    return Task(id=i, depends_on=deps, status=status, title=str(i), est_days=est, deadline=deadline)


def test_the_latest_report_wins_over_the_estimate_and_pushes_the_next_step():
    # 1 估 2 天，但接单人昨天报「还要 5 天」：按报的排，2 接在后面
    reports = {1: (NOW - timedelta(days=1), 5)}
    plan = timeline([_n(1, [], 2), _n(2, [1], 3, status="draft")], NOW, reports)
    r = {x["task_id"]: x for x in plan["rows"]}
    assert r[1]["basis"] == "reported" and r[1]["end"] == NOW + timedelta(days=4)
    assert r[1]["reported_at"] == NOW - timedelta(days=1) and r[1]["days_left"] == 5
    assert r[2]["start"] == NOW + timedelta(days=4) and plan["projected_finish"] == NOW + timedelta(days=7)
    assert r[2]["reported_at"] is None and r[2]["days_left"] is None
    # 报的时间已经过了还没做完：按「现在」，不往回画
    r = {x["task_id"]: x for x in timeline([_n(1, [], 2)], NOW, {1: (NOW - timedelta(days=9), 2)})["rows"]}
    assert r[1]["end"] == NOW
    # 报的没填工期也照样排得出来；按报的赶不上自己截止也算晚
    r = {x["task_id"]: x for x in timeline([_n(1, [], None, deadline=NOW + timedelta(days=2))], NOW,
                                           {1: (NOW, 3)})["rows"]}
    assert r[1]["basis"] == "reported" and r[1]["late"]


def _running_step(client, requester, worker):
    topup(client, requester, 2_000_000)
    t = _confirmed(client, requester)
    cp = client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(requester)).json()
    first = cp["critical_path"][0]
    child = client.get(f"/api/v1/tasks/{first}", headers=auth(requester)).json()
    match_and_fund(client, requester, worker, child)
    assert client.get(f"/api/v1/tasks/{first}", headers=auth(requester)).json()["status"] == "in_progress"
    return t, first


def test_only_the_executor_reports_days_left_and_the_cockpit_follows(client, requester, worker):
    t, first = _running_step(client, requester, worker)
    url = f"/api/v1/tasks/{first}/progress"
    # 发单人不能替他报，但照样能写进度
    r = client.post(url, json={"content": "怎么样了", "days_left": 2}, headers=auth(requester))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "days_left_executor_only"
    assert client.post(url, json={"content": "怎么样了"}, headers=auth(requester)).status_code == 201
    for bad in (-1, 366):
        assert client.post(url, json={"content": "x", "days_left": bad}, headers=auth(worker)).status_code == 422
    assert client.post(url, json={"content": "页面做了一半", "days_left": 6}, headers=auth(worker)).status_code == 201
    assert client.post(url, json={"content": "加了个需求", "days_left": 9}, headers=auth(worker)).status_code == 201
    assert client.post(url, json={"content": "今天传了截图"}, headers=auth(worker)).status_code == 201
    logs = client.get(url, headers=auth(requester)).json()
    assert [x["days_left"] for x in logs] == [None, 6, 9, None]
    cp = client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(requester)).json()
    from tests.test_client_shape_alignment import _assert_shape
    row = {x["task_id"]: x for x in cp["timeline"]["rows"]}[first]
    _assert_shape(row, "CockpitTimelineRow")
    # 以最近一次报的为准（9 天），没带天数的那条不算
    assert row["basis"] == "reported" and row["days_left"] == 9 and row["reported_at"]
    # 这一步的截止只剩 3 天：按他报的赶不上，预警写清是接单人报的
    with SessionLocal() as db:
        db.get(Task, first).deadline = utcnow() + timedelta(days=3)
        db.commit()
    cp = client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(requester)).json()
    late = [a for a in cp["alerts"] if a["kind"] == "estimate_past_deadline" and a["task_id"] == first]
    assert late and "接单人报的还要 9 天" in late[0]["text"]


def test_reports_are_read_in_one_query_for_all_steps(client, requester, worker):
    """每一步最近一次报的天数一条查询取全，不按步骤逐个查（115 号闸门同一条要求）。"""
    from sqlalchemy import event

    from app.core.db import engine
    t, first = _running_step(client, requester, worker)
    with SessionLocal() as db:
        db.add(ProgressLog(task_id=first, user_id=worker["id"], kind="note", content="x", days_left=1))
        db.commit()
    seen = []

    def count(conn, cursor, statement, *a):
        if "progress_logs" in statement:
            seen.append(statement)
    event.listen(engine, "before_cursor_execute", count)
    try:
        assert client.get(f"/api/v1/tasks/{t['id']}/cockpit", headers=auth(requester)).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(seen) == 1, seen
