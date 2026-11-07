"""AGT-097 方法按版本分开统计效果（239 号 spec，V266）。

168 号给了方法的成功率，但改过步骤之后新旧版本的结果混在一起算，看不出改了有没有变好。
现在改了步骤就升一版，编排记下用的是第几版，统计按版本分开。
"""
from app.core.db import SessionLocal
from app.modules.orchestrator.models import Mission
from tests.conftest import auth
from tests.test_method_stats import STEPS, _method, _mission, _row, _set

URL = "/api/v1/notebook/methods"


def test_only_step_changes_bump_the_version_and_missions_remember_it(client, requester):
    m = _method(client, requester)
    assert m["version"] == 1 and m["versions"] == []
    first = _mission(client, requester, m["id"])
    r = client.patch(f"{URL}/{m['id']}", json={"name": "新名字", "description": "说明", "steps": STEPS}, headers=auth(requester)).json()
    assert r["version"] == 1, "改名、改说明、步骤原样提交都不升版"
    r = client.patch(f"{URL}/{m['id']}", json={"steps": STEPS + [{"title": "验收", "note": ""}]}, headers=auth(requester)).json()
    assert r["version"] == 2
    second = client.post("/api/v1/missions", json={"goal": "搬家", "budget_cap_cents": 30000, "method_id": m["id"]}, headers=auth(requester)).json()
    assert second["method_version"] == 2
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(second, "Mission")
    with SessionLocal() as db:
        assert db.get(Mission, first).method_version == 1
    plain = client.post("/api/v1/missions", json={"goal": "不用方法", "budget_cap_cents": 30000}, headers=auth(requester)).json()
    assert plain["method_version"] is None


def test_stats_split_by_version_newest_first_and_legacy_last(client, requester):
    m = _method(client, requester)
    old = [_mission(client, requester, m["id"]) for _ in range(3)]
    for i, s in zip(old, ["succeeded", "failed", "failed"]):
        _set(i, s, 1000)
    client.patch(f"{URL}/{m['id']}", json={"steps": [{"title": "先列清单", "note": ""}] + STEPS}, headers=auth(requester))
    new = [_mission(client, requester, m["id"]) for _ in range(4)]
    for i, s in zip(new, ["succeeded", "succeeded", "succeeded", "cancelled"]):
        _set(i, s, 2000)
    legacy = _mission(client, requester, m["id"])
    with SessionLocal() as db:
        lm = db.get(Mission, legacy)
        lm.method_version, lm.status = None, "succeeded"      # 记版本之前建的编排，做成了一个
        db.commit()
    row = _row(client, requester, m["id"])
    assert row["missions_total"] == 8 and row["missions_succeeded"] == 5, "总数照旧把所有版本加在一起"
    assert [v["version"] for v in row["versions"]] == [2, 1, None]
    v2, v1, pre = row["versions"]
    assert (v2["missions_total"], v2["missions_succeeded"], v2["missions_failed"], v2["missions_spent_cents"], v2["success_rate"]) == (4, 3, 1, 8000, 0.75)
    assert (v1["missions_total"], v1["missions_succeeded"], v1["missions_failed"], v1["missions_spent_cents"], v1["success_rate"]) == (3, 1, 2, 3000, 0.33)
    assert (pre["missions_total"], pre["missions_succeeded"]) == (1, 1) and pre["success_rate"] is None, "做完的少于 3 个不给比率（按版本也一样）"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "NbMethod")
    _assert_shape(v2, "NbMethodVersionStats")
