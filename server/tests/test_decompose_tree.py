"""AI-DEC-040~048 拆到能干活为止的树（106 号 spec，设计见 96 号）。

用户 2026-10-10：「任务拆解借鉴 todolist 生成过程，生成树类脉络够细够具体的任务，
这样有些 AI 可以闭环，有些需要求助其他专家」。

这里用一个可编排的假网关代替模型：每条规则（逐层、依据、否决、保险、审核、回落）
都要能被单独驱动——真模型给不出可重复的输入。
"""
import ast
from pathlib import Path

import pytest

from app.core.config import settings
from app.modules.decompose import llm
from tests.conftest import JOB_HEADERS, auth, topup
from tests.test_task_flow import match_and_fund

PROJECT = {
    "title": "开一家咖啡店", "description": "从选址到开业", "category": "活动策划",
    "task_type": "project", "budget_cents": 1_000_000, "is_remote": True, "city": "上海",
    "publish_now": False, "ip_assignment": "assign",
}


def step(title, *, ratio=5000, deps=(), deliverable="", acceptance="", single=True,
         category="", hint=""):
    return {"title": title, "description": title, "required_skills": [],
            "budget_ratio_bps": ratio, "depends_on_idx": list(deps),
            "deliverable": deliverable, "acceptance": acceptance, "single_owner": single,
            "category": category, "executor_hint": hint}


def leaf(title, **kw):
    return step(title, deliverable=f"{title}的成果", acceptance=f"发布方确认{title}已完成", **kw)


class Stub:
    """按「要拆的那一步的标题」给出子步骤；None 是根。"""

    uses_model = True

    def __init__(self, plan, fail=False):
        self.plan, self.fail, self.calls = plan, fail, 0

    def expand(self, db, ctx):
        self.calls += 1
        if self.fail:
            res = llm.TemplateLLM().expand(db, ctx)
            return {**res, "fallback": True, "model_call": True}
        key = ctx["node"]["title"] if ctx["node"] else None
        return {"children": list(self.plan.get(key, [])), "source": "stub-model",
                "fallback": False, "model_call": True}


@pytest.fixture()
def gateway():
    old = llm.get_gateway()
    holder = {}

    def use(plan, **kw):
        holder["g"] = Stub(plan, **kw)
        llm.set_gateway(holder["g"])
        return holder["g"]

    yield use
    llm.set_gateway(old)


