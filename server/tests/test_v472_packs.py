"""SCN-333 / SCN-334 第七十六轮场景发掘：鱼缸水族维护、形象穿搭顾问（445 号 spec，V472）。

- 「鱼缸水族维护」不要资质：动手前断电湿手不碰插头（消保法第十八条）、换水不超过三分之一新水除氯调温、
  不用洗洁精滤棉用旧水洗、病鱼隔离拍照告诉主人不乱下药（第五十二条）、代喂按约定的量宁少勿多；
- 「形象穿搭顾问」不要资质：在预算里配不推贵的、陪购不收商家回扣（消保法第二十条）、谈身材只说合身不评美丑
  （民法典第一千零一十九条）、试穿照片用完即删（个保法第六条）、写清包括几次修改。
问法写测试之前都先用 scripts/pack_probe.py 离线试过；写完用 scripts/pack_mutate.py（PACK-094）做变异红验。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_aquarium_pack_powers_off_first_and_never_uses_detergent():
    d, problems = schema.validate(_load("aquarium-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("带电操作" in f for f in a.forbidden) and any("大半缸生水" in f for f in a.forbidden)
    assert any("洗洁精" in f for f in a.forbidden) and any("乱下药" in f for f in a.forbidden)
    assert any("多喂" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["鱼缸水族维护"]
    t = d.task_templates[0].description
    assert "拔加热棒" in t and "不超过三分之一" in t and "不乱下药" in t


def test_style_pack_stays_in_budget_takes_no_kickbacks_and_deletes_photos():
    d, problems = schema.validate(_load("style-consultant"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("超出客户预算" in f for f in a.forbidden) and any("回扣" in f for f in a.forbidden)
    assert any("美丑" in f for f in a.forbidden) and any("做案例" in f for f in a.forbidden)
    assert any("加钱" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["形象穿搭顾问"]
    t = d.task_templates[0].description
    assert "在预算里配" in t and "不收商家回扣" in t and "用完即删" in t


@pytest.mark.parametrize("key", ["aquarium-care", "style-consultant"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications(client, requester):
    w = make_verified(client, "13600047201")
    for title, cat in (("客厅鱼缸换水", "鱼缸水族维护"), ("面试穿搭方案", "形象穿搭顾问")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("aquarium-care", "aquarium-helper", ("13700472001", "13700472002"), "插头怎么拔", "动手前先拔掉加热棒和水泵的电，湿手不碰插头"),
    ("aquarium-care", "aquarium-helper", ("13700472003", "13700472004"), "一次换多少水", "每次换水不超过三分之一，新水先除氯、调温再加"),
    ("aquarium-care", "aquarium-helper", ("13700472005", "13700472006"), "能用洗洁精吗", "刷缸、洗滤材不用洗洁精，滤棉用换出来的旧水洗，不全换"),
    ("aquarium-care", "aquarium-helper", ("13700472007", "13700472008"), "病鱼怎么处理", "看到病鱼先捞出来隔离，拍照告诉主人，不自己乱下药"),
    ("aquarium-care", "aquarium-helper", ("13700472009", "13700472010"), "主人出门怎么喂", "主人出门代喂，按约定的量，宁少勿多"),
    ("style-consultant", "style-helper", ("13700472011", "13700472012"), "预算怎么定", "先问清预算、场合和平时风格，在预算里配，不往贵的推"),
    ("style-consultant", "style-helper", ("13700472013", "13700472014"), "陪购能拿提成吗", "陪购只按客户的利益挑，不收商家回扣，有合作的店事先说明"),
    ("style-consultant", "style-helper", ("13700472015", "13700472016"), "身材怎么说", "谈身材只说哪里合身、怎么修饰，不评美丑、不开玩笑"),
    ("style-consultant", "style-helper", ("13700472017", "13700472018"), "照片怎么处理", "试穿照片和身材数据只用于这次方案，用完删掉，不拿去做案例"),
    ("style-consultant", "style-helper", ("13700472019", "13700472020"), "改几次要加钱吗", "按次或按方案收费，写清包括几次修改、陪购几小时"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("aquarium-care", "aquarium-helper", ("13700472021", "13700472022"), "跳闸", "动手前先拔掉加热棒和水泵的电，湿手不碰插头"),
    ("aquarium-care", "aquarium-helper", ("13700472023", "13700472024"), "翻肚", "每次换水不超过三分之一，新水先除氯、调温再加"),
    ("aquarium-care", "aquarium-helper", ("13700472025", "13700472026"), "泡沫", "刷缸、洗滤材不用洗洁精，滤棉用换出来的旧水洗，不全换"),
    ("aquarium-care", "aquarium-helper", ("13700472027", "13700472028"), "回来才发现", "看到病鱼先捞出来隔离，拍照告诉主人，不自己乱下药"),
    ("style-consultant", "style-helper", ("13700472029", "13700472030"), "压箱底", "先问清预算、场合和平时风格，在预算里配，不往贵的推"),
    ("style-consultant", "style-helper", ("13700472031", "13700472032"), "拿好处", "陪购只按客户的利益挑，不收商家回扣，有合作的店事先说明"),
    ("style-consultant", "style-helper", ("13700472033", "13700472034"), "自卑", "谈身材只说哪里合身、怎么修饰，不评美丑、不开玩笑"),
    ("style-consultant", "style-helper", ("13700472035", "13700472036"), "朋友圈", "试穿照片和身材数据只用于这次方案，用完删掉，不拿去做案例"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
