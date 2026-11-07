"""AGT-096 修复步也参考方法里的备注（245 号 spec，V272）。

164 号让方法决定编排的第一轮；某一步失败后生成的修复步只写通用的「上一轮没完成 / 补齐缺什么」，
不看方法里这一步的备注。现在按方法拆的步骤失败了，修复步的整改要求里带上方法里这一步的备注，
而且读最新的——失败后发起人往方法里补的提醒，下一轮就用得上。
"""
from app.core.db import SessionLocal
from app.modules.orchestrator import service
from app.modules.orchestrator.models import Mission, MissionStep
from tests.conftest import auth, topup
from tests.test_mission_method import API, STEPS, _create, _method


def _fail_and_remedy(mission_id: int, titles: list[str]) -> dict[str, str]:
    with SessionLocal() as db:
        m = db.get(Mission, mission_id)
        for s in db.query(MissionStep).filter(MissionStep.mission_id == mission_id, MissionStep.title.in_(titles)):
            s.status, s.review_missing = "failed", []
        db.flush()
        made = service._make_remedy_steps(db, m)
        out = {r.title: r.args["description"] for r in made}
        db.commit()
    return out


def test_remedy_carries_the_latest_method_note_for_that_step(client, requester):
    topup(client, requester, 100000)
    meth = _method(client, requester)
    m = _create(client, requester, method_id=meth["id"]).json()
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    # 失败之后，发起人往方法里补了一句提醒（改了步骤 → 第 2 版）
    new_steps = [{**STEPS[0], "note": "易碎品单独装箱并标记；电视要原包装"}] + STEPS[1:]
    client.patch(f"/api/v1/notebook/methods/{meth['id']}", json={"steps": new_steps}, headers=auth(requester))
    got = _fail_and_remedy(m["id"], [STEPS[0]["title"], STEPS[1]["title"]])
    first = got[STEPS[0]["title"]]
    assert "【本轮整改要求】" in first
    tail = first.split("【本轮整改要求】", 1)[1]
    assert "按你的方法「我的搬家做法」，这一步要注意：易碎品单独装箱并标记；电视要原包装" in tail, "读最新的备注"
    assert "方法已从第 1 版改到第 2 版，按最新的备注" in tail
    assert "按你的方法" not in got[STEPS[1]["title"]], "这一步方法里没写备注：不加"


def test_without_method_remedy_is_unchanged(client, requester):
    topup(client, requester, 100000)
    m = _create(client, requester).json()
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    with SessionLocal() as db:
        title = db.query(MissionStep).filter(MissionStep.mission_id == m["id"]).first().title
    got = _fail_and_remedy(m["id"], [title])
    assert "按你的方法" not in got[title] and "上一轮未能完成" in got[title]


def test_unchanged_method_has_no_version_remark_and_deleted_method_is_ignored(client, requester):
    topup(client, requester, 100000)
    meth = _method(client, requester)
    m = _create(client, requester, method_id=meth["id"]).json()
    client.post(f"{API}/{m['id']}/tick", headers=auth(requester))
    got = _fail_and_remedy(m["id"], [STEPS[2]["title"]])
    tail = got[STEPS[2]["title"]].split("【本轮整改要求】", 1)[1]
    assert "这一步要注意：厨房卫生间重点" in tail and "版改到第" not in tail
    m2 = _create(client, requester, method_id=meth["id"]).json()
    client.post(f"{API}/{m2['id']}/tick", headers=auth(requester))
    client.delete(f"/api/v1/notebook/methods/{meth['id']}", headers=auth(requester))
    got = _fail_and_remedy(m2["id"], [STEPS[0]["title"]])
    assert "按你的方法" not in got[STEPS[0]["title"]].split("【本轮整改要求】", 1)[1], "方法删了就不加（不报错）"
