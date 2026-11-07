"""SCN-153 / SCN-154 第八轮场景发掘：整理收纳、上门做饭（274 号 spec，V298）。

交付物是两个数据文件 + 「上门做饭」类目要健康证明（食品安全法第四十五条：每年体检、取得健康证明后方可上岗）。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_organizing_pack_keeps_customer_items_and_photos_with_the_customer():
    d, problems = schema.validate(_load("home-organizing"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("丢弃" in f for f in a.forbidden) and any("照片" in f for f in a.forbidden)
    assert "整理收纳" in _categories() and a.fallback_category == "整理收纳"
    assert {t.category for t in d.task_templates} == {"整理收纳"}


def test_cooking_pack_and_category_need_a_health_certificate():
    d, problems = schema.validate(_load("home-cooking"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("健康证明" in f for f in a.forbidden) and any("医疗" in f for f in a.forbidden)
    assert _categories()["上门做饭"].get("required_cert") == "健康证明"
    assert {t.category for t in d.task_templates} == {"上门做饭"}
    assert all("过敏" in t.description for t in d.task_templates), "模板里要问过敏"


def test_only_cooks_with_a_health_certificate_can_apply(client, requester):
    t = _post(client, requester, title="周末上门做一顿家常菜", description="三口之家", category="上门做饭").json()
    cook = make_verified(client, "13600002981")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(cook))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "健康证明" in r.json()["detail"]["message"]
    plain = _post(client, requester, title="衣橱整理", description="两个柜子", category="整理收纳").json()
    assert client.post(f"{API}/tasks/{plain['id']}/applications", json={}, headers=auth(cook)).status_code == 201, "整理收纳不要证书"


def test_health_certificate_must_carry_an_expiry_within_a_year(client):
    cook = make_verified(client, "13600002982")
    r = apply_cert(client, cook, name="健康证明", expires_at=None)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_required"
    assert "健康证明" in r.json()["detail"]["message"]
    r = apply_cert(client, cook, name="健康证明", expires_at=(utcnow() + timedelta(days=400)).isoformat())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_too_far"
    assert apply_cert(client, cook, name="健康证明").status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("home-organizing", "organizer-helper", ("13900002981", "13900002982"), "整理时清出来的旧物可以直接丢吗", "客户的东西丢不丢，由客户逐件定"),
    ("home-organizing", "organizer-helper", ("13900002983", "13900002984"), "能拍客户家的前后对比照发作品集吗", "前后对比照：先问，再拍，不拍到人"),
    ("home-cooking", "home-cook-helper", ("13900002985", "13900002986"), "上门做饭要健康证吗", "接上门做饭的单要有健康证明"),
    ("home-cooking", "home-cook-helper", ("13900002987", "13900002988"), "客户说孩子对花生过敏怎么办", "过敏原要逐项问、写进单里"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])
