"""SCN-292 / SCN-293 第五十六轮场景发掘：网店代发货打包、用户访谈招募与执行（400 号 spec，V427）。

两个新类目都不要资质：
- 「网店代发货打包」：按单核对、易碎品封箱前拍照、买家姓名电话地址只用于这一单（个保法第二十一条）、
  禁寄物品不发且品名如实（快递暂行条例第二十二条）、每天回填单号对账；
- 「用户访谈」：先写清要了解什么再按条件筛人、不找托不编记录、录音录像先征得同意（个保法第十四条）、
  礼金按约定付、记录去掉姓名电话只交委托方（个保法第二十一条）。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091）离线试过。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_fulfillment_pack_checks_orders_and_keeps_buyer_info_private():
    d, problems = schema.validate(_load("ecommerce-fulfillment"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不核对" in f for f in a.forbidden) and any("拍照留底" in f for f in a.forbidden)
    assert any("买家姓名电话地址" in f for f in a.forbidden) and any("禁止寄递" in f for f in a.forbidden)
    assert any("不补发" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["网店代发货打包"]
    t = d.task_templates[0].description
    assert "不截图外传" in t and "品名如实" in t and "回填单号" in t


def test_interview_pack_requires_consent_and_real_participants():
    d, problems = schema.validate(_load("user-interview"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("找托" in f for f in a.forbidden) and any("不经同意录音录像" in f for f in a.forbidden)
    assert any("礼金" in f for f in a.forbidden) and any("外传或转卖" in f for f in a.forbidden)
    assert any("诱导" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["用户访谈"]
    t = d.task_templates[0].description
    assert "征得同意" in t and "不找托" in t and "去掉姓名电话" in t


@pytest.mark.parametrize("key", ["ecommerce-fulfillment", "user-interview"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600042701")
    for title, cat in (("双十一帮忙打包发货", "网店代发货打包"), ("约 6 位用户聊聊记账习惯", "用户访谈")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007001", "13900007002"), "装箱前要核对什么", "按单拣货，核对货号、规格、数量再装箱"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007003", "13900007004"), "易碎品怎么打包", "易碎品加固包装，封箱前拍照留底"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007005", "13900007006"), "面单上的电话能留着吗", "买家姓名电话地址只用于这一单，不外传、不留存"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007007", "13900007008"), "香水能寄吗", "禁止寄递的物品不发，品名如实填写"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007009", "13900007010"), "每天要对账吗", "每天回填单号对账，发错漏发按约定补发"),
    ("user-interview", "user-interview-helper", ("13900007011", "13900007012"), "受访者要按什么条件筛", "先写清要了解什么，再按条件筛人"),
    ("user-interview", "user-interview-helper", ("13900007013", "13900007014"), "可以找熟人凑数吗", "不找托、不拿熟人凑数，记录不编造"),
    ("user-interview", "user-interview-helper", ("13900007015", "13900007016"), "录音要对方同意吗", "录音录像前说明用途并征得同意，对方可以拒绝"),
    ("user-interview", "user-interview-helper", ("13900007017", "13900007018"), "礼金什么时候付", "礼金多少、怎么付事先说清，按约定付"),
    ("user-interview", "user-interview-helper", ("13900007019", "13900007020"), "访谈记录要去掉姓名吗", "记录去掉姓名电话，只交委托方用于这次研究"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007021", "13900007022"), "颜色不对", "按单拣货，核对货号、规格、数量再装箱"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007023", "13900007024"), "漏液", "易碎品加固包装，封箱前拍照留底"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007025", "13900007026"), "截图", "买家姓名电话地址只用于这一单，不外传、不留存"),
    ("ecommerce-fulfillment", "fulfillment-helper", ("13900007027", "13900007028"), "充电宝", "禁止寄递的物品不发，品名如实填写"),
    ("user-interview", "user-interview-helper", ("13900007029", "13900007030"), "白聊", "先写清要了解什么，再按条件筛人"),
    ("user-interview", "user-interview-helper", ("13900007031", "13900007032"), "全是好评", "不找托、不拿熟人凑数，记录不编造"),
    ("user-interview", "user-interview-helper", ("13900007033", "13900007034"), "事后才知道", "录音录像前说明用途并征得同意，对方可以拒绝"),
    ("user-interview", "user-interview-helper", ("13900007035", "13900007036"), "拖了一个月", "礼金多少、怎么付事先说清，按约定付"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
