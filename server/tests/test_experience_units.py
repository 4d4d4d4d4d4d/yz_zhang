"""KB-080~089 / AGT-080~083 经验变成能被调用的工具（109 号 spec，设计见 95 号）。

用户 2026-10-10：「攒经验完全可以作为检索数据库或者 skilltool 工具给后续复用」。
"""
import ast
from pathlib import Path

import pytest

from app.core.db import SessionLocal
from app.vendors import registry
from tests.conftest import auth, make_admin, register
from tests.test_knowledge_clusters import SemanticStub

STEPS = [{"title": "接单确认"}, {"title": "取件"}, {"title": "送达拍照"}]


def _person(phone, nickname, consent):
    """样本里的人直接建在库里：一个子类要十来个真实参与方，走注册接口会撞注册限流。"""
    from app.core.security import create_token
    from app.modules.account.models import User
    from app.modules.legal import consent as consents

    with SessionLocal() as db:
        u = User(phone=phone, nickname=nickname, password_hash="x")
        db.add(u)
        db.flush()
        if consent:
            consents.grant(db, u.id, "experience_reuse")
        db.commit()
        return {"id": u.id, "nickname": nickname, "token": create_token(u.id)}


def _cluster(client, n=5, consent=True, category="跑腿", price=20000, phone_base=13800150000):
    """一个子类，n 个样本；每个样本是一单真实任务（发布方与执行方），可选双方都同意复用。"""
    from app.modules.knowledge.models import KnowledgeCard, KnowledgeCluster
    from app.modules.task.models import Task

    people = [(_person(str(phone_base + 2 * i), f"发布{i}", consent),
               _person(str(phone_base + 2 * i + 1), f"执行{i}", consent)) for i in range(n)]
    with SessionLocal() as db:
        cl = KnowledgeCluster(category=category, label=f"{category}·同城代取", embedding_model="stub-sem-3",
                              centroid=[1.0, 0.0, 0.0], sample_count=n, outcome_counts={"completed": n})
        db.add(cl)
        db.flush()
        cards = []
        for a, b in people:
            t = Task(creator_id=a["id"], executor_id=b["id"], title="t", category=category, city="杭州",
                     budget_cents=price, status="completed", is_remote=True)
            db.add(t)
            db.flush()
            c = KnowledgeCard(category=category, city="杭州", title=f"{category}·杭州", price_actual_cents=price,
                              outcome="completed", source_task_id=t.id, decomposition=STEPS,
                              embedding=[1.0, 0.0, 0.0], embedding_model="stub-sem-3",
                              cluster_id=cl.id, cluster_state="assigned")
            db.add(c)
            db.flush()
            cards.append(c.id)
        db.commit()
        return cl.id, cards, people


def _distill(client, admin, cid, **over):
    body = {"kind": "procedure", "exclusions": ["老小区没电梯且要搬大件"], "reuse_license": True,
            "train_license": False, **over}
    return client.post(f"/api/v1/admin/knowledge/clusters/{cid}/units", json=body, headers=auth(admin))


# ------------------------------------------------------------------ KB-080a 注册门槛
def test_kb080a_a_unit_needs_exclusions_a_consented_source_and_both_licenses(client):
    admin = make_admin(client, "13800150900")
    cid, _cards, _p = _cluster(client)
    r = _distill(client, admin, cid, exclusions=[])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unit_exclusions_required"
    r = client.post(f"/api/v1/admin/knowledge/clusters/{cid}/units",
                    json={"kind": "procedure", "exclusions": ["x"], "reuse_license": True}, headers=auth(admin))
    assert r.status_code == 422, "两个授权位都必须明说，缺一个不许注册"
    no_consent, _c, _p = _cluster(client, consent=False, phone_base=13800151000)
    r = _distill(client, admin, no_consent)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "unit_no_consented_source"


def test_kb080a_only_samples_where_both_parties_consented_are_sources(client):
    admin = make_admin(client, "13800150901")
    cid, cards, people = _cluster(client, n=3)
    # 第三单的执行方从没同意过：那一单不能作来源
    with SessionLocal() as db:
        from app.modules.legal.consent import UserConsent

        db.query(UserConsent).filter(UserConsent.user_id == people[2][1]["id"]).delete()
        db.commit()
    r = _distill(client, admin, cid)
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["sample_count"] == 2 and u["validation"]["status"] == "unvalidated"
    assert u["applicability"]["exclusions"] == ["老小区没电梯且要搬大件"]
    names = {c["nickname"] for c in u["contributors"]}
    assert "执行2" not in names and {"发布0", "执行0", "发布1", "执行1"} <= names


