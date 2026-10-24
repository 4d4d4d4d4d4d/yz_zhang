"""SCN-106 发单时就提示创作类需求的九项（140 号 spec）。

137 号的需求单体检要先启用场景包再问助手；更早的地方是**发单页**：发布方写海报需求时就告诉他还缺什么。
只是提示：不计入「说明完整度」，原来的分数口径（126 号）不变。
"""
from app.modules.packs.creator import ITEMS
from tests.conftest import auth

API = "/api/v1/profiles/task-draft"


def _draft(client, user, **body):
    r = client.post(API, json=body, headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def test_design_draft_lists_the_nine_items_and_what_to_ask(client, requester):
    p = _draft(client, requester, title="奶茶店开业海报", description="要 3 张竖版海报，用于门店", category="设计")
    b = p["brief"]
    assert [i["name"] for i in b["items"]] == [name for name, _, _ in ITEMS]
    ok = {i["name"] for i in b["items"] if i["ok"]}
    assert ok == {"用途", "数量", "尺寸规格"}
    assert b["missing"] == 6
    asks = {i["name"]: i["ask"] for i in b["items"]}
    assert asks["版权授权"].startswith("版权怎么约定")


def test_form_fields_count_as_written(client, requester):
    """预算、截止时间在表单里填了，就不该再提示「没写预算」。"""
    p = _draft(client, requester, title="海报", description="门店海报", category="设计",
               budget_cents=50000, deadline="2026-12-01T10:00:00Z")
    ok = {i["name"] for i in p["brief"]["items"] if i["ok"]}
    assert {"预算", "交期"} <= ok


def test_skill_concepts_make_it_a_creative_job_even_without_the_category(client, requester):
    p = _draft(client, requester, title="做个标志", description="", required_skills=["VI设计"])
    assert p["brief"] is not None and p["brief"]["missing"] == len(ITEMS)


def test_other_jobs_have_no_brief_and_completeness_is_unchanged(client, requester):
    p = _draft(client, requester, title="两居室保洁", description="周六上午，两居室深度保洁", category="保洁")
    assert p["brief"] is None
    a = _draft(client, requester, title="设计一套门店海报", description="x" * 40, category="设计", budget_cents=1)
    b = _draft(client, requester, title="设计一套门店海报", description="x" * 40, category="保洁", budget_cents=1)
    assert a["completeness"] == b["completeness"], "九项只是提示，不改说明完整度的口径"


def test_shape(client, requester):
    from tests.test_client_shape_alignment import _assert_shape

    p = _draft(client, requester, title="海报", description="门店海报", category="设计")
    _assert_shape(p, "TaskProfile")
    brief = p["brief"]
    _assert_shape(brief, "TaskBrief")
    first = brief["items"][0]
    _assert_shape(first, "TaskBriefItem")
