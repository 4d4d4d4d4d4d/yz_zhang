"""SCN-290 / SCN-291 第五十五轮场景发掘：室内设计出图、婚礼策划（398 号 spec，V425）。

两个新类目都不要资质：
- 「室内设计出图」：先量房问清、不动承重墙不改防水区（住宅室内装饰装修管理办法第五条）、按预算出、改图轮数与交付图纸写清、不拿暗扣；
- 「婚礼策划」：预算逐项透明不吃差价、合同由新人自己签定金看清（定金不超过两成）、流程单有备案、舞台与冷焰火安全、当天专人对接。
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


def test_design_pack_respects_structure_and_budget():
    d, problems = schema.validate(_load("interior-design"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("承重墙" in f for f in a.forbidden) and any("防水" in f for f in a.forbidden)
    assert any("不按预算" in f for f in a.forbidden) and any("回扣" in f for f in a.forbidden)
    assert any("改图轮数" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["室内设计出图"]
    t = d.task_templates[0].description
    assert "不拆改承重墙" in t and "水电点位" in t and "不拿暗扣" in t


def test_wedding_pack_keeps_money_transparent_and_lets_the_couple_sign():
    d, problems = schema.validate(_load("wedding-planning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("加价不告诉新人" in f for f in a.forbidden) and any("替新人签合同" in f for f in a.forbidden)
    assert any("备案" in f for f in a.forbidden) and any("明火烟花" in f for f in a.forbidden)
    assert any("专人对接" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["婚礼策划"]
    t = d.task_templates[0].description
    assert "报价原样给我们看" in t and "合同我们自己签" in t and "雨天" in t


@pytest.mark.parametrize("key", ["interior-design", "wedding-planning"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600042601")
    for title, cat in (("两居室装修出图", "室内设计出图"), ("十月婚礼统筹", "婚礼策划")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("interior-design", "interior-design-helper", ("13900006001", "13900006002"), "上门量房要问清什么", "先量房，问清预算、几口人和生活习惯"),
    ("interior-design", "interior-design-helper", ("13900006003", "13900006004"), "能拆承重墙吗", "不动承重墙、不扩大承重墙门窗、不把没防水的房间改成卫生间厨房"),
    ("interior-design", "interior-design-helper", ("13900006005", "13900006006"), "方案要按预算出吗", "方案按预算出，主材清单写清品牌档次"),
    ("interior-design", "interior-design-helper", ("13900006007", "13900006008"), "要交水电点位图吗", "改图轮数、交付哪些图和源文件写进约定"),
    ("interior-design", "interior-design-helper", ("13900006009", "13900006010"), "推荐材料能拿回扣吗", "推荐材料和施工队不拿暗扣，有合作关系要说明"),
    ("wedding-planning", "wedding-planning-helper", ("13900006011", "13900006012"), "预算要逐项列吗", "预算逐项列，供应商报价原样给新人，不吃差价"),
    ("wedding-planning", "wedding-planning-helper", ("13900006013", "13900006014"), "定金和退改条款要看什么", "合同由新人自己签，定金、退改条款看清"),
    ("wedding-planning", "wedding-planning-helper", ("13900006015", "13900006016"), "流程单要精确到分钟吗", "流程单精确到分钟，下雨迟到设备坏都有备案"),
    ("wedding-planning", "wedding-planning-helper", ("13900006017", "13900006018"), "能用烟花吗", "舞台灯架搭稳，室内不用明火烟花，冷焰火按场地要求"),
    ("wedding-planning", "wedding-planning-helper", ("13900006019", "13900006020"), "当天谁对接", "当天专人对接，物品清单逐项核"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("interior-design", "interior-design-helper", ("13900006021", "13900006022"), "不实用", "先量房，问清预算、几口人和生活习惯"),
    ("interior-design", "interior-design-helper", ("13900006023", "13900006024"), "打通", "不动承重墙、不扩大承重墙门窗、不把没防水的房间改成卫生间厨房"),
    ("interior-design", "interior-design-helper", ("13900006025", "13900006026"), "超了一倍", "方案按预算出，主材清单写清品牌档次"),
    ("interior-design", "interior-design-helper", ("13900006027", "13900006028"), "插座装哪", "改图轮数、交付哪些图和源文件写进约定"),
    ("wedding-planning", "wedding-planning-helper", ("13900006029", "13900006030"), "翻了一倍", "预算逐项列，供应商报价原样给新人，不吃差价"),
    ("wedding-planning", "wedding-planning-helper", ("13900006031", "13900006032"), "退不了", "合同由新人自己签，定金、退改条款看清"),
    ("wedding-planning", "wedding-planning-helper", ("13900006033", "13900006034"), "乱了", "流程单精确到分钟，下雨迟到设备坏都有备案"),
    ("wedding-planning", "wedding-planning-helper", ("13900006035", "13900006036"), "碰倒", "舞台灯架搭稳，室内不用明火烟花，冷焰火按场地要求"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
