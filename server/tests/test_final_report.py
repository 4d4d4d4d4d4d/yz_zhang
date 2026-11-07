"""AGT-090 母任务的结项报告上两端（132 号 spec）：实付按合约放款算（与合作驾驶舱同一口径）、是否全部完成。"""
from tests.conftest import auth, register, topup, verify_user
from tests.test_task_flow import match_and_fund


def _two_slots(client, requester):
    r = client.post("/api/v1/tasks", json={"ip_assignment": "assign", "title": "双人搬运", "category": "跑腿", "budget_cents": 20000,
                                           "is_remote": True, "people_needed": 2}, headers=auth(requester))
    return r.json(), r.json()["slots"]


def _close(client, requester, executor, slot, bid=None):
    match_and_fund(client, requester, executor, slot, bid=bid)
    client.post(f"/api/v1/tasks/{slot['id']}/deliver", headers=auth(executor))
    client.post(f"/api/v1/tasks/{slot['id']}/accept-delivery", headers=auth(requester))


def test_report_shows_real_payout_and_readiness(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_inline_shape

    topup(client, requester, 100000)
    second = register(client, "13100000012", "第二人")
    verify_user(client, second, "钱七")
    parent, slots = _two_slots(client, requester)
    _close(client, requester, worker, slots[0], bid=8000)          # 按报价成交：实付 80 元，低于这一名额的预算 100 元
    half = client.get(f"/api/v1/tasks/{parent['id']}/final-report", headers=auth(requester)).json()
    assert half["ready"] is False and half["paid_cents"] == 8000 and half["children_completed"] == 1
    _close(client, requester, second, slots[1])
    full = client.get(f"/api/v1/tasks/{parent['id']}/final-report", headers=auth(requester)).json()
    assert full["ready"] is True and full["paid_cents"] == 18000 and full["total_cost_cents"] == 20000   # 实付 ≠ 预算合计
    _assert_inline_shape(full, "finalReport")
    # 只有发布者看得到
    assert client.get(f"/api/v1/tasks/{parent['id']}/final-report", headers=auth(worker)).status_code in (403, 404)