def _task(client, user, **over):
    r = client.post("/api/v1/tasks", json={**PROJECT, **over}, headers=auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def _propose(client, user, **over):
    t = _task(client, user, **over)
    r = client.post(f"/api/v1/tasks/{t['id']}/decompositions", headers=auth(user))
    assert r.status_code == 201, r.text
    return t, r.json()


def _expand(client, user, dec, node_ids=None):
    body = {"revision": dec["revision"]}
    if node_ids is not None:
        body["node_ids"] = node_ids
    r = client.post(f"/api/v1/decompositions/{dec['id']}/expand", json=body, headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def _patch(client, user, dec, nid, **fields):
    return client.patch(f"/api/v1/decompositions/{dec['id']}/nodes/{nid}",
                        json={"revision": dec["revision"], **fields}, headers=auth(user))


def _node(dec, title):
    return next(n for n in dec["nodes"] if n["title"] == title)


# ------------------------------------------------------------------ 模板模式
def test_template_layer_is_a_tree_of_ready_leaves(client, requester):
    """没有模型时：模板那一层每一步都带交付物与验收标准，直接是叶子。"""
    _t, dec = _propose(client, requester, category="软件开发", title="公司官网",
                       description="响应式官网")
    assert dec["mode"] == "tree" and len(dec["nodes"]) == 5
    assert all(n["leaf"] and n["stop_reason"] == "criteria_met" for n in dec["nodes"])
    assert all(n["executor_kind"] == "needs_human" for n in dec["nodes"])
    assert dec["unresolved"] == [] and dec["can_expand"] is False
    assert dec["fallback"] is False and dec["source"] == "seed_template"
    # 老客户端读的一层视图还在，且预算守恒
    assert sum(i["budget_cents"] for i in dec["items"]) == PROJECT["budget_cents"]


# ------------------------------------------------------------------ AI-DEC-040 叶子判据
def test_aidec040_a_step_without_deliverable_is_not_a_leaf(client, requester, gateway):
    gateway({None: [leaf("选址"), step("装修", acceptance="验收合格")]})
    _t, dec = _propose(client, requester)
    renov = _node(dec, "装修")
    assert renov["leaf"] is False and renov["missing"] == ["deliverable"]
    assert [u["title"] for u in dec["unresolved"]] == ["装修"]
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "tree_incomplete"
    assert "装修" in r.json()["detail"]["message"] and "交付物" in r.json()["detail"]["message"]

    r = _patch(client, requester, dec, renov["id"], deliverable="按图纸完成的店面")
    assert r.status_code == 200, r.text
    assert _node(r.json(), "装修")["leaf"] is True


def test_aidec040_two_owners_or_unescrowable_budget_is_not_a_leaf(client, requester, gateway):
    gateway({None: [leaf("合伙谈判", single=False, ratio=9000), leaf("跑腿", ratio=5),
                    step("定菜单", deliverable="菜单", ratio=995)]})
    _t, dec = _propose(client, requester)
    assert _node(dec, "合伙谈判")["missing"] == ["single_owner"]
    assert _node(dec, "跑腿")["missing"] == ["budget"]
    assert _node(dec, "定菜单")["missing"] == ["acceptance"], "说得出交什么、说不出怎么验，也不是叶子"


# ------------------------------------------------------------------ AI-DEC-041 逐层
def test_aidec041_grows_one_layer_per_call_and_every_layer_is_saved(client, requester, gateway):
    g = gateway({
        None: [step("开业筹备"), step("运营起步", deps=[0])],
        "开业筹备": [leaf("选址"), leaf("装修", deps=[0])],
        "运营起步": [leaf("招聘店员"), leaf("开业活动")],
    })
    _t, dec = _propose(client, requester)
    assert len(dec["nodes"]) == 2 and dec["can_expand"] is True and g.calls == 1
    rev0 = dec["revision"]

    dec2 = _expand(client, requester, dec)
    assert len(dec2["nodes"]) == 6 and g.calls == 3
    assert dec2["revision"] == rev0 + 1, "这一层没有落盘"
    assert dec2["can_expand"] is False and dec2["unresolved"] == []
    # 同级依赖映射到了真实节点
    pick, renov = _node(dec2, "选址"), _node(dec2, "装修")
    assert renov["depends_on"] == [pick["id"]]
    # 关掉页面再回来：读回来的是同一棵树（真的写进了库）
    again = client.get(f"/api/v1/tasks/{dec['task_id']}/decomposition", headers=auth(requester))
    assert again.status_code == 200, again.text
    assert again.json()["revision"] == dec2["revision"] and len(again.json()["nodes"]) == 6


def test_aidec041_a_single_step_can_be_split_on_demand(client, requester, gateway):
    gateway({None: [leaf("选址"), leaf("装修")],
             "装修": [leaf("设计图纸"), leaf("施工", deps=[0])]})
    _t, dec = _propose(client, requester)
    renov = _node(dec, "装修")
    dec2 = _expand(client, requester, dec, [renov["id"]])
    assert {n["title"] for n in dec2["nodes"]} == {"选址", "装修", "设计图纸", "施工"}
    assert _node(dec2, "装修")["leaf"] is False, "拆过的步骤变成组织结构，不再是叶子"
    r = client.post(f"/api/v1/decompositions/{dec2['id']}/expand",
                    json={"revision": dec2["revision"], "node_ids": [renov["id"]]}, headers=auth(requester))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_expanded"


# ------------------------------------------------------------------ AI-DEC-042/043 谁能闭环
def _seed_agent_history(category, n):
    from app.core.db import SessionLocal
    from app.modules.account.models import User
    from app.modules.agent.models import AgentRun
    from app.modules.task.models import Task

    with SessionLocal() as db:
        owner = User(phone=f"1390000{n:04d}", nickname="历史", password_hash="x")
        db.add(owner)
        db.flush()
        for i in range(n):
            t = Task(creator_id=owner.id, title=f"历史{i}", category=category, budget_cents=100,
                     status="completed", is_remote=True)
            db.add(t)
            db.flush()
            db.add(AgentRun(agent_user_id=owner.id, task_id=t.id, status="succeeded"))
        db.commit()


def _ensure_category(name, cert=""):
    from app.core.db import SessionLocal
    from app.modules.task.models import Category

    with SessionLocal() as db:
        if not db.query(Category).filter_by(name=name).first():
            db.add(Category(name=name, required_cert=cert))
            db.commit()


def test_aidec042_ai_closable_needs_real_history_otherwise_unknown(client, requester, gateway):
    _ensure_category("文案写作")
    gateway({None: [leaf("写开业文案", hint="ai", category="文案写作"), leaf("选址")]})
    _t, dec = _propose(client, requester)
    copy = _node(dec, "写开业文案")
    assert copy["category"] == "文案写作"
    assert copy["executor_kind"] == "unknown", "没有历史闭环记录，不得标 AI 可闭环"
    assert "0 次" in copy["executor_basis"]

    _seed_agent_history("文案写作", settings.DECOMPOSE_AI_CLOSABLE_MIN_RUNS)
    _t2, dec2 = _propose(client, requester)
    copy2 = _node(dec2, "写开业文案")
    assert copy2["executor_kind"] == "ai_closable"
    assert f"{settings.DECOMPOSE_AI_CLOSABLE_MIN_RUNS} 次" in copy2["executor_basis"]


def test_aidec043_certified_category_is_never_ai_closable(client, requester, gateway):
    """要资质的类目：哪怕模型说 AI 能做、哪怕 Agent 在这个类目闭环过，也是 needs_expert。"""
    _seed_agent_history("法律咨询", settings.DECOMPOSE_AI_CLOSABLE_MIN_RUNS + 2)
    gateway({None: [leaf("审租赁合同", hint="ai", category="法律咨询"), leaf("选址")]})
    _t, dec = _propose(client, requester)
    lawyer = _node(dec, "审租赁合同")
    assert lawyer["executor_kind"] == "needs_expert"
    assert lawyer["required_cert"] == "律师" and "类目资质表" in lawyer["executor_basis"]


def test_aidec043_root_category_with_a_cert_makes_every_leaf_an_expert_step(client, requester):
    _t, dec = _propose(client, requester, category="法律咨询", title="公司设立法律服务")
    assert dec["nodes"] and all(n["executor_kind"] == "needs_expert" for n in dec["nodes"])


def test_model_invented_categories_are_not_trusted(client, requester, gateway):
    gateway({None: [leaf("算命", category="不存在的类目"), leaf("选址")]})
    _t, dec = _propose(client, requester)
    assert _node(dec, "算命")["category"] == ""


# ------------------------------------------------------------------ AI-DEC-044 去处
def test_aidec044_unknown_must_be_resolved_and_each_resolution_is_real(client, requester, gateway):
    gateway({None: [leaf("搞定营业执照", hint="unknown"), leaf("店面法律审查", hint="expert")]})
    _t, dec = _propose(client, requester)
    assert {u["title"] for u in dec["unresolved"]} == {"搞定营业执照", "店面法律审查"}
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 409 and "谁来做" in r.json()["detail"]["message"]

    r = _patch(client, requester, dec, _node(dec, "搞定营业执照")["id"], executor_hint="human")
    dec = r.json()
    assert _node(dec, "搞定营业执照")["executor_kind"] == "needs_human"
    r = _patch(client, requester, dec, _node(dec, "店面法律审查")["id"], category="法律咨询")
    dec = r.json()
    assert _node(dec, "店面法律审查")["executor_kind"] == "needs_expert"
    assert dec["unresolved"] == []

    # 用户不能空口把一步标成「AI 可闭环」：hint=ai 照样要历史依据
    r = _patch(client, requester, dec, _node(dec, "搞定营业执照")["id"], executor_hint="ai")
    assert _node(r.json(), "搞定营业执照")["executor_kind"] == "unknown"
    bad = _patch(client, requester, r.json(), _node(dec, "搞定营业执照")["id"],
                 executor_hint="ai_closable")
    assert bad.status_code == 400


def test_aidec044_expert_step_is_published_behind_the_cert_gate(client, requester, worker, gateway):
    """「需要律师」不是一句提示：确认后它是法律咨询类目的任务，没有律师资质接不了。"""
    gateway({None: [leaf("审租赁合同", category="法律咨询", ratio=3000), leaf("选址", ratio=7000)]})
    _t, dec = _propose(client, requester)
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 200, r.text
    legal = next(c for c in r.json()["children"] if c["title"].endswith("审租赁合同"))
    assert legal["category"] == "法律咨询" and legal["status"] == "published"
    assert "验收标准" in legal["description"]
    r = client.post(f"/api/v1/tasks/{legal['id']}/applications", json={"message": "我来"},
                    headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"


# ------------------------------------------------------------------ AI-DEC-045 保险
def test_aidec045_max_depth_stops_visibly(client, requester, gateway, monkeypatch):
    monkeypatch.setattr(settings, "DECOMPOSE_MAX_DEPTH", 1)
    gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("a"), leaf("b")]})
    _t, dec = _propose(client, requester)
    dec2 = _expand(client, requester, dec)
    prep = _node(dec2, "开业筹备")
    assert prep["stop_reason"] == "max_depth" and prep["stop_note"], "停了却不说为什么"
    assert dec2["report"]["stopped"] == [{"id": prep["id"], "reason": "max_depth"}]
    assert dec2["can_expand"] is False