def test_price_hint_needs_enough_samples(client):
    admin = make_admin(client, "13800150902")
    cid, _c, _p = _cluster(client, n=2, phone_base=13800151100)
    r = _distill(client, admin, cid, kind="price_hint")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "unit_too_few_samples"


# ------------------------------------------------------------------ KB-086/087 两个授权位
def test_reuse_and_train_licenses_are_independent(client):
    admin = make_admin(client, "13800150903")
    cid, _c, _p = _cluster(client, phone_base=13800151200)
    no_reuse = _distill(client, admin, cid, kind="checklist", reuse_license=False, train_license=True).json()
    reuse = _distill(client, admin, cid, kind="checklist", reuse_license=True, train_license=False).json()
    listed = {u["id"] for u in client.get("/api/v1/knowledge/units", params={"cluster_id": cid}).json()}
    assert reuse["id"] in listed and no_reuse["id"] not in listed, "没有复用授权的单元不许被复用（训练授权替代不了它）"
    assert client.get(f"/api/v1/knowledge/units/{no_reuse['id']}").status_code == 404, "读内容就是复用"
    assert client.get(f"/api/v1/knowledge/units/{reuse['id']}").json()["train_license"] is False


def test_only_platform_scope_until_units_have_an_owner(client):
    """「仅自己 / 项目内」没有归属对象就执行不了：收下等于把私有单元公开。"""
    admin = make_admin(client, "13800150913")
    cid, _c, _p = _cluster(client, phone_base=13800152400)
    for scope in ("private", "project"):
        r = _distill(client, admin, cid, scope=scope)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "unit_scope_invalid"
        # KB-093（309 号 spec）说清为什么、去哪里：只想自己用的去个人知识库 / 我的方法；项目内还不开放
        msg = r.json()["detail"]["message"]
        assert ("个人知识库" in msg and "我的方法" in msg) if scope == "private" else ("协作空间还是母任务" in msg and "全平台" in msg)


