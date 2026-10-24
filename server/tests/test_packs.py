"""PACK-100~109 场景包与平台资产（123 号 spec）。

用户原话：「场景千变万化，可以提炼一些方法或者 skill 或者工作流……快速发掘并部署方法到这个平台上……
本身这些 agent、skill、知识库就是平台重要的资产之一。」
"""
import copy
import json
from datetime import timedelta


from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit
from app.modules.analytics.models import SearchQuery
from app.modules.notebook.models import NbMethod, NbNote
from app.modules.packs import schema
from app.modules.packs import service as svc
from app.modules.packs.models import PackEnrollment, PackEvent
from app.modules.task.models import Task
from app.modules.workbench.models import WbRoutine
from tests.conftest import auth, register

SEED = json.loads((svc.SEEDS / "collab-basics.json").read_text(encoding="utf-8"))
API = "/api/v1"


def _def(**over):
    d = copy.deepcopy(SEED)
    d.update(over)
    return d


# `admins`（两位运营）在 conftest（LINT-008，290 号 spec）


def _publish(client, admins, definition=None):
    a, b = admins
    r = client.post(f"{API}/admin/packs", json={"definition": definition or SEED}, headers=auth(a))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a)).status_code == 200
    r = client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ 定义与规则（PACK-101）
def test_every_repo_seed_is_valid():
    """skill `scenario-discovery` 产出的种子包必须过校验：仓库里不许躺着上不了线的包。"""
    assert svc.seed_files(), "seeds 目录是空的"
    for path in svc.seed_files():
        d, problems = schema.validate(svc.load_seed(path))
        assert d is not None and not problems, (path.name, problems)
        assert path.stem == d.key, f"文件名要等于 key：{path.name}"


def test_rules_are_platform_red_lines():
    a = SEED["assistants"][0]
    cases = {
        "高风险人群": _def(segment="opc"),        # 协作顾问只设了 money / sign，没有 file
        "白名单外": _def(assistants=[{**a, "tools": [*a["tools"], "wallet.pay"]}]),
        "人工关口不认识": _def(assistants=[{**a, "human_gates": ["money", "telepathy"]}]),
        "包里没有的方法": _def(assistants=[{**a, "methods": ["nope"]}]),
        "政策必须写有效期": _def(knowledge=[{**SEED["knowledge"][0], "kind": "policy"}]),
        "key 重复": _def(methods=SEED["methods"] + [SEED["methods"][0]]),
        "没有 pack.knowledge": _def(assistants=[{**a, "tools": ["notebook.search"]}]),
    }
    for name, data in cases.items():
        d, problems = schema.validate(data)
        assert problems, f"{name}：本该不合格却通过了"
    _, problems = schema.validate(_def(assistants=[], methods=[], knowledge=[], routines=[]))
    assert any("一样资产都没有" in p for p in problems)
    # 格式错误（多收字段、缺出处）也要报出来，而不是抛异常
    d, problems = schema.validate(_def(extra_field=1))
    assert d is None and problems
    d, problems = schema.validate(_def(knowledge=[{**SEED["knowledge"][0], "source": ""}]))
    assert d is None and any("source" in p for p in problems)
    assert schema.Score(coverage=5, frequency=3, pain=3, ai=0.8, value=3, cost=1).total() == 108.0


