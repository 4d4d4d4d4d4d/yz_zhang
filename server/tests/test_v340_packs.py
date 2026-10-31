"""SCN-186 / SCN-187 第十五轮场景发掘：老人上门助浴、上门理发（313 号 spec，V340）。

交付物是两个数据文件、两个新类目；「老人助浴」要审核通过的健康证明（贴身照护）。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_bathing_pack_assesses_first_and_never_works_alone():
    d, problems = schema.validate(_load("elder-bathing"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("血压过高" in f for f in a.forbidden) and any("一个人搬动" in f for f in a.forbidden)
    assert any("拍老人身体" in f for f in a.forbidden) and any("医疗诊断" in f for f in a.forbidden)
    assert _categories()["老人助浴"].get("required_cert") == "健康证明"
    t = d.task_templates[0]
    assert "量血压体温" in t.visit_checklist and "两人一组" in t.description


def test_haircut_pack_keeps_tools_clean_and_prices_upfront():
    d, problems = schema.validate(_load("home-haircut"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不消毒" in f for f in a.forbidden) and any("再加价" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["上门理发"]
    assert "工具消毒" in d.task_templates[0].visit_checklist


def test_only_health_certified_helpers_can_take_bathing_orders(client, requester):
    t = _post(client, requester, title="给我爸上门助浴", description="八十五岁，能坐", category="老人助浴").json()
    w = make_verified(client, "13600003401")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "健康证明" in r.json()["detail"]["message"]
    cut = _post(client, requester, title="上门给奶奶理发", description="卧床", category="上门理发").json()
    assert client.post(f"{API}/tasks/{cut['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("elder-bathing", "bathing-helper", ("13900003401", "13900003402"), "老人血压高还能洗澡吗", "洗之前先评估：量血压体温，这些情况不洗"),
    ("elder-bathing", "bathing-helper", ("13900003403", "13900003404"), "洗到一半老人头晕胸闷怎么办", "头晕、胸闷、脸色发白：马上停"),
    ("home-haircut", "haircut-helper", ("13900003405", "13900003406"), "卧床的老人怎么理发", "卧床的老人怎么剪"),
    ("home-haircut", "haircut-helper", ("13900003407", "13900003408"), "理发工具要消毒吗", "工具每次清洁消毒，一人一用"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
