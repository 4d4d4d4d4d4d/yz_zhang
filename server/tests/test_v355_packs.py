"""SCN-203 / SCN-204 第二十轮场景发掘：上门跟妆、小店网站与小程序搭建（328 号 spec，V355）。

交付物是两个数据文件、两个新类目（都不要资质）。跟妆的关口是正规产品、工具一人一清洁、先试敏、不临时换人；
建站的关口是需求写成清单、源码与著作权归属写进合同（没约定默认归开发方）、账号在客户名下、上线前备案。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_makeup_pack_uses_licensed_products_clean_tools_and_patch_tests():
    d, problems = schema.validate(_load("makeup-artist"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("三无化妆品" in f for f in a.forbidden) and any("共用不清洁" in f for f in a.forbidden)
    assert any("不试敏" in f for f in a.forbidden) and any("临时换人" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["上门跟妆"]
    t = d.task_templates[0]
    assert "试敏" in t.visit_checklist and "不临时换人" in t.description


def test_site_pack_writes_down_scope_ownership_accounts_and_filing():
    d, problems = schema.validate(_load("small-site-builder"))
    assert d is not None and not problems, problems
    assert d.segment == "studio"
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates), "签合同与收钱是人工关口"
    assert any("开发方名下" in f for f in a.forbidden) and any("源码归属不写进合同" in f for f in a.forbidden)
    assert any("不备案" in f for f in a.forbidden) and any("后门" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["网站小程序搭建"]
    t = d.task_templates[0]
    assert "我的主体注册" in t.description and "备案" in t.description and "著作权" in t.description


def test_both_categories_take_orders_without_certificates(client, requester):
    w = make_verified(client, "13600003551")
    for title, cat, remote in (("婚礼跟妆", "上门跟妆", False), ("做个点单小程序", "网站小程序搭建", True)):
        t = _post(client, requester, title=title, description="x", category=cat, is_remote=remote)
        assert t.status_code in (200, 201), t.text
        assert client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("makeup-artist", "makeup-helper", ("13900003551", "13900003552"), "客户化完妆脸上起疹子怎么办", "易过敏的先试敏；过敏马上停用"),
    ("makeup-artist", "makeup-helper", ("13900003553", "13900003554"), "几个伴娘能共用一把刷子吗", "刷具粉扑一人一清洁"),
    ("makeup-artist", "makeup-helper", ("13900003555", "13900003556"), "那天去不了能找朋友替班吗", "说好是谁就是谁：不临时换人"),
    ("small-site-builder", "site-builder-helper", ("13900003557", "13900003558"), "做完了客户要源代码给不给", "源码给不给、著作权归谁：写进合同"),
    ("small-site-builder", "site-builder-helper", ("13900003559", "13900003560"), "小程序上线前要ICP吗", "上线前要备案，留出审核时间"),
    ("small-site-builder", "site-builder-helper", ("13900003561", "13900003562"), "域名用我自己的身份证注册行吗", "域名、小程序、服务器都注册在客户名下"),
    # 人们真正会说的话：正文与标题里没有这些词，靠标签接住
    ("small-site-builder", "site-builder-helper", ("13900003563", "13900003564"), "需要办ICP吗", "上线前要备案，留出审核时间"),
    ("small-site-builder", "site-builder-helper", ("13900003565", "13900003566"), "客户要源代码", "源码给不给、著作权归谁：写进合同"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