# ------------------------------------------------------------------ 审核与上线（PACK-102 / 103）
def test_four_eyes_versioning_and_retire(client, admins, requester):
    a, b = admins
    assert client.post(f"{API}/admin/packs", json={"definition": SEED}, headers=auth(requester)).status_code == 403
    bad = client.post(f"{API}/admin/packs", json={"definition": _def(segment="opc")}, headers=auth(a))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "pack_invalid"
    v1 = client.post(f"{API}/admin/packs", json={"definition": SEED}, headers=auth(a)).json()
    assert v1["version"] == 1 and v1["status"] == "draft" and v1["score"] == 108.0
    again = client.post(f"{API}/admin/packs", json={"definition": SEED}, headers=auth(b))
    assert again.json()["detail"]["code"] == "pack_draft_exists"
    # 草稿可改，改 key 不行
    r = client.put(f"{API}/admin/packs/{v1['id']}", json={"definition": _def(title="协作入门")}, headers=auth(a))
    assert r.json()["title"] == "协作入门"
    r = client.put(f"{API}/admin/packs/{v1['id']}", json={"definition": _def(key="other-key")}, headers=auth(a))
    assert r.json()["detail"]["code"] == "pack_key_changed"
    assert client.post(f"{API}/admin/packs/{v1['id']}/approve", headers=auth(b)).json()["detail"]["code"] == "pack_not_in_review"
    client.post(f"{API}/admin/packs/{v1['id']}/submit", headers=auth(a))
    r = client.post(f"{API}/admin/packs/{v1['id']}/approve", headers=auth(a))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pack_four_eyes"
    assert client.put(f"{API}/admin/packs/{v1['id']}", json={"definition": SEED}, headers=auth(a)).json()["detail"]["code"] == "pack_not_draft"
    pub = client.post(f"{API}/admin/packs/{v1['id']}/approve", headers=auth(b)).json()
    assert pub["status"] == "published" and pub["reviewed_by"] == b["id"]
    v2 = _publish(client, admins, _def(summary="第二版"))
    rows = {(r["version"], r["status"]) for r in client.get(f"{API}/admin/packs", headers=auth(a)).json()}
    assert rows == {(1, "superseded"), (2, "published")} and v2["version"] == 2
    assert client.get(f"{API}/packs/collab-basics", headers=auth(requester)).json()["summary"] == "第二版"
    r = client.post(f"{API}/admin/packs/{v2['id']}/retire", json={"reason": "规则改了，重写"}, headers=auth(b))
    assert r.json()["status"] == "retired" and r.json()["retired_reason"] == "规则改了，重写"
    assert client.get(f"{API}/packs/collab-basics", headers=auth(requester)).status_code == 404
    with SessionLocal() as db:
        actions = [x.action for x in db.query(AdminAudit).order_by(AdminAudit.id)]
    assert actions.count("pack_publish") == 2 and "pack_retire" in actions and "pack_create" in actions


def test_import_seeds_makes_drafts_that_still_need_review(client, admins):
    a, _ = admins
    out = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    assert "collab-basics" in out["created"] and out["invalid"] == []
    rows = client.get(f"{API}/admin/packs", headers=auth(a)).json()
    assert {r["status"] for r in rows if r["key"] == "collab-basics"} == {"draft"}
    again = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    assert again["created"] == [] and "collab-basics" in again["skipped"]


# ------------------------------------------------------------------ 启用、升级、停用（PACK-104）
def test_enable_installs_copies_upgrade_adds_only_new_and_disable_cleans_up(client, admins, requester):
    _publish(client, admins)
    h = auth(requester)
    cards = client.get(f"{API}/packs", headers=h).json()
    assert [c["key"] for c in cards] == ["collab-basics"] and cards[0]["enabled"] is False
    r = client.post(f"{API}/packs/collab-basics/enable", json={}, headers=h)
    assert r.status_code == 200 and r.json()["installed"] == {"methods": 2, "notes": 4, "routines": 1}
    assert r.json()["enabled"] and r.json()["enabled_version"] == 1
    uid = requester["id"]
    with SessionLocal() as db:
        assert db.query(NbMethod).filter(NbMethod.owner_id == uid).count() == 2
        notes = db.query(NbNote).filter(NbNote.owner_id == uid).all()
        assert len(notes) == 4 and all("平台协作入门" in n.tags for n in notes) and all("出处：" in n.body for n in notes)
        routine = db.query(WbRoutine).filter(WbRoutine.owner_id == uid).one()
        assert routine.enabled and routine.next_run_at is not None
    # 再点一次不重复装
    assert client.post(f"{API}/packs/collab-basics/enable", json={}, headers=h).json()["installed"]["notes"] == 4
    with SessionLocal() as db:
        assert db.query(NbNote).filter(NbNote.owner_id == uid).count() == 4
    # 用户改过一条笔记；新版本多一条知识 → 升级只补新的，不覆盖改过的
    note_id = notes[0].id
    client.patch(f"{API}/notebook/notes/{note_id}", json={"body": "我自己的理解"}, headers=h)
    extra = {"key": "invoice", "title": "开票找谁", "body": "在任务完成后申请。", "kind": "howto", "source": "平台服务规则：发票"}
    _publish(client, admins, _def(knowledge=SEED["knowledge"] + [extra]))
    card = client.get(f"{API}/packs/collab-basics", headers=h).json()
    assert card["upgrade_available"] and card["enabled_version"] == 1 and card["version"] == 2
    up = client.post(f"{API}/packs/collab-basics/enable", json={}, headers=h).json()
    assert up["installed"]["notes"] == 5 and up["enabled_version"] == 2 and not up["upgrade_available"]
    assert client.get(f"{API}/notebook/notes/{note_id}", headers=h).json()["body"] == "我自己的理解"
    # 停用并删副本：没改过的删，改过的留；例行任务删掉
    out = client.post(f"{API}/packs/collab-basics/disable", json={"remove_copies": True}, headers=h).json()
    assert out == {"disabled": True, "removed": 7, "kept_modified": 1}
    with SessionLocal() as db:
        assert db.query(NbNote).filter(NbNote.owner_id == uid).count() == 1
        assert db.query(WbRoutine).filter(WbRoutine.owner_id == uid).count() == 0
    assert client.post(f"{API}/packs/collab-basics/disable", json={}, headers=h).status_code == 404


