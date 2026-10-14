"""AGT-091 编排复盘（133 号 spec）：花了多少、几轮、哪些步骤整改过、评审分、经验工具草稿用了几份、下一步建议。"""
from tests.conftest import auth, topup
from tests.test_orchestrator import _finish_task, _mission

API = "/api/v1/missions"


def test_summary_after_a_remedy_and_success(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    topup(client, requester, 300000)
    m = _mission(client, requester, cap=200000, goal="装修验收统筹")
    running = client.get(f"{API}/{m['id']}/summary", headers=auth(requester)).json()
    assert running["steps_total"] == 0 and running["duration_days"] is None and "推进下一轮" in running["next"]
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    detail = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()
    first, rest = detail["steps"][0], detail["steps"][1:]
    client.post(f"/api/v1/tasks/{first['task_id']}/cancel", headers=auth(requester))
    for s in rest:
        _finish_task(client, requester, worker, s["task_id"])
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    remedy = [s for s in client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"] if s["is_remedy"]][0]
    _finish_task(client, requester, worker, remedy["task_id"])
    assert client.post(f"{API}/{m['id']}/tick", headers=auth(requester)).json()["status"] == "succeeded"
    s = client.get(f"{API}/{m['id']}/summary", headers=auth(requester)).json()
    _assert_shape(s, "MissionSummary")
    assert s["status"] == "succeeded" and s["steps_done"] == s["steps_total"] == len(detail["steps"])   # 被替代的那一步不算
    assert s["remedies"] == 1 and s["steps_failed"] == 0 and s["duration_days"] == 0
    assert any(h.startswith("达标") for h in s["highlights"]) and any(first["title"] in h for h in s["highlights"])
    assert "个人知识库" in s["next"] and s["spent_cents"] > 0 and s["cap_cents"] == 200000
    # 只有发起人（与管理员）能看
    assert client.get(f"{API}/{m['id']}/summary", headers=auth(worker)).status_code == 403
