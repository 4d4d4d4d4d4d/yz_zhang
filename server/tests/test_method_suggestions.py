"""AGT-100 编排复盘起草方法备注的修改建议（251 号 spec，V278）。

245 号让修复步读方法里的备注；反方向还缺：这次哪一步整改过、缺了什么，没有回到方法里，下次照样踩坑。
现在复盘时按方法拆的、整改过的步骤会起草「方法备注改成什么」的建议；发起人勾选后才写回方法（升一版、旧版进历史）。
"""
from app.core.db import SessionLocal
from app.modules.orchestrator.models import Mission, MissionStep
from tests.conftest import auth, register, topup
from tests.test_mission_method import API, STEPS, _create, _method
from tests.test_remedy_method_notes import _fail_and_remedy


def _setup(client, requester):
    topup(client, requester, 100000)
    meth = _method(client, requester)
    m = _create(client, requester, method_id=meth["id"]).json()
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    with SessionLocal() as db:
        s = db.query(MissionStep).filter(MissionStep.mission_id == m["id"], MissionStep.title == STEPS[0]["title"]).one()
        s.review_missing = ["易碎品没有标记", "缺装箱照片"]
        db.commit()
    with SessionLocal() as db:                               # 第一步失败生成修复步，修复步做成了
        mm = db.get(Mission, m["id"])
        s = db.query(MissionStep).filter(MissionStep.mission_id == m["id"], MissionStep.title == STEPS[0]["title"]).one()
        s.status = "failed"
        db.flush()
        from app.modules.orchestrator import service

        service._make_remedy_steps(db, mm)
        r = db.query(MissionStep).filter(MissionStep.mission_id == m["id"], MissionStep.is_remedy == 1).one()
        r.status = "done"
        db.commit()
    _fail_and_remedy(m["id"], [STEPS[1]["title"]])            # 第二步失败、还没做成（没有缺项，写观测）
    return meth, m


def test_suggestions_are_drafts_and_apply_writes_back_as_a_new_version(client, requester):
    meth, m = _setup(client, requester)
    s = client.get(f"{API}/{m['id']}/method-suggestions", headers=auth(requester)).json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(s, "MissionMethodSuggestions")
    assert (s["method_id"], s["method_name"], s["method_version"]) == (meth["id"], "我的搬家做法", 1)
    by = {x["title"]: x for x in s["suggestions"]}
    assert set(by) == {STEPS[0]["title"], STEPS[1]["title"]}, "只有整改过的步骤；第三步一次做成不在里面"
    first = by[STEPS[0]["title"]]
    assert first["current_note"] == "易碎品单独装箱并标记"
    assert first["suggested_note"] == "易碎品单独装箱并标记；上次这一步没做到：易碎品没有标记、缺装箱照片"
    assert first["reason"] == "试了 2 次才做成"
    assert by[STEPS[1]["title"]]["suggested_note"].startswith("上次这一步没做成：") and by[STEPS[1]["title"]]["reason"] == "试了 2 次仍没做成"
    with SessionLocal() as db:                               # 只是草稿：方法没变
        from app.modules.notebook.models import NbMethod

        assert db.get(NbMethod, meth["id"]).version == 1
    r = client.post(f"{API}/{m['id']}/method-suggestions/apply", json={"titles": [STEPS[0]["title"]]}, headers=auth(requester))
    assert r.status_code == 200 and r.json()["version"] == 2
    assert r.json()["steps"][0]["note"] == first["suggested_note"] and r.json()["steps"][1]["note"] == ""
    h = client.get(f"/api/v1/notebook/methods/{meth['id']}/versions", headers=auth(requester)).json()
    assert h["versions"][0]["steps"][0]["note"] == "易碎品单独装箱并标记", "旧版进历史"
    again = client.get(f"{API}/{m['id']}/method-suggestions", headers=auth(requester)).json()
    assert [x["title"] for x in again["suggestions"]] == [STEPS[1]["title"]], "写过的不再建议"
    dup = client.post(f"{API}/{m['id']}/method-suggestions/apply", json={"titles": [STEPS[0]["title"]]}, headers=auth(requester))
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "method_suggestion_none"


def test_no_method_and_not_owner(client, requester):
    topup(client, requester, 100000)
    m = _create(client, requester).json()
    s = client.get(f"{API}/{m['id']}/method-suggestions", headers=auth(requester)).json()
    assert s["method_id"] is None and s["suggestions"] == [] and "没有用你的方法" in s["note"]
    other = register(client, "13800351001", "别人")
    assert client.get(f"{API}/{m['id']}/method-suggestions", headers=auth(other)).status_code in (403, 404)
    assert client.post(f"{API}/{m['id']}/method-suggestions/apply", json={"titles": ["x"]}, headers=auth(other)).status_code in (403, 404)


def test_admins_can_look_at_missions_but_not_rewrite_someone_elses_method(client, requester):
    from tests.conftest import make_admin

    meth, m = _setup(client, requester)
    boss = make_admin(client, "13800351011", "管理员")
    assert client.get(f"{API}/{m['id']}", headers=auth(boss)).status_code == 200, "管理员能看编排（排查用）"
    assert client.get(f"{API}/{m['id']}/method-suggestions", headers=auth(boss)).status_code == 403
    r = client.post(f"{API}/{m['id']}/method-suggestions/apply", json={"titles": [STEPS[0]["title"]]}, headers=auth(boss))
    assert r.status_code == 403, "方法只能本人改"