def test_task_template_carries_acceptance_into_the_prefill(client, admins, requester):
    tpl = {"key": "bookkeeping", "title": "代理记账（按月）", "category": "财税", "description": "每月整理凭证并记账",
           "acceptance": ["按月交记账凭证", "月末给出科目余额表"]}
    _publish(client, admins, _def(task_templates=[tpl]))
    card = client.get(f"{API}/packs/collab-basics", headers=auth(requester)).json()
    t = card["assets"]["task_templates"][0]
    assert t["title"] == "代理记账（按月）" and t["category"] == "财税"
    assert t["description"] == "每月整理凭证并记账\n\n验收标准：\n- 按月交记账凭证\n- 月末给出科目余额表"
    first_template = t
    from tests.test_client_shape_alignment import _assert_shape
    _assert_shape(first_template, "PackTaskTemplateBrief")


def test_disable_without_removing_turns_routines_off(client, admins, requester):
    _publish(client, admins)
    h = auth(requester)
    client.post(f"{API}/packs/collab-basics/enable", json={"with_routines": True}, headers=h)
    client.post(f"{API}/packs/collab-basics/disable", json={}, headers=h)
    with SessionLocal() as db:
        r = db.query(WbRoutine).filter(WbRoutine.owner_id == requester["id"]).one()
        assert r.enabled is False and r.next_run_at is None
        assert db.query(NbNote).filter(NbNote.owner_id == requester["id"]).count() == 4
    # 重新启用：装回来，状态回到 active
    assert client.post(f"{API}/packs/collab-basics/enable", json={"with_routines": False}, headers=h).json()["enabled"]


def test_install_limit(client, admins, requester, monkeypatch):
    from app.modules.notebook import service as nsvc

    _publish(client, admins)
    monkeypatch.setitem(nsvc.LIMITS, "notes", 3)
    r = client.post(f"{API}/packs/collab-basics/enable", json={}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "pack_install_limit"
    with SessionLocal() as db:
        assert db.query(PackEnrollment).count() == 0


# ------------------------------------------------------------------ 助手专家（PACK-105）
def test_assistant_cites_sources_respects_whitelist_and_gates(client, admins, requester):
    _publish(client, admins)
    h = auth(requester)
    client.post(f"{API}/notebook/notes", json={"title": "我的验收经验", "body": "验收过期前一天要提醒对方，记得截图留证据"}, headers=h)
    r = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "验收过期会怎样"}, headers=h).json()
    assert not r["refused"] and r["assistant"] == "协作顾问"
    kinds = [c["kind"] for c in r["citations"]]
    assert kinds[0] == "pack" and "note" in kinds
    assert r["citations"][0]["title"] == "交付后要在期限内验收，过期自动放款"
    assert "出处：平台服务规则：验收与自动放款" in r["answer"]
    assert r["gates"] == [schema.GATES["money"], schema.GATES["sign"]] and "必须你本人确认" in r["gate_notice"]
    refused = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "对方威胁我"}, headers=h).json()
    assert refused["refused"] and refused["citations"] == []
    miss = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "量子计算"}, headers=h).json()
    assert miss["citations"] == [] and miss["remedy"] is None
    assert client.post(f"{API}/packs/collab-basics/assistants/nobody/ask", json={"q": "x"}, headers=h).status_code == 404
    with SessionLocal() as db:
        kinds = sorted(e.kind for e in db.query(PackEvent))
        assert kinds == ["ask", "ask", "unanswered"]
        # 提问原文不落库：事件表没有放文字的列
        assert {c.name for c in PackEvent.__table__.columns} == {"id", "pack_key", "pack_id", "user_id", "kind", "created_at"}