def test_aidec045_max_nodes(client, requester, gateway, monkeypatch):
    monkeypatch.setattr(settings, "DECOMPOSE_MAX_NODES", 3)
    gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("a"), leaf("b")]})
    _t, dec = _propose(client, requester)
    dec2 = _expand(client, requester, dec)
    assert _node(dec2, "开业筹备")["stop_reason"] == "max_nodes" and len(dec2["nodes"]) == 2


def test_aidec045_budget_fragment(client, requester, gateway):
    gateway({None: [step("开业筹备", ratio=9990), step("小事", ratio=10)],
             "小事": [leaf("x"), leaf("y")], "开业筹备": [leaf("a"), leaf("b")]})
    _t, dec = _propose(client, requester)
    dec2 = _expand(client, requester, dec)
    assert _node(dec2, "小事")["stop_reason"] == "budget_fragment"


def test_aidec045_no_progress(client, requester, gateway):
    gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("开业筹备"), leaf("别的")]})
    _t, dec = _propose(client, requester)
    assert _node(_expand(client, requester, dec), "开业筹备")["stop_reason"] == "no_progress"


def test_aidec045_cost_cap(client, requester, gateway, monkeypatch):
    monkeypatch.setattr(settings, "DECOMPOSE_MAX_MODEL_CALLS", 1)
    g = gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("a"), leaf("b")]})
    _t, dec = _propose(client, requester)
    dec2 = _expand(client, requester, dec)
    assert _node(dec2, "开业筹备")["stop_reason"] == "cost_cap" and g.calls == 1
    assert dec2["model_calls"] == 1


