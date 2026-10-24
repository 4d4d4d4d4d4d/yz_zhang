"""AGT-095 「我的方法」的效果统计（168 号 spec，V195）。

164 号让方法能套到新编排上，但方法好不好用看不到：只记了「用过几次」。现在每个方法写明按它拆过几个编排、
做成几个、没成几个、花了多少；做完的少于 3 个不给成功率（小样本的比率会误导人）。
"""
from app.core.db import SessionLocal
from app.modules.orchestrator.models import Mission
from tests.conftest import auth

STEPS = [{"title": "打包", "note": ""}, {"title": "搬运", "note": ""}]


def _method(client, u, name="我的搬家做法"):
    return client.post("/api/v1/notebook/methods", json={"name": name, "steps": STEPS}, headers=auth(u)).json()


def _mission(client, u, mid):
    r = client.post("/api/v1/missions", json={"goal": "搬家", "budget_cap_cents": 30000, "method_id": mid}, headers=auth(u))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _set(mission_id, status, spent=0):
    with SessionLocal() as db:
        m = db.get(Mission, mission_id)
        m.status, m.spent_cents = status, spent
        db.commit()


def _row(client, u, mid):
    return next(x for x in client.get("/api/v1/notebook/methods", headers=auth(u)).json() if x["id"] == mid)


def test_stats_count_outcomes_and_spend_and_hold_back_the_rate_on_small_samples(client, requester):
    m = _method(client, requester)
    ids = [_mission(client, requester, m["id"]) for _ in range(4)]
    _set(ids[0], "succeeded", 12000)
    _set(ids[1], "failed", 3000)
    row = _row(client, requester, m["id"])
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "NbMethod")
    assert (row["missions_total"], row["missions_succeeded"], row["missions_failed"], row["missions_spent_cents"]) == (4, 1, 1, 15000)
    assert row["success_rate"] is None, "做完的只有 2 个：不给成功率"
    _set(ids[2], "succeeded", 10000)
    row = _row(client, requester, m["id"])
    assert row["success_rate"] == 0.67 and row["missions_spent_cents"] == 25000
    _set(ids[3], "cancelled", 0)
    row = _row(client, requester, m["id"])
    assert row["missions_failed"] == 2 and row["success_rate"] == 0.5, "取消算没成"


def test_stats_are_per_method_and_new_methods_start_empty(client, requester, worker):
    a = _method(client, requester, "做法甲")
    b = _method(client, requester, "做法乙")
    theirs = _method(client, worker, "别人的做法")
    _set(_mission(client, requester, a["id"]), "succeeded", 5000)
    _set(_mission(client, worker, theirs["id"]), "succeeded", 9000)
    assert _row(client, requester, a["id"])["missions_total"] == 1
    assert _row(client, requester, b["id"])["missions_total"] == 0 and _row(client, requester, b["id"])["missions_spent_cents"] == 0
    assert b["missions_total"] == 0 and b["success_rate"] is None, "新建的方法响应里也带统计（形状一致）"
    assert _row(client, worker, theirs["id"])["missions_spent_cents"] == 9000