def test_assistant_without_notebook_tool_never_reads_my_notes(client, admins, requester):
    a = {**SEED["assistants"][0], "tools": ["pack.knowledge"], "fallback_category": "法律咨询"}
    _publish(client, admins, _def(assistants=[a]))
    h = auth(requester)
    client.post(f"{API}/notebook/notes", json={"title": "验收", "body": "验收 验收 验收"}, headers=h)
    r = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "验收"}, headers=h).json()
    assert r["citations"] and all(c["kind"] == "pack" for c in r["citations"])
    miss = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "量子计算"}, headers=h).json()
    assert miss["remedy"] == {"action": "publish_task", "category": "法律咨询", "label": "发布一单「法律咨询」，请专业的人来做"}


def test_expired_knowledge_is_flagged_in_answers_and_radar(client, admins, requester):
    k = {**SEED["knowledge"][1], "kind": "policy", "valid_until": "2020-01-01"}
    _publish(client, admins, _def(knowledge=[SEED["knowledge"][0], k, *SEED["knowledge"][2:]]))
    a = admins[0]
    r = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "验收过期"}, headers=auth(requester)).json()
    assert r["citations"][0]["expired"] and "已过有效期" in r["answer"]
    radar = client.get(f"{API}/admin/packs/radar", headers=auth(a)).json()
    assert any(x["source"] == "pack_gap" and "已过有效期" in x["evidence"] for x in radar)


# ------------------------------------------------------------------ 指标与雷达（PACK-106 / 107）
def test_metrics_and_feedback(client, admins, requester, worker):
    _publish(client, admins)
    for u in (requester, worker):
        client.post(f"{API}/packs/collab-basics/enable", json={}, headers=auth(u))
    client.post(f"{API}/packs/collab-basics/feedback", json={"helpful": True}, headers=auth(requester))
    client.post(f"{API}/packs/collab-basics/feedback", json={"helpful": False}, headers=auth(worker))
    client.post(f"{API}/packs/collab-basics/disable", json={}, headers=auth(worker))
    row = next(r for r in client.get(f"{API}/admin/packs", headers=auth(admins[0])).json() if r["status"] == "published")
    m = row["metrics"]
    assert m["active"] == 1 and m["enabled_total"] == 2 and m["helpful_rate"] == 0.5
    assert client.get(f"{API}/packs", headers=auth(requester)).json()[0]["active_users"] == 1


def test_radar_uses_only_k_anonymous_aggregates(client, admins):
    a = admins[0]
    users = [register(client, f"1370000000{i}", f"用户{i}") for i in range(4)]
    now = utcnow()
    with SessionLocal() as db:
        for u in users[:3]:
            db.add(SearchQuery(term="宠物上门喂养", user_id=u["id"], created_at=now))
        for u in users[:2]:
            db.add(SearchQuery(term="只有两个人搜", user_id=u["id"], created_at=now))
        db.add(SearchQuery(term="宠物上门喂养", user_id=users[0]["id"], created_at=now))   # 同一个人多搜不加人数
        for u in users[:3]:
            db.add(Task(creator_id=u["id"], title="修理老式座钟", description="上门", category="维修",
                        budget_cents=10000, status="published", visibility="public",
                        created_at=now - timedelta(days=5)))
        db.add(Task(creator_id=users[0]["id"], title="翻译", description="", category="翻译",
                    budget_cents=10000, status="published", visibility="public", created_at=now - timedelta(days=5)))
        db.commit()
    radar = client.get(f"{API}/admin/packs/radar", headers=auth(a)).json()
    gaps = {x["key"]: x for x in radar if x["source"] == "search_gap"}
    assert "宠物上门喂养" in gaps and gaps["宠物上门喂养"]["people"] == 3 and "只有两个人搜" not in gaps
    stuck = {x["key"] for x in radar if x["source"] == "stuck_demand"}
    assert "维修" in stuck and "翻译" not in stuck          # 翻译只有 1 个发布方
    # 有供给的词不算缺口
    with SessionLocal() as db:
        db.add(Task(creator_id=users[3]["id"], title="宠物上门喂养两周", description="", category="宠物",
                    budget_cents=10000, status="published", visibility="public", created_at=now))
        db.commit()
    radar = client.get(f"{API}/admin/packs/radar", headers=auth(a)).json()
    assert "宠物上门喂养" not in {x["key"] for x in radar if x["source"] == "search_gap"}
    assert client.get(f"{API}/admin/packs/radar", headers=auth(users[0])).status_code == 403