def test_aidec045_invalid_dependency_output(client, requester, gateway):
    gateway({None: [step("开业筹备"), leaf("选址")],
             "开业筹备": [leaf("a", deps=[1]), leaf("b", deps=[0])]})
    _t, dec = _propose(client, requester)
    assert _node(_expand(client, requester, dec), "开业筹备")["stop_reason"] == "invalid_output"


# ------------------------------------------------------------------ AI-DEC-046 多层预算
def test_aidec046_budget_is_checked_at_every_level(client, requester, gateway):
    gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("a"), leaf("b")]})
    _t, dec = _propose(client, requester)
    dec = _expand(client, requester, dec)
    prep = _node(dec, "开业筹备")
    a = _node(dec, "a")
    r = _patch(client, requester, dec, a["id"], budget_cents=prep["budget_cents"])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "budget_exceeded"
    assert "开业筹备" in r.json()["detail"]["message"]


# ------------------------------------------------------------------ AI-DEC-047 每层过审核
def test_aidec047_a_deep_layer_with_banned_content_is_blocked(client, requester, gateway):
    from app.modules.task.service import machine_review

    banned = next((w for w in ("赌博", "代开发票", "枪支") if machine_review(w)), None)
    assert banned, "找不到一个会被机审拦下的词，这条测不了"
    gateway({None: [step("开业筹备"), leaf("选址")],
             "开业筹备": [leaf(f"安排{banned}"), leaf("正常一步")]})
    _t, dec = _propose(client, requester)
    dec2 = _expand(client, requester, dec)
    prep = _node(dec2, "开业筹备")
    assert prep["stop_reason"] == "moderation"
    assert dec2["report"]["blocked"] == [f"安排{banned}"]
    assert not any(n["parent"] == prep["id"] for n in dec2["nodes"]), "被拦的那一层不该部分落盘"