# ------------------------------------------------------------------ KB-083/084 计量与回流
def _project(client, user, category="跑腿", budget=300000):
    r = client.post("/api/v1/tasks", json={
        "title": "帮我把一批货同城送到", "description": "", "category": category, "task_type": "project",
        "budget_cents": budget, "is_remote": True, "city": "杭州", "publish_now": False,
        "ip_assignment": "assign"}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def _invocations(unit_id):
    from app.modules.knowledge.models import UnitInvocation

    with SessionLocal() as db:
        return [(i.scenario, i.task_id, i.outcome) for i in
                db.query(UnitInvocation).filter_by(unit_id=unit_id).order_by(UnitInvocation.id)]


def test_kb083_procedure_units_drive_decomposition_and_every_use_is_metered(client):
    admin = make_admin(client, "13800150904")
    cid, _c, _p = _cluster(client, phone_base=13800151300)
    unit = _distill(client, admin, cid).json()
    boss = register(client, "13800150990")
    task = _project(client, boss)
    dec = client.post(f"/api/v1/tasks/{task['id']}/decompositions", headers=auth(boss)).json()
    assert dec["source"] == f"experience_unit:{unit['id']}@v1"
    assert [n["title"] for n in dec["nodes"]] == ["接单确认", "取件", "送达拍照"]
    assert all(n["leaf"] for n in dec["nodes"]), "流程单元的每一步都带交付物与验收标准"
    assert _invocations(unit["id"]) == [("decompose", task["id"], "pending")]


def test_kb084_outcomes_flow_back_and_bad_units_go_to_review(client, monkeypatch):
    from app.core.config import settings
    from app.modules.knowledge import units
    from app.modules.knowledge.models import ReusableUnit

    monkeypatch.setattr(settings, "KB_UNIT_REVIEW_MIN_USES", 2)
    admin = make_admin(client, "13800150905")
    cid, _c, _p = _cluster(client, phone_base=13800151400)
    unit = _distill(client, admin, cid).json()
    boss = register(client, "13800150991")
    for _ in range(2):
        t = _project(client, boss)
        client.post(f"/api/v1/tasks/{t['id']}/decompositions", headers=auth(boss))
        with SessionLocal() as db:
            units.settle(db, t["id"], "failed")
            db.commit()
    with SessionLocal() as db:
        u = db.get(ReusableUnit, unit["id"])
        assert u.validation["uses"] == 2 and u.validation["failed"] == 2
        assert u.status == "needs_review", "返工与失败过半：单元自己转待复核"
    # 待复核的单元不再被拿去拆解
    t = _project(client, boss)
    dec = client.post(f"/api/v1/tasks/{t['id']}/decompositions", headers=auth(boss)).json()
    assert not dec["source"].startswith("experience_unit:")
    review = client.get("/api/v1/admin/knowledge/units", params={"status": "needs_review"}, headers=auth(admin)).json()
    assert unit["id"] in {r["id"] for r in review}


def test_kb084_a_cancelled_task_is_a_failure_of_the_unit_it_used(client):
    """事件路径：真的取消一单，调用记录变成 failed。"""
    admin = make_admin(client, "13800150906")
    cid, _c, _p = _cluster(client, phone_base=13800151500)
    unit = _distill(client, admin, cid).json()
    boss = register(client, "13800150992")
    t = _project(client, boss)
    client.post(f"/api/v1/tasks/{t['id']}/decompositions", headers=auth(boss))
    from app.core.events import publish
    from app.modules.knowledge.units import _on_task_cancelled

    with SessionLocal() as db:
        _on_task_cancelled(db, {"task_id": t["id"]})
        db.commit()
    assert _invocations(unit["id"])[-1][2] == "failed"
    assert publish  # 事件总线在（订阅在 main 里注册）


def test_reactivate_after_review_bumps_the_version_and_restarts_validation(client):
    from app.modules.knowledge.models import ReusableUnit

    admin = make_admin(client, "13800150907")
    cid, _c, _p = _cluster(client, phone_base=13800151600)
    unit = _distill(client, admin, cid).json()
    with SessionLocal() as db:
        u = db.get(ReusableUnit, unit["id"])
        u.status, u.validation = "needs_review", {"status": "needs_review", "uses": 9, "failed": 9}
        db.commit()
    r = client.patch(f"/api/v1/admin/knowledge/units/{unit['id']}", json={"status": "active", "note": "改了第二步"},
                     headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2 and r.json()["validation"]["uses"] == 0, "复核前的结果属于上一版"


# ------------------------------------------------------------------ KB-088 / AGT-080~083 工具
@pytest.fixture()
def semantic(monkeypatch):
    monkeypatch.setitem(registry._instances, "embedding", SemanticStub())
    yield
    registry._instances.pop("embedding", None)


def _tool_unit(client, admin, base):
    cid, _c, _p = _cluster(client, phone_base=base)
    r = _distill(client, admin, cid, kind="skill_tool", tool="acceptance_report_draft")
    assert r.status_code == 201, r.text
    assert r.json()["manifest"]["spends"] is False and r.json()["manifest"]["writes"] == ["draft"]
    return r.json()


def _plain_task(client, owner, category="跑腿"):
    r = client.post("/api/v1/tasks", json={
        "title": "代取快递", "description": "", "category": category, "task_type": "service",
        "budget_cents": 20000, "is_remote": True, "city": "杭州", "publish_now": False,
        "ip_assignment": "assign"}, headers=auth(owner))
    assert r.status_code == 201, r.text
    return r.json()


def test_agt083_tool_output_is_a_labelled_discardable_draft(client, semantic):
    admin = make_admin(client, "13800150908")
    unit = _tool_unit(client, admin, 13800151700)
    owner = register(client, "13800150993")
    t = _plain_task(client, owner)
    r = client.post(f"/api/v1/agent/tools/{unit['id']}/invoke", json={"task_id": t["id"]}, headers=auth(owner))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["draft"] is True and "未经人工确认" in out["label"] and "未经人工确认" in out["text"]
    assert "☐ 确认已完成：取件" in out["text"] and "老小区没电梯" in out["text"], "排除条件跟着草稿走"
    assert out["contributors"] == 10
    other = register(client, "13800150994")
    assert client.post(f"/api/v1/agent/tools/invocations/{out['invocation_id']}/discard",
                       headers=auth(other)).status_code == 403
    d = client.post(f"/api/v1/agent/tools/invocations/{out['invocation_id']}/discard", headers=auth(owner))
    assert d.status_code == 200 and d.json()["discarded"] is True
    assert _invocations(unit["id"]) == [("agent_tool", t["id"], "pending")]


def test_tool_guards(client, semantic, monkeypatch):
    from app.core.config import settings

    admin = make_admin(client, "13800150909")
    unit = _tool_unit(client, admin, 13800151800)
    owner = register(client, "13800150995")
    stranger = register(client, "13800150996")
    t = _plain_task(client, owner)
    url = f"/api/v1/agent/tools/{unit['id']}/invoke"
    assert client.post(url, json={"task_id": t["id"]}, headers=auth(stranger)).status_code == 403
    other_cat = _plain_task(client, owner, category="保洁")
    r = client.post(url, json={"task_id": other_cat["id"]}, headers=auth(owner))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "tool_not_applicable"
    monkeypatch.setattr(settings, "KB_TOOL_MAX_COST_CENTS", -1)
    r = client.post(url, json={"task_id": t["id"]}, headers=auth(owner))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "tool_over_budget"


def test_tools_are_off_in_degraded_mode(client):
    """缺省词袋哈希不是语义模型：只读单元可用，可执行的不行（95 号第 6 节）。"""
    admin = make_admin(client, "13800150910")
    unit = _tool_unit(client, admin, 13800151900)
    owner = register(client, "13800150997")
    t = _plain_task(client, owner)
    r = client.post(f"/api/v1/agent/tools/{unit['id']}/invoke", json={"task_id": t["id"]}, headers=auth(owner))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "tool_degraded"


def test_agt081_tools_and_units_never_touch_money_contracts_or_rights():
    base = Path(__file__).resolve().parents[1] / "app" / "modules" / "knowledge"
    forbidden = ("app.modules.wallet", "app.modules.contract", "app.vendors.payment",
                 "app.modules.finance", "app.modules.coop")
    for name in ("tools.py", "units.py"):
        tree = ast.parse((base / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = ([node.module] if isinstance(node, ast.ImportFrom) and node.module else
                    [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for m in mods:
                assert not m.startswith(forbidden), f"{name} import 了 {m}：经验工具不许碰钱、签约、权益"


# ------------------------------------------------------------------ KB-089 撤回
def test_kb089_revoking_reuse_really_changes_stats_units_and_drafts(client, semantic):
    from app.modules.knowledge.models import KnowledgeCard, KnowledgeCluster, ReusableUnit, UnitInvocation

    admin = make_admin(client, "13800150911")
    cid, cards, people = _cluster(client, phone_base=13800152000)
    unit = _distill(client, admin, cid, kind="skill_tool", tool="acceptance_report_draft").json()
    owner = register(client, "13800150998")
    t = _plain_task(client, owner)
    inv = client.post(f"/api/v1/agent/tools/{unit['id']}/invoke", json={"task_id": t["id"]},
                      headers=auth(owner)).json()["invocation_id"]
    leaver = people[0][1]
    r = client.post("/api/v1/legal/consents/experience_reuse/revoke", headers=auth(leaver))
    assert r.status_code == 200, r.text
    assert any(a.startswith("units_to_review") for a in r.json()["applied"])
    with SessionLocal() as db:
        assert db.get(KnowledgeCard, cards[0]).cluster_state == "retracted"
        assert db.get(KnowledgeCluster, cid).sample_count == 4, "退出子类统计（重算过）"
        u = db.get(ReusableUnit, unit["id"])
        assert u.status == "needs_review" and cards[0] not in u.sample_ids
        assert db.get(UnitInvocation, inv).source_revoked is True, "草稿不追回，但标出来源已撤回"
    names = {c["nickname"] for c in client.get(f"/api/v1/knowledge/units/{unit['id']}").json()["contributors"]}
    assert leaver["nickname"] not in names


def test_kb089_people_who_never_opted_in_can_still_opt_out(client):
    from app.modules.knowledge.models import KnowledgeCard

    cid, cards, people = _cluster(client, n=2, consent=False, phone_base=13800152100)
    r = client.post("/api/v1/legal/consents/experience_reuse/revoke", headers=auth(people[1][0]))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(KnowledgeCard, cards[1]).cluster_state == "retracted"


def test_consent_status_lists_the_two_data_uses_separately(client):
    u = register(client, "13800150999")
    st = client.get("/api/v1/legal/consents", headers=auth(u))
    if st.status_code == 404:
        st = client.get("/api/v1/legal/agreements", headers=auth(u))
    body = st.json()
    keys = {s["key"] for s in body["data_use_scopes"]}
    assert keys == {"experience_reuse", "experience_train"}
    assert all(not s["granted"] for s in body["data_use_scopes"]), "选择加入：默认没同意"
    assert not {s["key"] for s in body["sensitive_scopes"]} & keys, "它们不是敏感个人信息，单列"


def test_unit_responses_match_the_sdk_declarations(client, semantic):
    from tests.test_client_shape_alignment import _assert_shape

    admin = make_admin(client, "13800150912")
    cid, _c, _p = _cluster(client, phone_base=13800152200)
    created = _distill(client, admin, cid).json()
    _assert_shape(created, "ReusableUnitDetail")
    lst = client.get("/api/v1/knowledge/units").json()
    _assert_shape(lst[0], "ReusableUnit")
    _assert_shape(client.get(f"/api/v1/knowledge/units/{created['id']}").json(), "ReusableUnitDetail")
    tool = _tool_unit(client, admin, 13800152300)
    owner = register(client, "13800152999")
    t = _plain_task(client, owner)
    out = client.post(f"/api/v1/agent/tools/{tool['id']}/invoke", json={"task_id": t["id"]}, headers=auth(owner)).json()
    _assert_shape(out, "ExperienceToolDraft")
