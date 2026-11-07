"""SCN-296 / SCN-297 第五十八轮场景发掘：展台搭建、外卖店铺代运营（406 号 spec，V433）。

两个新类目都不要资质（展台里 2 米以上作业、接电要持证的，知识与禁止项里写明）：
- 「展台搭建」：按场馆规定报图、结构搭稳不超限高（高处作业持证）、持证电工从指定电箱接电、
  装饰材料阻燃（消防法第二十六条）、按时撤场清垃圾；
- 「外卖店铺代运营」：不刷单不搞好评返现（电子商务法第十七条、反不正当竞争法第八条）、菜品如实、
  改价与活动先经店主确认、用子账号不要主账号密码、每周报数据且不外传。
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


def test_booth_pack_keeps_structure_power_and_fire_safe():
    d, problems = schema.validate(_load("exhibition-booth"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不报图" in f for f in a.forbidden) and any("高处作业证" in f for f in a.forbidden)
    assert any("持证电工" in f for f in a.forbidden) and any("阻燃" in f for f in a.forbidden)
    assert any("超时撤场" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["展台搭建"]
    t = d.task_templates[0].description
    assert "报图" in t and "持证电工" in t and "材料阻燃" in t


def test_food_delivery_pack_refuses_fake_orders_and_master_passwords():
    d, problems = schema.validate(_load("food-delivery-ops"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("刷单" in f for f in a.forbidden) and any("虚假图片" in f for f in a.forbidden)
    assert any("不经店主确认" in f for f in a.forbidden) and any("主账号密码" in f for f in a.forbidden)
    assert any("数据外传" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["外卖店铺代运营"]
    t = d.task_templates[0].description
    assert "不刷单" in t and "子账号" in t and "数据不外传" in t


@pytest.mark.parametrize("key", ["exhibition-booth", "food-delivery-ops"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600043301")
    for title, cat in (("家居展 36 平米展位搭建", "展台搭建"), ("小面馆外卖店铺托管三个月", "外卖店铺代运营")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("exhibition-booth", "exhibition-booth-helper", ("13900009001", "13900009002"), "要提前报图吗", "按场馆规定报图审图，搭出来和图纸一致"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009003", "13900009004"), "背板要怎么加固", "结构搭稳不超限高，2 米以上作业持证系安全带"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009005", "13900009006"), "用电要持证电工接吗", "用电由持证电工从场馆指定电箱接，不私拉乱接"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009007", "13900009008"), "装饰材料要阻燃吗", "装饰材料阻燃，消防通道不堵，灭火器放到位"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009009", "13900009010"), "撤场要清走垃圾吗", "按时进撤场，垃圾清走，押金和加班费事先说清"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009011", "13900009012"), "可以帮店主刷单吗", "不刷单、不搞好评返现，也不帮店主做这些"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009013", "13900009014"), "菜品图片要怎么拍", "菜品图片、分量、价格、过敏原如实写"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009015", "13900009016"), "满减活动要店主确认吗", "改价、满减、平台活动先经店主确认，算清还赚不赚"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009017", "13900009018"), "要主账号密码吗", "用子账号或平台授权登录，不要主账号密码和提现权限"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009019", "13900009020"), "每周要报什么数据", "每周报数据，店铺经营数据不外传"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("exhibition-booth", "exhibition-booth-helper", ("13900009021", "13900009022"), "被叫停", "按场馆规定报图审图，搭出来和图纸一致"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009023", "13900009024"), "砸到人", "结构搭稳不超限高，2 米以上作业持证系安全带"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009025", "13900009026"), "跳闸", "用电由持证电工从场馆指定电箱接，不私拉乱接"),
    ("exhibition-booth", "exhibition-booth-helper", ("13900009027", "13900009028"), "消防检查", "装饰材料阻燃，消防通道不堵，灭火器放到位"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009029", "13900009030"), "补单", "不刷单、不搞好评返现，也不帮店主做这些"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009031", "13900009032"), "照骗", "菜品图片、分量、价格、过敏原如实写"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009033", "13900009034"), "倒贴", "改价、满减、平台活动先经店主确认，算清还赚不赚"),
    ("food-delivery-ops", "food-delivery-ops-helper", ("13900009035", "13900009036"), "登不上", "用子账号或平台授权登录，不要主账号密码和提现权限"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
