"""SCN-190 / SCN-191 第十六轮场景发掘：上门回收废品、电动车上门维修（316 号 spec，V343）。

交付物是两个数据文件、两个新类目（都不要资质）。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_scrap_pack_weighs_in_front_of_the_customer():
    d, problems = schema.validate(_load("scrap-recycling"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("遥控改数" in f for f in a.forbidden) and any("压价" in f for f in a.forbidden)
    assert any("电缆" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["废品回收"]
    t = d.task_templates[0]
    assert "当面称" in t.visit_checklist and "我看秤" in t.description


def test_ebike_pack_never_modifies_batteries_or_speed_limits():
    d, problems = schema.validate(_load("ebike-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    for word in ("锂电池", "大容量", "限速", "鼓包"):
        assert any(word in f for f in a.forbidden), word
    assert "required_cert" not in _categories()["电动车维修"]
    t = d.task_templates[0]
    assert "不改装" in t.description and "检查电池与线路" in t.visit_checklist


def test_both_categories_take_applications_without_certificates(client, requester):
    w = make_verified(client, "13600003431")
    for title, cat in (("收一堆旧纸箱", "废品回收"), ("电动车后胎漏气", "电动车维修")):
        r = _post(client, requester, title=title, description="尽快", category=cat)
        assert r.status_code in (200, 201), r.text
        assert client.post(f"{API}/tasks/{r.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201, cat


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("scrap-recycling", "scrap-helper", ("13900003431", "13900003432"), "客户怀疑我的秤不准怎么办", "当面称、让客户看秤，不用「违规秤」"),
    ("scrap-recycling", "scrap-helper", ("13900003433", "13900003434"), "有人卖成捆的新电缆能收吗", "来路不明的电缆、井盖、公共设施不收"),
    ("ebike-repair", "ebike-helper", ("13900003435", "13900003436"), "客户要把铅酸电池改成锂电池能改吗", "不改装：不铅酸改锂电、不拆限速、不提电压"),
    ("ebike-repair", "ebike-helper", ("13900003437", "13900003438"), "电池鼓包了还能充电吗", "电池鼓包、线路烧焦：先断电，别再进楼充电"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