def test_aidec047_finance_offers_are_blocked_in_deep_layers(client, requester, gateway):
    gateway({None: [step("开业筹备"), leaf("选址")],
             "开业筹备": [leaf("招募股东保本保收益"), leaf("正常一步")]})
    _t, dec = _propose(client, requester)
    assert _node(_expand(client, requester, dec), "开业筹备")["stop_reason"] == "moderation"


# ------------------------------------------------------------------ AI-DEC-048 回落看得见
def test_aidec048_model_fallback_is_visible(client, requester, gateway):
    gateway({}, fail=True)
    _t, dec = _propose(client, requester)
    assert dec["fallback"] is True and all(n["fallback"] for n in dec["nodes"])


def test_aidec048_real_gateway_marks_fallback(db_session=None):
    class Broken(llm.AnthropicLLM):
        def _call_expand(self, ctx):
            raise RuntimeError("model gone")

    from app.core.db import SessionLocal

    with SessionLocal() as db:
        res = Broken().expand(db, {"root": {"title": "t", "description": "", "category": "x",
                                            "budget_cents": 100}, "path": [], "node": None, "depth": 1})
    assert res["fallback"] is True and res["model_call"] is True and res["children"]


# ------------------------------------------------------------------ 并发与归属
def test_concurrent_edits_do_not_silently_overwrite(client, requester, gateway):
    gateway({None: [leaf("选址"), leaf("装修")]})
    _t, dec = _propose(client, requester)
    nid = _node(dec, "选址")["id"]
    first = _patch(client, requester, dec, nid, title="选址（第一个窗口）")
    second = _patch(client, requester, dec, nid, title="选址（第二个窗口）")
    assert first.status_code == 200
    assert second.status_code == 409 and second.json()["detail"]["code"] == "decomposition_changed"


def test_only_the_publisher_can_touch_the_tree(client, requester, worker, gateway):
    gateway({None: [leaf("选址"), leaf("装修")]})
    _t, dec = _propose(client, requester)
    nid = dec["nodes"][0]["id"]
    assert client.post(f"/api/v1/decompositions/{dec['id']}/expand", json={"revision": dec["revision"]},
                       headers=auth(worker)).status_code == 403
    assert _patch(client, worker, dec, nid, title="x").status_code == 403
    assert client.delete(f"/api/v1/decompositions/{dec['id']}/nodes/{nid}",
                         params={"revision": dec["revision"]}, headers=auth(worker)).status_code == 403


