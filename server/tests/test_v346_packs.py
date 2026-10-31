"""SCN-193 / SCN-194 第十七轮场景发掘：防水补漏、上门开锁（319 号 spec，V346）。

交付物是两个数据文件、两个新类目；「上门开锁」要审核通过的开锁备案证明（多地按特种行业管理）。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_leak_pack_quotes_a_total_and_finds_the_leak_first():
    d, problems = schema.validate(_load("leak-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("胶水斤数" in f for f in a.forbidden) and any("不查漏点" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["防水补漏"]
    t = d.task_templates[0]
    assert "不按胶水斤数结算" in t.description and "查漏点" in t.visit_checklist


def test_locksmith_pack_verifies_identity_and_needs_a_filing():
    d, problems = schema.validate(_load("locksmith"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不核验身份" in f for f in a.forbidden) and any("没有备案" in f for f in a.forbidden)
    assert any("教别人开锁" in f for f in a.forbidden)
    assert _categories()["上门开锁"].get("required_cert") == "开锁备案证明"
    assert "核验身份" in d.task_templates[0].visit_checklist


def test_only_filed_locksmiths_can_take_lock_orders(client, requester):
    t = _post(client, requester, title="钥匙锁屋里了", description="防盗门", category="上门开锁").json()
    w = make_verified(client, "13600003461")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "开锁备案证明" in r.json()["detail"]["message"]
    leak = _post(client, requester, title="卫生间漏水到楼下", description="用水后才漏", category="防水补漏").json()
    assert client.post(f"{API}/tasks/{leak['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("leak-repair", "leak-helper", ("13900003461", "13900003462"), "注胶按斤收费怎么报价", "报总价，不按「每斤胶多少钱」报"),
    ("leak-repair", "leak-helper", ("13900003463", "13900003464"), "卫生间漏水先找漏点还是直接砸砖", "先查漏点：防水层坏了还是暗管漏水"),
    ("locksmith", "locksmith-helper", ("13900003465", "13900003466"), "开锁前要核验什么身份证件", "先核验是你家的门：对不上不开"),
    ("locksmith", "locksmith-helper", ("13900003467", "13900003468"), "开锁需要备案吗", "开锁要备案：没有备案不接单"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
