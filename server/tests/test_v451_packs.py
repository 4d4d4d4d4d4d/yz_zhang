"""SCN-310 / SCN-311 第六十五轮场景发掘：上门取送洗衣、老人助餐送餐（424 号 spec，V451）。

两个新类目都不要资质：
- 「上门取送洗衣」：取件当面清点拍照、按洗涤标识选洗法、按件报价写清时间、洗坏丢失按约定赔
  （消保法第五十二条）、口袋里的东西当面交回（民法典第三百一十四条）；
- 「老人助餐送餐」：先问清忌口过敏和慢病饮食、只送有许可的餐不私做私卖（食品安全法第三十五条）、
  保温按时当面交到手、留意老人状况异常告诉家属、不收额外的钱不推销。
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


def test_laundry_pack_counts_on_pickup_and_returns_pocket_items():
    d, problems = schema.validate(_load("laundry-pickup"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不清点不拍照" in f for f in a.forbidden) and any("洗涤标识" in f for f in a.forbidden)
    assert any("取送时间" in f for f in a.forbidden) and any("推脱不赔" in f for f in a.forbidden)
    assert any("口袋里的东西" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["上门取送洗衣"]
    t = d.task_templates[0].description
    assert "当面清点" in t and "洗涤标识" in t and "口袋里的东西当面交回" in t


def test_elder_meal_pack_checks_the_diet_and_hands_meals_over_in_person():
    d, problems = schema.validate(_load("elder-meal-delivery"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("忌口过敏" in f for f in a.forbidden) and any("自己在家做" in f for f in a.forbidden)
    assert any("放门口" in f for f in a.forbidden) and any("告诉家属" in f for f in a.forbidden)
    assert any("推销" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["老人助餐送餐"]
    t = d.task_templates[0].description
    assert "有许可" in t and "当面交到手" in t and "告诉家属" in t


@pytest.mark.parametrize("key", ["laundry-pickup", "elder-meal-delivery"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600045101")
    for title, cat in (("每周取送一次洗衣", "上门取送洗衣"), ("给我妈每天送午饭", "老人助餐送餐")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("laundry-pickup", "laundry-pickup-helper", ("13700451001", "13700451002"), "取件要清点吗", "取件当面清点件数，拍下污渍和破损，双方确认"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451003", "13700451004"), "羊绒能水洗吗", "按洗涤标识选干洗还是水洗，特殊面料先问清再收"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451005", "13700451006"), "怎么报价", "按件按类型报价，取件和送回的时间写清"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451007", "13700451008"), "洗坏了怎么赔", "洗坏洗丢按事先约定的办法赔，洗不掉的先说"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451009", "13700451010"), "口袋里的东西怎么办", "口袋里的东西当面交回，衣服不外借不转卖"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451011", "13700451012"), "要问清哪些忌口", "先问清忌口、过敏和慢病饮食，做成饮食卡"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451013", "13700451014"), "能自己做饭送吗", "只送有许可的食堂餐馆的餐，不自己做了卖"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451015", "13700451016"), "饭能放门口吗", "保温箱按时送，当面交到老人手里"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451017", "13700451018"), "老人状况异常怎么办", "留意老人状况，异常马上告诉家属或社区"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451019", "13700451020"), "能推销保健品吗", "不收老人额外的钱，不推销保健品和理财"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("laundry-pickup", "laundry-pickup-helper", ("13700451021", "13700451022"), "少了一件", "取件当面清点件数，拍下污渍和破损，双方确认"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451023", "13700451024"), "缩成", "按洗涤标识选干洗还是水洗，特殊面料先问清再收"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451025", "13700451026"), "等了一个星期", "按件按类型报价，取件和送回的时间写清"),
    ("laundry-pickup", "laundry-pickup-helper", ("13700451027", "13700451028"), "五百块", "口袋里的东西当面交回，衣服不外借不转卖"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451029", "13700451030"), "甜汤", "先问清忌口、过敏和慢病饮食，做成饮食卡"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451031", "13700451032"), "拉肚子", "只送有许可的食堂餐馆的餐，不自己做了卖"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451033", "13700451034"), "一下午", "保温箱按时送，当面交到老人手里"),
    ("elder-meal-delivery", "elder-meal-helper", ("13700451035", "13700451036"), "第二天才发现", "留意老人状况，异常马上告诉家属或社区"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
