"""AGT-084 / REL-110 编排调用平台经验工具、助手只读检索经验、每月助手成本上限（131 号 spec）。

来源：109 号 spec「这两个调用方今天都还不存在（编排器调用是 AGT-084）」；111 号 spec 的设计：
按步骤给工具白名单、写草稿的工具要发布方授权、草稿挂在步骤上等人确认、审计记 agent 身份 + 授权人 + 工具 + 版本 + 结果。
"""
import json

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.knowledge.models import ReusableUnit, UnitInvocation
from app.modules.orchestrator.models import MissionEvent, MissionStep
from app.modules.packs import service as psvc
from app.modules.workbench.models import WbRoutineRun
from tests.conftest import auth, make_admin, topup
from tests.test_experience_units import _tool_unit, semantic  # noqa: F401  （pytest 夹具）

API = "/api/v1"


def _usable_everywhere(unit_id):
    """测试里的单元来自杭州的样本；编排发的单是线上的、没有城市——放宽成只看类目。"""
    with SessionLocal() as db:
        u = db.get(ReusableUnit, unit_id)
        u.applicability = {**(u.applicability or {}), "cities": [], "budget_min_cents": None, "budget_max_cents": None}
        db.commit()


def _mission(client, owner, allow_tools=True):
    r = client.post(f"{API}/missions", json={"goal": "搬家整体统筹", "detail": "含打包、搬运", "category": "跑腿",
                                             "budget_cap_cents": 30000, "max_iterations": 3, "allow_tools": allow_tools},
                    headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()


def _steps(client, owner, mid):
    return client.get(f"{API}/missions/{mid}", headers=auth(owner)).json()["steps"]


# ------------------------------------------------------------------ AGT-084 编排调用经验工具
def test_authorised_mission_attaches_tool_drafts_with_an_audit_trail(client, requester, semantic):  # noqa: F811
    admin = make_admin(client, "13800152901")
    unit = _tool_unit(client, admin, 13800152000)
    _usable_everywhere(unit["id"])
    topup(client, requester, 200000)
    m = _mission(client, requester)
    assert m["allow_tools"] is True
    client.post(f"{API}/missions/{m['id']}/tick", headers=auth(requester))
    steps = _steps(client, requester, m["id"])
    drafted = [s for s in steps if s["tool_drafts"]]
    assert drafted, steps
    d = drafted[0]["tool_drafts"][0]
    assert d["status"] == "pending" and d["unit_id"] == unit["id"] and "未经人工确认" in d["text"] and d["version"] == unit["version"]
    with SessionLocal() as db:
        inv = db.get(UnitInvocation, d["invocation_id"])
        assert inv.caller_id == requester["id"] and inv.draft and not inv.adopted        # 授权人 + 只是草稿
        assert inv.agent == f"orchestrator:mission#{m['id']}:step#{drafted[0]['id']}"   # agent 身份
        assert inv.version == unit["version"] and inv.task_id == drafted[0]["task_id"]
        assert any("等你确认" in e.summary for e in db.query(MissionEvent).filter_by(mission_id=m["id"]))
    # 采用：只是标记，不发给任何人；再处理一次说清楚
    url = f"{API}/missions/{m['id']}/steps/{drafted[0]['id']}/drafts/{d['invocation_id']}"
    r = client.post(f"{url}/adopt", headers=auth(requester)).json()
    assert r["status"] == "adopted"
    again = client.post(f"{url}/discard", headers=auth(requester))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "draft_already_decided"
    with SessionLocal() as db:
        assert db.get(UnitInvocation, d["invocation_id"]).adopted is True


def test_without_authorisation_no_tool_is_called(client, requester, semantic):  # noqa: F811
    admin = make_admin(client, "13800152902")
    unit = _tool_unit(client, admin, 13800152100)
    _usable_everywhere(unit["id"])
    topup(client, requester, 200000)
    m = _mission(client, requester, allow_tools=False)
    client.post(f"{API}/missions/{m['id']}/tick", headers=auth(requester))
    assert all(s["tool_drafts"] == [] for s in _steps(client, requester, m["id"]))
    with SessionLocal() as db:
        assert db.query(UnitInvocation).filter(UnitInvocation.agent != "").count() == 0


def test_only_the_owner_can_toggle_and_decide(client, requester, worker, semantic):  # noqa: F811
    admin = make_admin(client, "13800152903")
    unit = _tool_unit(client, admin, 13800152200)
    _usable_everywhere(unit["id"])
    topup(client, requester, 200000)
    m = _mission(client, requester, allow_tools=False)
    assert client.put(f"{API}/missions/{m['id']}/tools", json={"allow_tools": True}, headers=auth(worker)).status_code == 403
    # 管理员看得到别人的编排，但不能替人授权
    assert client.put(f"{API}/missions/{m['id']}/tools", json={"allow_tools": True}, headers=auth(admin)).status_code == 403
    assert client.put(f"{API}/missions/{m['id']}/tools", json={"allow_tools": True}, headers=auth(requester)).json()["allow_tools"] is True
    client.post(f"{API}/missions/{m['id']}/tick", headers=auth(requester))
    s = next(x for x in _steps(client, requester, m["id"]) if x["tool_drafts"])
    url = f"{API}/missions/{m['id']}/steps/{s['id']}/drafts/{s['tool_drafts'][0]['invocation_id']}"
    assert client.post(f"{url}/discard", headers=auth(worker)).status_code == 403
    assert client.post(f"{API}/missions/{m['id']}/steps/{s['id']}/drafts/999999/adopt", headers=auth(requester)).status_code == 404
    assert client.post(f"{url}/discard", headers=auth(requester)).json()["status"] == "discarded"
    with SessionLocal() as db:
        assert db.get(UnitInvocation, s["tool_drafts"][0]["invocation_id"]).discarded is True


def test_degraded_mode_skips_tools_but_still_dispatches(client, requester):
    admin = make_admin(client, "13800152904")
    unit = _tool_unit(client, admin, 13800152300)
    _usable_everywhere(unit["id"])
    topup(client, requester, 200000)
    m = _mission(client, requester)
    client.post(f"{API}/missions/{m['id']}/tick", headers=auth(requester))
    steps = _steps(client, requester, m["id"])
    sent = [s for s in steps if s["task_id"]]
    assert sent and all(s["tool_drafts"] == [] for s in steps)            # 照常分发，只是不用工具
    with SessionLocal() as db:
        assert any("没用上" in e.summary for e in db.query(MissionEvent).filter_by(mission_id=m["id"]))


# ------------------------------------------------------------------ REL-110 每月助手成本上限
def test_monthly_cost_cap_stops_agent_calls_and_is_visible(client, requester, semantic, monkeypatch):  # noqa: F811
    admin = make_admin(client, "13800152905")
    unit = _tool_unit(client, admin, 13800152400)
    _usable_everywhere(unit["id"])
    with SessionLocal() as db:
        db.get(ReusableUnit, unit["id"]).est_cost_cents = 30
        db.add(WbRoutineRun(routine_id=1, owner_id=requester["id"], status="ok", output="", cost_cents=5))
        db.commit()
    monkeypatch.setattr(settings, "AGENT_MONTHLY_COST_CAP_CENTS", 34)
    topup(client, requester, 200000)
    m = _mission(client, requester)
    client.post(f"{API}/missions/{m['id']}/tick", headers=auth(requester))
    assert [d for s in _steps(client, requester, m["id"]) for d in s["tool_drafts"]] == []   # 5 + 30 > 34
    with SessionLocal() as db:
        assert any("本月助手成本已到上限" in e.summary for e in db.query(MissionEvent).filter_by(mission_id=m["id"]))
    c = client.get(f"{API}/users/me/assistant-costs", headers=auth(requester)).json()
    assert (c["agent_tools_cents"], c["routines_cents"], c["total_cents"], c["cap_cents"], c["remaining_cents"], c["agent_calls"]) == (0, 5, 5, 34, 29, 0)
    # 上限放宽到 35：刚好够，这一次就调了，并计入本月
    monkeypatch.setattr(settings, "AGENT_MONTHLY_COST_CAP_CENTS", 35)
    m2 = _mission(client, requester)
    client.post(f"{API}/missions/{m2['id']}/tick", headers=auth(requester))
    assert len([d for s in _steps(client, requester, m2["id"]) for d in s["tool_drafts"]]) == 1
    c = client.get(f"{API}/users/me/assistant-costs", headers=auth(requester)).json()
    assert (c["agent_tools_cents"], c["total_cents"], c["remaining_cents"], c["agent_calls"]) == (30, 35, 0, 1)
    assert len(c["month"]) == 7


def test_people_clicking_the_button_do_not_count_against_the_agent_cap(client, requester, semantic):  # noqa: F811
    with SessionLocal() as db:
        db.add(UnitInvocation(unit_id=1, version=1, scenario="agent_tool", caller_id=requester["id"], cost_cents=99, agent=""))
        db.commit()
    assert client.get(f"{API}/users/me/assistant-costs", headers=auth(requester)).json()["agent_tools_cents"] == 0


# ------------------------------------------------------------------ 助手只读检索经验
def test_pack_assistant_cites_experience_units_read_only(client, requester, semantic):  # noqa: F811
    admin = make_admin(client, "13800152906")
    unit = _tool_unit(client, admin, 13800152500)
    a, b = make_admin(client, "13800152907", "运营甲"), make_admin(client, "13800152908", "运营乙")
    seed = json.loads((psvc.SEEDS / "collab-basics.json").read_text(encoding="utf-8"))
    assert "experience.search" in seed["assistants"][0]["tools"]
    pid = client.post(f"{API}/admin/packs", json={"definition": seed}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200
    with SessionLocal() as db:
        before = db.query(UnitInvocation).count()
    r = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": unit["title"]}, headers=auth(requester)).json()
    exp = [c for c in r["citations"] if c["kind"] == "experience"]
    assert exp and exp[0]["title"] == unit["title"] and "平台经验（第" in exp[0]["source"]
    with SessionLocal() as db:
        assert db.query(UnitInvocation).count() == before          # 只读引用，不算一次调用
    _ = admin, MissionStep


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, requester, semantic):  # noqa: F811
    from tests.test_client_shape_alignment import _assert_shape

    admin = make_admin(client, "13800152909")
    unit = _tool_unit(client, admin, 13800152600)
    _usable_everywhere(unit["id"])
    topup(client, requester, 200000)
    m = _mission(client, requester)
    _assert_shape(m, "Mission")
    client.post(f"{API}/missions/{m['id']}/tick", headers=auth(requester))
    s = next(x for x in _steps(client, requester, m["id"]) if x["tool_drafts"])
    _assert_shape(s, "MissionStep")
    first_draft = s["tool_drafts"][0]
    _assert_shape(first_draft, "MissionToolDraft")
    decided = client.post(f"{API}/missions/{m['id']}/steps/{s['id']}/drafts/{first_draft['invocation_id']}/adopt",
                          headers=auth(requester)).json()
    _assert_shape(decided, "MissionDraftDecision")
    toggled = client.put(f"{API}/missions/{m['id']}/tools", json={"allow_tools": False}, headers=auth(requester)).json()
    _assert_shape(toggled, "Mission")
    costs = client.get(f"{API}/users/me/assistant-costs", headers=auth(requester)).json()
    _assert_shape(costs, "AssistantCosts")
