"""SCN-314 / SCN-315 第六十七轮场景发掘：民宿退房保洁、露营搭建（427 号 spec，V454）。

两个新类目都不要资质：
- 「民宿退房保洁」：先查损坏遗留物拍照报房东、布草一客一换（公共场所卫生管理条例）、按清单打扫拍完成照、
  赶在下一位入住前、遗留物登记交房东不外传门锁密码（民法典第三百一十四条）；
- 「露营搭建」：只在允许的营地不进河滩、地钉风绳打牢大风撤天幕、炭火远离帐篷不在帐篷里烧炭、
  装备押金写清（消保法第二十条）、撤场带走垃圾（民法典第一千一百九十八条，组织者安全保障义务）。
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


def test_homestay_pack_changes_linen_and_hands_lost_items_to_the_host():
    d, problems = schema.validate(_load("homestay-turnover"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不查损坏" in f for f in a.forbidden) and any("布草不换" in f for f in a.forbidden)
    assert any("不按清单" in f for f in a.forbidden) and any("门锁密码" in f for f in a.forbidden)
    assert any("赔偿" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["民宿退房保洁"]
    t = d.task_templates[0].description
    assert "一客一换" in t and "拍照发房东" in t and "门锁密码不外传" in t


def test_camping_pack_avoids_riverbeds_and_never_burns_charcoal_in_tents():
    d, problems = schema.validate(_load("camping-setup"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("河滩" in f for f in a.forbidden) and any("地钉风绳" in f for f in a.forbidden)
    assert any("帐篷里烧炭" in f for f in a.forbidden) and any("押金" in f for f in a.forbidden)
    assert any("垃圾" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["露营搭建"]
    t = d.task_templates[0].description
    assert "不在河滩" in t and "帐篷里不烧炭" in t and "带走垃圾" in t


@pytest.mark.parametrize("key", ["homestay-turnover", "camping-setup"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600045401")
    for title, cat in (("周日退房后保洁", "民宿退房保洁"), ("周末营地搭帐篷天幕", "露营搭建")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("homestay-turnover", "homestay-turnover-helper", ("13700454001", "13700454002"), "进门先查什么", "进门先查损坏和遗留物，拍照发房东，赔不赔由房东定"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454003", "13700454004"), "布草要一客一换吗", "床单被套毛巾一客一换，脏的送洗不重复用"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454005", "13700454006"), "打扫按什么清单", "按清单打扫、补耗品，做完拍照"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454007", "13700454008"), "来不及怎么办", "赶在下一位入住前做完，来不及提前告诉房东"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454009", "13700454010"), "客人落下东西怎么办", "遗留物登记交房东，不拍客人私物，门锁密码不外传"),
    ("camping-setup", "camping-setup-helper", ("13700454011", "13700454012"), "营地怎么选", "只在允许的营地搭，不进河滩、低洼和禁营区"),
    ("camping-setup", "camping-setup-helper", ("13700454013", "13700454014"), "风大怎么办", "地钉风绳打牢，风大了降低天幕或撤掉"),
    ("camping-setup", "camping-setup-helper", ("13700454015", "13700454016"), "帐篷里能烧炭吗", "炭火炉具远离帐篷，绝不在帐篷里烧炭取暖"),
    ("camping-setup", "camping-setup-helper", ("13700454017", "13700454018"), "押金怎么算", "装备清单、押金、损坏怎么算事先写清"),
    ("camping-setup", "camping-setup-helper", ("13700454019", "13700454020"), "撤场要做什么", "撤场带走全部垃圾，地钉坑填平，营地恢复原状"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("homestay-turnover", "homestay-turnover-helper", ("13700454021", "13700454022"), "摔坏", "进门先查损坏和遗留物，拍照发房东，赔不赔由房东定"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454023", "13700454024"), "头发", "床单被套毛巾一客一换，脏的送洗不重复用"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454025", "13700454026"), "差评", "按清单打扫、补耗品，做完拍照"),
    ("homestay-turnover", "homestay-turnover-helper", ("13700454027", "13700454028"), "耳机", "遗留物登记交房东，不拍客人私物，门锁密码不外传"),
    ("camping-setup", "camping-setup-helper", ("13700454029", "13700454030"), "冲走", "只在允许的营地搭，不进河滩、低洼和禁营区"),
    ("camping-setup", "camping-setup-helper", ("13700454031", "13700454032"), "掀翻", "地钉风绳打牢，风大了降低天幕或撤掉"),
    ("camping-setup", "camping-setup-helper", ("13700454033", "13700454034"), "没醒过来", "炭火炉具远离帐篷，绝不在帐篷里烧炭取暖"),
    ("camping-setup", "camping-setup-helper", ("13700454035", "13700454036"), "扣了一半", "装备清单、押金、损坏怎么算事先写清"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