def test_delete_a_subtree_and_its_dependants_are_cleaned(client, requester, gateway):
    gateway({None: [leaf("选址"), leaf("装修", deps=[0])]})
    _t, dec = _propose(client, requester)
    r = client.delete(f"/api/v1/decompositions/{dec['id']}/nodes/{_node(dec, '选址')['id']}",
                      params={"revision": dec["revision"]}, headers=auth(requester))
    assert r.status_code == 200, r.text
    assert [n["title"] for n in r.json()["nodes"]] == ["装修"]
    assert r.json()["nodes"][0]["depends_on"] == []


# ------------------------------------------------------------------ 确认与推进
def test_confirm_a_two_level_tree_then_work_it_to_completion(client, requester, worker, gateway):
    """只有叶子发布；容器步骤是草稿；前置完成后，下一个容器下面的叶子才发布；
    全部完成后容器与总任务自动结项。"""
    gateway({
        None: [step("开业筹备", ratio=6000), step("运营起步", ratio=4000, deps=[0])],
        "开业筹备": [leaf("选址"), leaf("装修", deps=[0])],
        "运营起步": [leaf("招聘店员"), leaf("开业活动")],
    })
    topup(client, requester, 3_000_000)
    task, dec = _propose(client, requester)
    dec = _expand(client, requester, dec)
    r = client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    assert r.status_code == 200, r.text
    kids = {c["title"].split(" - ", 1)[1]: c for c in r.json()["children"]}
    assert kids["开业筹备"]["status"] == "draft", "容器步骤不发布、不托管"
    assert kids["选址"]["status"] == "published"
    assert kids["装修"]["status"] == "draft" and kids["运营起步"]["status"] == "draft"
    assert kids["招聘店员"]["status"] == "draft", "它的上一级还在等前置，它也得等"
    nodes = r.json()["decomposition"]["nodes"]
    assert all(n["task_id"] for n in nodes)

    def finish(t):
        match_and_fund(client, requester, worker, t)
        client.post(f"/api/v1/tasks/{t['id']}/deliver", headers=auth(worker))
        assert client.post(f"/api/v1/tasks/{t['id']}/accept-delivery",
                           headers=auth(requester)).status_code == 200

    def status(tid):
        return client.get(f"/api/v1/tasks/{tid}", headers=auth(requester)).json()["status"]

    finish(kids["选址"])
    assert status(kids["装修"]["id"]) == "published"
    assert status(kids["运营起步"]["id"]) == "draft", "前置容器还没完成"
    finish({**kids["装修"], "status": "published"})
    assert status(kids["开业筹备"]["id"]) == "completed", "容器的全部子步骤完成，它自己结项"
    # 前置容器完成：后继**容器**自己不发布，发布的是它下面的叶子
    assert status(kids["运营起步"]["id"]) == "draft"
    assert status(kids["招聘店员"]["id"]) == "published"
    assert status(kids["开业活动"]["id"]) == "published"
    finish({**kids["招聘店员"], "status": "published"})
    finish({**kids["开业活动"], "status": "published"})
    assert status(kids["运营起步"]["id"]) == "completed"
    assert status(task["id"]) == "completed", "全部完成，总任务结项"


def test_legacy_flat_proposals_still_confirm(client, requester):
    """V132 之前存下的一层提案（tree 为空）照原来的路走。"""
    from app.core.db import SessionLocal
    from app.modules.decompose.models import Decomposition

    t = _task(client, requester)
    with SessionLocal() as db:
        row = Decomposition(task_id=t["id"], creator_id=requester["id"], source="old",
                            items=[{"title": "A", "budget_cents": 500000, "required_skills": [],
                                    "depends_on_idx": []}])
        db.add(row)
        db.commit()
        did = row.id
    r = client.post(f"/api/v1/decompositions/{did}/confirm", headers=auth(requester))
    assert r.status_code == 200, r.text
    assert r.json()["decomposition"]["mode"] == "flat"


