"""AGT-094 「我的方法」套到新编排上作第一轮计划（164 号 spec，V187）。

154 号 spec 让编排复盘能蒸馏成「我的方法」，但方法只能套到工作台任务上：下次再做同样的事，
编排还是从头让 AI 拆一遍。现在发起编排时可以选一个自己的方法，第一轮就按它的步骤拆，不调模型。
"""
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.notebook.models import NbMethod
from tests.conftest import auth, topup

API = "/api/v1/missions"
STEPS = [{"title": "打包家具与易碎品", "note": "易碎品单独装箱并标记"}, {"title": "搬运上楼", "note": ""},
         {"title": "新家保洁", "note": "厨房卫生间重点"}]


def _method(client, u, steps=STEPS, name="我的搬家做法"):
    r = client.post("/api/v1/notebook/methods", json={"name": name, "steps": steps}, headers=auth(u))
    assert r.status_code == 201, r.text
    return r.json()


def _create(client, u, **kw):
    return client.post(API, json={"goal": "搬家整体统筹", "category": "跑腿", "budget_cap_cents": 30000,
                                  "max_iterations": 3, **kw}, headers=auth(u))


def test_first_round_follows_my_method_step_by_step(client, requester, monkeypatch):
    from app.modules.decompose import llm

    called = []
    monkeypatch.setattr(llm.TemplateLLM, "decompose", lambda *a, **k: called.append(1) or [])
    topup(client, requester, 100000)
    meth = _method(client, requester)
    r = _create(client, requester, method_id=meth["id"], budget_cap_cents=31000)   # 平分有零头
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["method_id"] == meth["id"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(m, "Mission")
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    steps = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]
    assert [s["title"] for s in steps] == [s["title"] for s in STEPS], "第一轮按方法的步骤、按顺序"
    assert called == [], "按方法拆就不再调分解网关"
    plan_budget = 31000 * (10000 - settings.ORC_PLAN_RESERVE_BPS) // 10000
    assert plan_budget % len(STEPS), "这个用例要有零头才验得到「零头给最后一步」"
    budgets = [s["budget_cents"] for s in steps]
    assert sum(budgets) == plan_budget and max(budgets) - min(budgets) < len(STEPS), "预算平分、零头给最后一步、总数守恒"
    task = client.get(f"/api/v1/tasks/{steps[0]['task_id']}", headers=auth(requester)).json()
    assert "易碎品单独装箱" in task["description"] and "我的搬家做法" in task["description"]
    assert steps[0]["acceptance"], "验收要点照旧兜底"
    with SessionLocal() as db:
        assert db.get(NbMethod, meth["id"]).uses == 1, "用了一次就记一次"


def test_someone_elses_method_is_404_and_missing_method_falls_back_visibly(client, requester, worker):
    theirs = _method(client, worker, name="别人的方法")
    r = _create(client, requester, method_id=theirs["id"])
    assert r.status_code == 404
    topup(client, requester, 100000)
    mine = _method(client, requester)
    m = _create(client, requester, method_id=mine["id"]).json()
    client.delete(f"/api/v1/notebook/methods/{mine['id']}", headers=auth(requester))
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    after = client.get(f"{API}/{m['id']}", headers=auth(requester)).json()
    assert after["steps"], "方法没了就退回 AI 分解，照样能拆"
    assert "方法已经删了" in after["last_error"], "换了拆法要说出来"


def test_long_methods_are_capped_and_without_method_nothing_changes(client, requester):
    from app.modules.orchestrator.service import METHOD_MAX_STEPS

    topup(client, requester, 200000)
    many = _method(client, requester, steps=[{"title": f"第 {i} 步", "note": ""} for i in range(METHOD_MAX_STEPS + 3)])
    m = _create(client, requester, method_id=many["id"]).json()
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    assert len(client.get(f"{API}/{m['id']}", headers=auth(requester)).json()["steps"]) == METHOD_MAX_STEPS
    plain = _create(client, requester).json()
    assert plain["method_id"] is None
