"""SCN-324 / SCN-325 第七十二轮场景发掘：墙纸墙布铺贴、石材地面翻新养护（433 号 spec，V460）。

- 「墙纸墙布铺贴」不要资质：先测墙面干透再刷基膜；按卷算料同一批号对花；用环保胶贴完通风（消保法第十八条）；
  开关插座先断电拆面板、不剪电线；接缝压实、交代养护、留余料（消保法第五十二条）；
- 「石材地面翻新养护」不要资质：先认石材角落试做；水磨护墙边挡水不渗楼下（民法典第二百九十六条）；
  药剂通风防护、老人孩子先离开；做完提醒防滑；报价前说清能修到什么程度。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091，含 PACK-093 逐个标签检查）离线试过；
写完用 scripts/pack_mutate.py（PACK-094）做变异红验。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_wallpaper_pack_waits_for_a_dry_wall_and_never_cuts_wires():
    d, problems = schema.validate(_load("wallpaper-install"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("没干透" in f for f in a.forbidden) and any("批号" in f for f in a.forbidden)
    assert any("劣质胶" in f for f in a.forbidden) and any("剪断电线" in f for f in a.forbidden)
    assert any("不压实接缝" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["墙纸墙布铺贴"]
    t = d.task_templates[0].description
    assert "刷基膜" in t and "同一批号" in t and "不剪电线" in t


def test_stone_pack_tests_a_corner_first_and_keeps_water_off_the_neighbours():
    d, problems = schema.validate(_load("stone-floor-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不认石材" in f for f in a.forbidden) and any("不挡水" in f for f in a.forbidden)
    assert any("不通风不防护" in f for f in a.forbidden) and any("不提醒防滑" in f for f in a.forbidden)
    assert any("跟新的一样" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["石材地面翻新养护"]
    t = d.task_templates[0].description
    assert "角落试做" in t and "挡水" in t and "提醒防滑" in t


@pytest.mark.parametrize("key", ["wallpaper-install", "stone-floor-care"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications(client, requester):
    w = make_verified(client, "13600046001")
    for title, cat in (("卧室贴墙布", "墙纸墙布铺贴"), ("客厅大理石地面结晶", "石材地面翻新养护")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("wallpaper-install", "wallpaper-helper", ("13700460001", "13700460002"), "墙面要干透吗", "先测墙面是否干透，再刷基膜，干了再贴"),
    ("wallpaper-install", "wallpaper-helper", ("13700460003", "13700460004"), "批号要一样吗", "按卷算料，同一批号，对花对缝"),
    ("wallpaper-install", "wallpaper-helper", ("13700460005", "13700460006"), "用什么胶", "用环保胶，贴完开窗通风再住人"),
    ("wallpaper-install", "wallpaper-helper", ("13700460007", "13700460008"), "插座那里怎么贴", "开关插座先断电，拆下面板再贴，不剪电线"),
    ("wallpaper-install", "wallpaper-helper", ("13700460009", "13700460010"), "接缝怎么处理", "接缝压实，交代头几天的养护，留下余料"),
    ("stone-floor-care", "stone-care-helper", ("13700460011", "13700460012"), "是什么石材", "先认清石材，药剂在角落试一块再大面积做"),
    ("stone-floor-care", "stone-care-helper", ("13700460013", "13700460014"), "磨地的水怎么办", "水磨时护住墙边和木地板，挡好门口，不让水渗到楼下"),
    ("stone-floor-care", "stone-care-helper", ("13700460015", "13700460016"), "药剂要通风吗", "结晶药剂开窗通风，师傅戴手套口罩，老人孩子宠物先离开"),
    ("stone-floor-care", "stone-care-helper", ("13700460017", "13700460018"), "做完会滑吗", "做完地面更滑，卫生间门口、入户处提醒防滑"),
    ("stone-floor-care", "stone-care-helper", ("13700460019", "13700460020"), "划痕能修好吗", "报价前说清能修到什么程度，按平方报价"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("wallpaper-install", "wallpaper-helper", ("13700460021", "13700460022"), "大包", "先测墙面是否干透，再刷基膜，干了再贴"),
    ("wallpaper-install", "wallpaper-helper", ("13700460023", "13700460024"), "色差", "按卷算料，同一批号，对花对缝"),
    ("wallpaper-install", "wallpaper-helper", ("13700460025", "13700460026"), "麻了一下", "开关插座先断电，拆下面板再贴，不剪电线"),
    ("wallpaper-install", "wallpaper-helper", ("13700460027", "13700460028"), "翘边", "接缝压实，交代头几天的养护，留下余料"),
    ("stone-floor-care", "stone-care-helper", ("13700460029", "13700460030"), "烧得发白", "先认清石材，药剂在角落试一块再大面积做"),
    ("stone-floor-care", "stone-care-helper", ("13700460031", "13700460032"), "天花板", "水磨时护住墙边和木地板，挡好门口，不让水渗到楼下"),
    ("stone-floor-care", "stone-care-helper", ("13700460033", "13700460034"), "头晕", "结晶药剂开窗通风，师傅戴手套口罩，老人孩子宠物先离开"),
    ("stone-floor-care", "stone-care-helper", ("13700460035", "13700460036"), "滑倒", "做完地面更滑，卫生间门口、入户处提醒防滑"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
