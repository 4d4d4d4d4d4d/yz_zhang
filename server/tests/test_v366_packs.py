"""SCN-225 / SCN-226 第二十五轮场景发掘：派对与气球布置、除甲醛治理（339 号 spec，V366）。

两个数据文件、两个新类目（都不要资质）。气球只用氦气、不挡消防通道；除甲醛不承诺零甲醛、不出检测报告、
检测交给客户自己选的有 CMA 资质的机构。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_party_decor_pack_uses_helium_only_and_keeps_exits_clear():
    d, problems = schema.validate(_load("party-decor"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("氢气" in f for f in a.forbidden) and any("安全出口" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["派对布置"]
    t = d.task_templates[0]
    assert "只用氦气" in t.description and "不挡安全出口" in t.description
    assert "进场先看安全出口与灭火器" in t.visit_checklist


def test_formaldehyde_pack_never_promises_zero_and_leaves_testing_to_cma_labs():
    d, problems = schema.validate(_load("formaldehyde-treatment"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("零甲醛" in f for f in a.forbidden) and any("指定检测机构" in f for f in a.forbidden)
    assert any("出具检测报告" in f for f in a.forbidden) and any("试纸" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["除甲醛治理"]
    t = d.task_templates[0].description
    assert "CMA" in t and "0.08 mg/m³" in t and "关窗 12 小时" in t


@pytest.mark.parametrize("key", ["party-decor", "formaldehyde-treatment"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_orders_without_certificates(client, requester):
    w = make_verified(client, "13600003661")
    for cat, title in (("派对布置", "宝宝宴气球布置"), ("除甲醛治理", "新房除甲醛")):
        t = _post(client, requester, title=title, description="周六上午", category=cat)
        assert t.status_code in (200, 201), t.text
        assert client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("party-decor", "party-decor-helper", ("13900003671", "13900003672"), "客户嫌氦气贵想用便宜的气", "飘空气球只用氦气，不用氢气"),
    ("party-decor", "party-decor-helper", ("13900003673", "13900003674"), "酒店能不能贴胶带", "先问场地让不让贴、让不让挂"),
    ("party-decor", "party-decor-helper", ("13900003675", "13900003676"), "拱门放在门口被要求拆", "不挡安全出口和消防通道，气球布幔远离明火"),
    ("party-decor", "party-decor-helper", ("13900003677", "13900003678"), "客户说气球数量对不上", "数量、尺寸、含不含氦气，分项写进报价"),
    ("formaldehyde-treatment", "formaldehyde-helper", ("13900003679", "13900003680"), "客户要我保证一次除净", "不承诺「零甲醛」「永久除醛」"),
    ("formaldehyde-treatment", "formaldehyde-helper", ("13900003681", "13900003682"), "客户要我推荐个检测机构", "治理方不出检测报告、不指定检测机构"),
    ("formaldehyde-treatment", "formaldehyde-helper", ("13900003683", "13900003684"), "客户拿试纸说还是超标", "按标准的采样条件检测，试纸读数只当参考"),
    ("formaldehyde-treatment", "formaldehyde-helper", ("13900003685", "13900003686"), "多少算合格", "验收看国标限值：甲醛 0.08 mg/m³"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("party-decor", "party-decor-helper", ("13900003687", "13900003688"), "上回炸了吓到小孩", "飘空气球只用氦气，不用氢气"),
    ("party-decor", "party-decor-helper", ("13900003689", "13900003690"), "掉漆了谁负责", "先问场地让不让贴、让不让挂"),
    ("formaldehyde-treatment", "formaldehyde-helper", ("13900003691", "13900003692"), "客户让我打包票", "不承诺「零甲醛」「永久除醛」"),
    ("formaldehyde-treatment", "formaldehyde-helper", ("13900003693", "13900003694"), "客户怕我们串通好了", "治理方不出检测报告、不指定检测机构"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
