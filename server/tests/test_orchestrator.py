"""ORC 编排循环（Agent Harness）：任务发布=工具调用，验收结果=observation，
问题→自动生成修复步再分发，直至达标或触及护栏。

护栏是重点：agent 会自动花钱，必须有预算上限、迭代上限、人工停机，
且资金动作仍复用既有托管/守恒链路。
"""
from .conftest import JOB_HEADERS, auth, register, topup, verify_user
from .test_task_flow import match_and_fund


def _mission(client, owner, cap=30000, iters=3, goal="搬家整体统筹"):
    r = client.post("/api/v1/missions", json={
        "goal": goal, "detail": "含打包、搬运、保洁三段", "category": "跑腿",
        "budget_cap_cents": cap, "max_iterations": iters,
        "acceptance_criteria": ["物品无损", "现场清洁"],
    }, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()


def _finish_task(client, owner, worker, task_id):
    """把一个已发布任务走完整闭环（他人执行 → 验收放款）。"""
    task = client.get(f"/api/v1/tasks/{task_id}", headers=auth(owner)).json()
    match_and_fund(client, owner, worker, task)
    client.post(f"/api/v1/tasks/{task_id}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task_id}/accept-delivery", headers=auth(owner))


def test_tick_plans_and_dispatches_tasks_as_tool_calls(client, requester, worker):
    topup(client, requester, 200000)
    m = _mission(client, requester)
    assert m["status"] == "planning" and m["completion_pct"] == 0

    r = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester)).json()
    assert r["status"] == "running" and r["dispatched"] >= 1

    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    steps = detail["steps"]
    assert steps and all(s["tool"] == "publish_task" for s in steps)
    # 每一步都对应一个真实的、可被他人报名的已发布任务（工具的实现体）
    for s in steps:
        assert s["task_id"] and s["status"] == "dispatched"
        task = client.get(f"/api/v1/tasks/{s['task_id']}", headers=auth(worker)).json()
        assert task["status"] == "published" and task["creator_id"] == requester["id"]
    # 预算承诺不超过上限
    assert detail["spent_cents"] <= detail["budget_cap_cents"]


def test_loop_completes_when_all_steps_accepted(client, requester, worker):
    topup(client, requester, 300000)
    m = _mission(client, requester, goal="活动执行统筹")
    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()

    for s in detail["steps"]:
        _finish_task(client, requester, worker, s["task_id"])

    r = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester)).json()
    assert r["status"] == "succeeded" and r["completion_pct"] == 100
    assert r["done"] == r["total_steps"]
    # 结束后不可再推进
    r2 = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "mission_closed"


def test_failed_step_triggers_remedy_iteration(client, requester, worker):
    topup(client, requester, 300000)
    m = _mission(client, requester, cap=200000, goal="装修验收统筹")
    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    first, rest = detail["steps"][0], detail["steps"][1:]

    # 第一步流单（取消）→ 观测为失败，应触发修复步
    client.post(f"/api/v1/tasks/{first['task_id']}/cancel", headers=auth(requester))
    for s in rest:
        _finish_task(client, requester, worker, s["task_id"])

    r = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester)).json()
    # 失败步已被修复步接续（superseded），故 failed 归零、remedies 计数上升
    assert r["remedies"] >= 1 and r["superseded"] >= 1 and r["status"] == "running"

    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    remedy = [s for s in detail["steps"] if s["is_remedy"]]
    assert remedy and remedy[0]["title"].startswith("[修复]")
    assert remedy[0]["status"] == "dispatched" and remedy[0]["task_id"]
    assert detail["iteration"] == 1

    # 修复步完成 → 全部达标
    _finish_task(client, requester, worker, remedy[0]["task_id"])
    r = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester)).json()
    assert r["status"] == "succeeded"


def test_budget_cap_blocks_remedy_dispatch(client, requester):
    """ORC-004 预算护栏：规划已用满上限时，修复步会超支 → 挂起等待人工，而非继续烧钱。

    这正是 agent 自动重试最危险的地方：失败重发会不断追加真实支出。
    """
    topup(client, requester, 300000)
    m = _mission(client, requester, cap=100000, goal="超预算统筹")
    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    # 规划只用上限的 70%（其余为重试预留金）
    assert detail["spent_cents"] == detail["budget_cap_cents"] * 7 // 10

    # 全部流单 → 修复步总额（70%）超过剩余预留（30%）→ 挂起等待人工
    for s in detail["steps"]:
        client.post(f"/api/v1/tasks/{s['task_id']}/cancel", headers=auth(requester))
    r = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester)).json()
    assert r["status"] == "blocked" and "预算" in r["error"]

    after = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    assert after["spent_cents"] <= after["budget_cap_cents"]  # 绝不越过上限


def test_max_iterations_gives_up(client, requester):
    topup(client, requester, 300000)
    m = _mission(client, requester, cap=200000, iters=1, goal="迭代上限统筹")
    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()

    # 全部流单 → 第一轮生成修复步（iteration=1，已达上限）
    for s in detail["steps"]:
        client.post(f"/api/v1/tasks/{s['task_id']}/cancel", headers=auth(requester))
    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    # 修复步再次全部流单 → 触及迭代上限 → 放弃
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    for s in detail["steps"]:
        if s["status"] == "dispatched":
            client.post(f"/api/v1/tasks/{s['task_id']}/cancel", headers=auth(requester))
    r = client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester)).json()
    assert r["status"] == "failed" and "迭代上限" in \
        client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()["last_error"]


def test_cancel_mission_closes_open_tasks(client, requester):
    topup(client, requester, 200000)
    m = _mission(client, requester, cap=100000, goal="人工停机统筹")
    client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(requester))
    r = client.post(f"/api/v1/missions/{m['id']}/cancel", headers=auth(requester)).json()
    assert r["status"] == "cancelled" and r["closed_open_tasks"] >= 1
    detail = client.get(f"/api/v1/missions/{m['id']}", headers=auth(requester)).json()
    for s in detail["steps"]:
        if s["task_id"]:
            t = client.get(f"/api/v1/tasks/{s['task_id']}", headers=auth(requester)).json()
            assert t["status"] == "cancelled"


def test_mission_isolated_and_job_tick_requires_token(client, requester, worker):
    topup(client, requester, 100000)
    m = _mission(client, requester, cap=50000, goal="隔离性统筹")
    # 他人不可查看/推进
    assert client.get(f"/api/v1/missions/{m['id']}", headers=auth(worker)).status_code == 403
    assert client.post(f"/api/v1/missions/{m['id']}/tick", headers=auth(worker)).status_code == 403
    assert client.get("/api/v1/missions", headers=auth(worker)).json() == []
    # 心跳 job 需令牌
    assert client.post("/api/v1/missions/jobs/tick-all").status_code == 403
    assert client.post("/api/v1/missions/jobs/tick-all", headers=JOB_HEADERS).status_code == 200