# ------------------------------------------------------------------ 结构闸门
def test_decompose_never_touches_money():
    """AI 只产出草稿，确认由人；拆解模块不许 import 任何动钱的代码（96 号第 7 节）。"""
    base = Path(__file__).resolve().parents[1] / "app" / "modules" / "decompose"
    forbidden = ("app.modules.wallet", "app.modules.contract", "app.vendors.payment")
    for f in base.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                assert not name.startswith(forbidden), f"{f.name} import 了 {name}"


def test_migration_seed_fields_match_the_seed_templates():
    import importlib.util

    from app.modules.knowledge.service import SEED_TEMPLATES

    path = next((Path(__file__).resolve().parents[1] / "migrations" / "versions")
                .glob("c1d220260007_*.py"))
    spec = importlib.util.spec_from_file_location("m", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seeds = {it["title"]: (it["deliverable"], it["acceptance"])
             for t in SEED_TEMPLATES for it in t["items"]}
    assert mod.SEED_LEAF_FIELDS == seeds


def test_resume_is_owner_only_and_404_when_nothing_in_progress(client, requester, worker, gateway):
    gateway({None: [leaf("选址"), leaf("装修")]})
    t, dec = _propose(client, requester)
    assert client.get(f"/api/v1/tasks/{t['id']}/decomposition", headers=auth(worker)).status_code == 403
    client.post(f"/api/v1/decompositions/{dec['id']}/confirm", headers=auth(requester))
    r = client.get(f"/api/v1/tasks/{t['id']}/decomposition", headers=auth(requester))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_decomposition_in_progress"


def test_tree_responses_match_the_sdk_declarations(client, requester, gateway):
    """四个新端点都返回 `_dump(...)`（调用而不是字面量），静态扫描读不到——
    用真实响应与 SDK 的 `Decomposition` 声明比。`report` 只有展开的响应带。"""
    from tests.test_client_shape_alignment import _assert_shape

    gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("a"), leaf("b")]})
    t, dec = _propose(client, requester)
    _assert_shape(dec, "Decomposition", optional={"report"})
    current = client.get(f"/api/v1/tasks/{t['id']}/decomposition", headers=auth(requester)).json()
    _assert_shape(current, "Decomposition", optional={"report"})
    expanded = _expand(client, requester, dec)
    _assert_shape(expanded, "Decomposition")
    _assert_shape(expanded["report"], "DecompositionExpandReport")
    _assert_shape(expanded["nodes"][0], "DecompositionNode")
    edited = _patch(client, requester, expanded, _node(expanded, "a")["id"], title="a2").json()
    _assert_shape(edited, "Decomposition", optional={"report"})
    deleted = client.delete(f"/api/v1/decompositions/{dec['id']}/nodes/{_node(edited, 'b')['id']}",
                            params={"revision": edited["revision"]}, headers=auth(requester)).json()
    _assert_shape(deleted, "Decomposition", optional={"report"})


def test_aidec045_stop_reasons_are_observable(client, requester, gateway, monkeypatch):
    """96 号第 5 节：保险的**实际触发率**要可观测——经常截断说明判据或模板不对。"""
    from app.core.config import settings as s

    def count():
        text = client.get("/metrics", headers=JOB_HEADERS).text
        line = next(l for l in text.splitlines() if l.startswith('decompose_stop_total{reason="max_depth"}'))
        return int(line.split()[-1])

    before = count()
    monkeypatch.setattr(s, "DECOMPOSE_MAX_DEPTH", 1)
    gateway({None: [step("开业筹备"), leaf("选址")], "开业筹备": [leaf("a"), leaf("b")]})
    _t, dec = _propose(client, requester)
    _expand(client, requester, dec)
    assert count() == before + 1
    text = client.get("/metrics", headers=JOB_HEADERS).text
    assert 'decompose_stop_total{reason="cost_cap"}' in text, "没触发过的原因也要出一行（0）"
