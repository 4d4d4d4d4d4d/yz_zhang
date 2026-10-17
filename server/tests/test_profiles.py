"""PROF-100~107 任务画像与能力画像（126 号 spec）。

用户原话：「对于平台来说需要任务画像。」画像只用已有数据算：不新增表，对外只给聚合。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.knowledge.models import KnowledgeCard
from app.modules.profiles import service as svc
from app.modules.task.models import Review, Task
from tests.conftest import auth, ban_user_row

API = "/api/v1"


def _set_skills(uid, skills):
    with SessionLocal() as db:
        u = db.get(User, uid)
        u.skills = skills
        db.commit()


def _done(executor_id, creator_id, category, stars=None, skills=(), late=False, rework=0):
    now = utcnow()
    with SessionLocal() as db:
        t = Task(creator_id=creator_id, executor_id=executor_id, title=f"{category}单", description="", category=category,
                 budget_cents=10000, status="completed", required_skills=list(skills), reject_count=rework,
                 deadline=now - timedelta(days=1), delivered_at=now if late else now - timedelta(days=2), completed_at=now)
        db.add(t)
        db.flush()
        if stars:
            db.add(Review(task_id=t.id, reviewer_id=creator_id, target_id=executor_id, stars=stars))
        db.commit()
        return t.id


# ------------------------------------------------------------------ 任务画像（PROF-101~103）
def test_draft_profile_flags_missing_pieces_and_price(client, requester, worker):
    _set_skills(worker["id"], ["Figma", "品牌设计"])
    with SessionLocal() as db:
        for p in (40000, 50000, 60000):
            db.add(KnowledgeCard(category="设计", city="", title="设计", outcome="completed", price_actual_cents=p))
        db.commit()
    h = auth(requester)
    bare = client.post(f"{API}/profiles/task-draft", json={"title": "设计", "category": "设计", "budget_cents": 20000}, headers=h).json()
    failing = {c["key"] for c in bare["checks"] if not c["ok"]}
    assert {"title", "description", "acceptance", "deadline", "location", "skills", "price"} <= failing
    assert bare["price"]["position"] == "below_min" and "最低价" in next(c["hint"] for c in bare["checks"] if c["key"] == "price")
    assert bare["completeness"] < 0.3 and bare["size"] == "small"
    good = client.post(f"{API}/profiles/task-draft", json={
        "title": "咖啡店品牌升级：logo 与菜单", "category": "设计", "budget_cents": 52000, "is_remote": True,
        "description": "社区咖啡店换新，需要重新设计 logo、菜单与门头。交付物：源文件与印刷稿，验收标准：三轮内修改到满意。用 Figma 出稿。",
        "deadline": (utcnow() + timedelta(days=10)).isoformat() + "Z"}, headers=h).json()
    assert good["completeness"] == 1.0 and all(c["ok"] for c in good["checks"])
    assert good["inferred_skills"] == ["Figma"] and good["price"]["position"] == "around_median" and good["mode"] == "remote"


def test_risk_flags(client, requester):
    h = auth(requester)
    r = client.post(f"{API}/profiles/task-draft", json={"title": "上门照看孩子并帮忙垫付买菜", "category": "跑腿",
                                                       "description": "", "budget_cents": 600000}, headers=h).json()
    kinds = {x["kind"] for x in r["risks"]}
    assert {"onsite_home", "minor", "advance", "large_amount"} <= kinds
    lawyer = client.post(f"{API}/profiles/task-draft", json={"title": "合同审阅", "category": "法律咨询"}, headers=h).json()
    assert any(x["kind"] == "cert" and "律师" in x["text"] for x in lawyer["risks"])
    remote = client.post(f"{API}/profiles/task-draft", json={"title": "上门服务方案写作", "is_remote": True}, headers=h).json()
    assert "onsite_home" not in {x["kind"] for x in remote["risks"]}         # 线上的活不提示上门安全


def test_task_profile_visibility(client, requester, worker):
    with SessionLocal() as db:
        pub = Task(creator_id=requester["id"], title="公开的单", description="", category="保洁", budget_cents=100,
                   status="published", visibility="public")
        draft = Task(creator_id=requester["id"], title="草稿", description="", category="保洁", budget_cents=100, status="draft")
        db.add_all([pub, draft])
        db.commit()
        pub_id, draft_id = pub.id, draft.id
    assert client.get(f"{API}/tasks/{pub_id}/profile", headers=auth(worker)).json()["task_id"] == pub_id
    assert client.get(f"{API}/tasks/{draft_id}/profile", headers=auth(worker)).status_code == 404
    assert client.get(f"{API}/tasks/{draft_id}/profile", headers=auth(requester)).status_code == 200


def test_infer_skills_unit():
    vocab = ["Figma", "UI设计", "设计", "Python"]
    # 长词先认；「设计」已被「UI设计」包含，不重复列
    assert sorted(svc.infer_skills("用 figma 做 UI设计", vocab, [])) == ["Figma", "UI设计"]
    assert svc.infer_skills("用 Figma", vocab, ["figma"]) == []                       # 写明了的不重复列


# ------------------------------------------------------------------ 撮合用上推断技能（PROF-104）
def test_matching_gets_a_small_bonus_from_inferred_skills(client, requester, worker):
    _set_skills(worker["id"], ["Figma"])
    with SessionLocal() as db:
        t = Task(creator_id=requester["id"], title="海报设计", description="用 Figma 出稿", category="设计",
                 budget_cents=10000, status="published", visibility="public", is_remote=True)
        db.add(t)
        db.commit()
        tid = t.id
    from app.modules.matching.service import _category_fit

    with SessionLocal() as db:
        fit = _category_fit(db, db.get(Task, tid), [db.get(User, worker["id"])])
    assert worker["id"] in fit and any("说明里提到了你的技能「Figma」" in w for w in fit[worker["id"]][1])


# ------------------------------------------------------------------ 能力画像（PROF-105~107）
def test_capability_separates_claimed_from_evidenced(client, requester, worker):
    _set_skills(worker["id"], ["Figma", "摄影"])
    for n in range(3):
        _done(worker["id"], requester["id"], "设计", stars=5 if n else 3, skills=["Figma"], late=(n == 0), rework=1 if n == 0 else 0)
    _done(worker["id"], requester["id"], "保洁", stars=4)
    me = client.get(f"{API}/users/me/capability", headers=auth(worker)).json()
    assert me["tasks_completed"] == 4 and me["categories"][0] == {"category": "设计", "completed": 3, "rating_avg": 4.3}
    assert {s["skill"]: s["evidenced"] for s in me["skills"]} == {"Figma": True, "摄影": False}
    assert me["on_time_rate"] == 0.75 and me["rework_rate"] == 0.25 and me["disputes"] == 0
    public = client.get(f"{API}/users/{worker['id']}/capability", headers=auth(requester)).json()
    assert public["disputes"] is None and public["tasks_completed"] == 4


def test_small_samples_give_no_rates(client, requester, worker):
    _done(worker["id"], requester["id"], "设计")
    me = client.get(f"{API}/users/me/capability", headers=auth(worker)).json()
    assert me["on_time_rate"] is None and me["rework_rate"] is None and "少于 3 单" in me["note"]


def test_capability_privacy(client, requester, worker):
    with SessionLocal() as db:
        u = db.get(User, worker["id"])
        u.privacy = {"profile_public": False}
        db.commit()
    assert client.get(f"{API}/users/{worker['id']}/capability", headers=auth(requester)).status_code == 404
    assert client.get(f"{API}/users/{worker['id']}/capability", headers=auth(worker)).status_code == 200
    with SessionLocal() as db:
        u = db.get(User, worker["id"])
        u.privacy = {}
        db.commit()
    ban_user_row(worker["id"])
    assert client.get(f"{API}/users/{worker['id']}/capability", headers=auth(requester)).status_code == 404


# ------------------------------------------------------------------ 响应形状（CLI-083）
def test_responses_match_sdk_types(client, requester, worker):
    from tests.test_client_shape_alignment import _assert_shape

    _set_skills(worker["id"], ["Figma"])
    _done(worker["id"], requester["id"], "设计", stars=5, skills=["Figma"])
    draft = client.post(f"{API}/profiles/task-draft", json={"title": "上门设计", "category": "法律咨询", "budget_cents": 600000}, headers=auth(requester)).json()
    with SessionLocal() as db:
        t = Task(creator_id=requester["id"], title="x", description="", category="保洁", budget_cents=1, status="published", visibility="public")
        db.add(t)
        db.commit()
        tid = t.id
    prof = client.get(f"{API}/tasks/{tid}/profile", headers=auth(worker)).json()
    cap = client.get(f"{API}/users/me/capability", headers=auth(worker)).json()
    pub = client.get(f"{API}/users/{worker['id']}/capability", headers=auth(requester)).json()
    _assert_shape(draft, "TaskProfile")
    first_check, first_risk, price = draft["checks"][0], draft["risks"][0], draft["price"]
    _assert_shape(first_check, "TaskProfileCheck")
    _assert_shape(first_risk, "TaskProfileRisk")
    _assert_shape(price, "TaskProfilePrice")
    _assert_shape(prof, "TaskProfileView")
    for c in (cap, pub):
        _assert_shape(c, "CapabilityProfile")
    first_cat, first_skill = cap["categories"][0], cap["skills"][0]
    _assert_shape(first_cat, "CapabilityCategory")
    _assert_shape(first_skill, "CapabilitySkill")
