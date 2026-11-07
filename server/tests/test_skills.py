"""SKL-100~106 技能的语义匹配：技能概念表（135 号 spec）。

「VI 设计」「标志设计」「logo 设计」说的都是「品牌设计」：撮合、说明里认技能（PROF-110）、能力画像佐证、
个人空间相关性（SPACE-023b）、知识库检索（KB-110）都按概念算。概念表 = 仓库种子 + 运营在后台的增改。
"""
from app.core.db import SessionLocal
from app.modules.account.models import User
from app.modules.matching.service import _category_fit, _skill_score
from app.modules.profiles import service as psvc
from app.modules.skills import service as svc
from app.modules.task.models import Task
from tests.conftest import auth, make_admin

API = "/api/v1"


def test_norm_and_canonical():
    idx = svc.index()
    assert svc.norm("ＶＩ 设计") == svc.norm("vi设计") == "vi设计"
    assert svc.canonical("VI 设计", idx) == svc.canonical("logo设计", idx) == svc.canonical("标志设计", idx) == "品牌设计"
    assert svc.canonical("剪纸", idx) == "剪纸"           # 认不出就原样，不猜


def test_skill_score_counts_aliases_and_keeps_exact_matches():
    same = svc.matcher(None)
    assert _skill_score(["品牌设计", "文案"], ["VI设计"], same) == 0.5
    assert _skill_score(["品牌设计"], ["品牌设计"], same) == 1.0
    assert _skill_score(["品牌设计"], ["剪纸"], same) == 0.0
    assert _skill_score(["品牌设计"], ["VI设计"]) == 0.0               # 不传 same 时是原来的字面比较
    assert _skill_score([], ["VI设计"], same) == 0.5


def test_infer_skills_recognises_aliases_in_the_description():
    out = psvc.infer_skills("咖啡店要做一套 logo设计，再出几张宣传单设计", vocab=[], declared=[])
    assert out == ["品牌设计", "平面设计"]
    assert psvc.infer_skills("要做 logo设计", vocab=[], declared=["品牌设计"]) == []      # 已经写了就不重复


def test_matching_uses_concepts_for_required_skills(client, requester, worker):
    from app.modules.matching.service import recommend

    with SessionLocal() as db:
        db.get(User, worker["id"]).skills = ["VI设计"]
        t = Task(creator_id=requester["id"], title="咖啡店品牌升级", description="", category="设计", budget_cents=50000,
                 status="published", required_skills=["品牌设计"], is_remote=True)
        db.add(t)
        db.commit()
        rows = {r["user_id"]: r for r in recommend(db, t, limit=50)}
    assert "技能完全匹配" in rows[worker["id"]]["reasons"]          # 写的是「VI设计」，要求是「品牌设计」


def test_space_text_with_an_alias_counts_as_mentioning_the_category(client, requester, worker):
    with SessionLocal() as db:
        db.get(User, worker["id"]).skills = ["logo设计"]
        t = Task(creator_id=requester["id"], title="x", description="", category="品牌设计", budget_cents=10000,
                 status="published", required_skills=["x"])
        db.add(t)
        db.flush()
        fit = _category_fit(db, t, [db.get(User, worker["id"])])
        assert any("擅长「品牌设计」" in w for w in fit[worker["id"]][1])


def test_capability_marks_alias_skills_as_evidenced(client, requester, worker):
    with SessionLocal() as db:
        u = db.get(User, worker["id"])
        u.skills = ["VI设计", "剪纸"]
        db.add(Task(creator_id=requester["id"], executor_id=worker["id"], title="t", category="设计", budget_cents=1000,
                    status="completed", required_skills=["品牌设计"]))
        db.commit()
    c = client.get(f"{API}/users/me/capability", headers=auth(worker)).json()
    assert {s["skill"]: s["evidenced"] for s in c["skills"]} == {"VI设计": True, "剪纸": False}


def test_notebook_search_expands_concepts(client, requester):
    h = auth(requester)
    client.post(f"{API}/notebook/notes", json={"title": "品牌设计报价经验", "body": "一般按三轮修改报价"}, headers=h)
    hits = client.get(f"{API}/notebook/notes", params={"q": "标志设计"}, headers=h).json()      # 只沾「设计」两个字的不算相关
    items = hits if isinstance(hits, list) else hits.get("items", [])
    assert any(n["title"] == "品牌设计报价经验" for n in items)


def test_normalize_endpoint_and_admin_edits(client, requester):
    h = auth(requester)
    r = client.get(f"{API}/skills/normalize", params={"skills": "VI设计,剪纸"}, headers=h).json()
    assert r["items"] == [{"skill": "VI设计", "canonical": "品牌设计", "known": True},
                          {"skill": "剪纸", "canonical": "剪纸", "known": False}]
    admin = make_admin(client, "13800170001", "运营")
    assert client.post(f"{API}/admin/skill-concepts", json={"name": "手工", "aliases": ["剪纸"]}, headers=h).status_code == 403
    c = client.post(f"{API}/admin/skill-concepts", json={"name": "手工", "aliases": ["剪纸", "折纸"]}, headers=auth(admin)).json()
    assert c["status"] == "active" and c["aliases"] == ["剪纸", "折纸"]
    assert client.get(f"{API}/skills/normalize", params={"skills": "剪纸"}, headers=h).json()["items"][0]["canonical"] == "手工"
    clash = client.post(f"{API}/admin/skill-concepts", json={"name": "手工2", "aliases": ["VI设计"]}, headers=auth(admin))
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "skill_alias_taken" and "品牌设计" in clash.json()["detail"]["message"]
    client.post(f"{API}/admin/skill-concepts/{c['id']}/retire", headers=auth(admin))
    assert client.get(f"{API}/skills/normalize", params={"skills": "剪纸"}, headers=h).json()["items"][0]["known"] is False
    view = client.get(f"{API}/admin/skill-concepts", headers=auth(admin)).json()
    assert any(x["name"] == "品牌设计" for x in view["effective"]) and view["overrides"][0]["status"] == "retired"


def test_responses_match_sdk_types(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    admin = make_admin(client, "13800170002", "运营")
    lst = client.get(f"{API}/skills/concepts", headers=auth(requester)).json()
    _assert_shape(lst, "SkillConceptList")
    first = lst["items"][0]
    _assert_shape(first, "SkillConceptView")
    n = client.get(f"{API}/skills/normalize", params={"skills": "VI设计"}, headers=auth(requester)).json()
    _assert_shape(n, "SkillNormalizeResult")
    item = n["items"][0]
    _assert_shape(item, "SkillNormalized")
    row = client.post(f"{API}/admin/skill-concepts", json={"name": "手工", "aliases": ["剪纸"]}, headers=auth(admin)).json()
    _assert_shape(row, "SkillConceptRow")
    v = client.get(f"{API}/admin/skill-concepts", headers=auth(admin)).json()
    _assert_shape(v, "SkillConceptAdminView")
