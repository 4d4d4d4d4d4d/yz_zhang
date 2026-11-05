"""SCN-298 / SCN-299 第五十九轮场景发掘：居家适老化改造、社区团购分拣配送（409 号 spec，V436）。

两个新类目都不要资质：
- 「居家适老化改造」：先上门评估按需要改不推销全套、扶手进实墙试拉、防滑铺平门槛高差改坡、
  补贴按当地清单如实申报、装完带老人走一遍并回访（无障碍环境建设法、消保法第二十条）；
- 「社区团购分拣配送」：按单核对分拣、冻品先进冷柜、取货名单只写尾号（个保法第二十一条）、
  缺货坏果如实登记按规则退、只发正规商品不私卖自制食品（食品安全法第三十五条）。
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


def test_elder_mod_pack_assesses_first_and_anchors_bars():
    d, problems = schema.validate(_load("elder-home-mod"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("推销全套" in f for f in a.forbidden) and any("拉力测试" in f for f in a.forbidden)
    assert any("门槛高差" in f for f in a.forbidden) and any("虚报补贴" in f for f in a.forbidden)
    assert any("带老人试用" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["居家适老化改造"]
    t = d.task_templates[0].description
    assert "先上门评估" in t and "实墙" in t and "如实申报" in t


def test_group_buy_pack_keeps_food_safe_and_numbers_masked():
    d, problems = schema.validate(_load("group-buy-helper"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不核对" in f for f in a.forbidden) and any("常温久放" in f for f in a.forbidden)
    assert any("完整手机号" in f for f in a.forbidden) and any("私下扣钱" in f for f in a.forbidden)
    assert any("私卖自制" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["社区团购分拣配送"]
    t = d.task_templates[0].description
    assert "按单核对" in t and "冷柜" in t and "尾号" in t


@pytest.mark.parametrize("key", ["elder-home-mod", "group-buy-helper"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600043601")
    for title, cat in (("给我爸卫生间装扶手", "居家适老化改造"), ("小区团购每天分拣两小时", "社区团购分拣配送")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("elder-home-mod", "elder-home-mod-helper", ("13700436001", "13700436002"), "上门先评估什么", "先上门评估，按老人的需要改，不推销全套"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436003", "13700436004"), "扶手要装在哪种墙上", "扶手打进实墙、用合适的锚栓，装好挂重试拉"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436005", "13700436006"), "防滑地胶怎么铺", "防滑地面整块铺平不翘边，门槛高差改坡或去掉"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436007", "13700436008"), "补贴怎么申报", "政府补贴按当地清单如实申报，不虚报项目"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436009", "13700436010"), "装完要教老人怎么用吗", "装完带老人走一遍、教会用，过一阵回访"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436011", "13700436012"), "分拣要核对什么", "按订单清单分拣，核对数量规格，按楼栋分好贴签"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436013", "13700436014"), "冻品到了先放哪", "冷冻冷藏的到货先进冷柜，送达时间写清"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436015", "13700436016"), "取货名单怎么写", "取货名单只写取件码或手机尾号，不贴完整手机号和门牌"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436017", "13700436018"), "坏果怎么处理", "缺货坏果如实登记，按平台规则退，不私下扣钱"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436019", "13700436020"), "能卖自己做的腊肉吗", "只发平台上架的正规商品，不私卖自制、散装食品"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("elder-home-mod", "elder-home-mod-helper", ("13700436021", "13700436022"), "套餐", "先上门评估，按老人的需要改，不推销全套"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436023", "13700436024"), "一撑", "扶手打进实墙、用合适的锚栓，装好挂重试拉"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436025", "13700436026"), "轮椅过不去", "防滑地面整块铺平不翘边，门槛高差改坡或去掉"),
    ("elder-home-mod", "elder-home-mod-helper", ("13700436027", "13700436028"), "社区核查", "政府补贴按当地清单如实申报，不虚报项目"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436029", "13700436030"), "分反了", "按订单清单分拣，核对数量规格，按楼栋分好贴签"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436031", "13700436032"), "化了", "冷冻冷藏的到货先进冷柜，送达时间写清"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436033", "13700436034"), "说不清", "缺货坏果如实登记，按平台规则退，不私下扣钱"),
    ("group-buy-helper", "group-buy-helper-assistant", ("13700436035", "13700436036"), "吃坏", "只发平台上架的正规商品，不私卖自制、散装食品"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