# ------------------------------------------------------------------ 注销（PACK-109）
def test_account_erase_removes_enrollments_and_events(client, admins, requester):
    from app.modules.account.deletion import erase_personal_data

    _publish(client, admins)
    client.post(f"{API}/packs/collab-basics/enable", json={}, headers=auth(requester))
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, requester["id"]))
        db.commit()
        assert db.query(PackEnrollment).count() == 0 and db.query(PackEvent).count() == 0


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, admins, requester):
    from tests.test_client_shape_alignment import _assert_inline_shape, _assert_shape

    a, b = admins
    h = auth(requester)
    validation = client.post(f"{API}/admin/packs/validate", json={"definition": SEED}, headers=auth(a)).json()
    imported = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    rows = client.get(f"{API}/admin/packs", headers=auth(a)).json()
    pid = rows[0]["id"]
    updated = client.put(f"{API}/admin/packs/{pid}", json={"definition": SEED}, headers=auth(a)).json()
    submitted = client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a)).json()
    rejected = client.post(f"{API}/admin/packs/{pid}/reject", headers=auth(b)).json()
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    approved = client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).json()
    created = client.post(f"{API}/admin/packs", json={"definition": _def(summary="v2")}, headers=auth(a)).json()
    retired = client.post(f"{API}/admin/packs/{created['id']}/retire", json={"reason": "不要了"}, headers=auth(a)).json()
    cards = client.get(f"{API}/packs", headers=h).json()
    card = client.get(f"{API}/packs/collab-basics", headers=h).json()
    enabled = client.post(f"{API}/packs/collab-basics/enable", json={}, headers=h).json()
    answer = client.post(f"{API}/packs/collab-basics/assistants/collab-advisor/ask", json={"q": "验收过期"}, headers=h).json()
    fb = client.post(f"{API}/packs/collab-basics/feedback", json={"helpful": True}, headers=h).json()
    disabled = client.post(f"{API}/packs/collab-basics/disable", json={}, headers=h).json()
    with SessionLocal() as db:
        for u in (a, b, requester):
            db.add(SearchQuery(term="宠物上门喂养", user_id=u["id"], created_at=utcnow()))
        db.commit()
    radar = client.get(f"{API}/admin/packs/radar", headers=auth(a)).json()
    assert cards and answer["citations"] and rows and radar

    _assert_shape(validation, "PackValidation")
    _assert_shape(imported, "PackImportResult")
    first_row, metrics = rows[0], rows[0]["metrics"]
    _assert_shape(first_row, "ScenarioPackAdminListRow")
    _assert_shape(metrics, "PackMetrics")
    for row in (updated, submitted, rejected, approved, created, retired):
        _assert_shape(row, "ScenarioPackAdminRow")
    first_card = cards[0]
    _assert_shape(first_card, "ScenarioPackCard")
    _assert_shape(card, "ScenarioPackCard")
    _assert_shape(enabled, "PackEnableResult")
    assets, counts = card["assets"], enabled["installed"]
    _assert_shape(assets, "PackAssets")
    _assert_shape(counts, "PackInstalledCounts")
    first_assistant, first_method, first_knowledge, first_routine = (
        assets["assistants"][0], assets["methods"][0], assets["knowledge"][0], assets["routines"][0])
    _assert_shape(first_assistant, "PackAssistant")
    _assert_shape(first_method, "PackMethodBrief")
    _assert_shape(first_knowledge, "PackKnowledgeBrief")
    _assert_shape(first_routine, "PackRoutineBrief")
    _assert_shape(answer, "PackAnswer")
    first_cite = answer["citations"][0]
    _assert_shape(first_cite, "PackCitation")
    _assert_inline_shape(fb, "packFeedback")
    _assert_inline_shape(disabled, "disablePack")
    first_signal = radar[0]
    _assert_shape(first_signal, "RadarSignal")
