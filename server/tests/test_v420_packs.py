"""SCN-284 / SCN-285 第五十二轮场景发掘：纱窗更换、地暖清洗（393 号 spec，V420）。

两个新类目都不要资质：
- 「纱窗更换」：上门量尺寸、材质写清当面验、只在室内侧装不探身窗外（外侧作业属高处作业）、不承诺防坠防盗、旧纱窗带走；
- 「地暖清洗」：先问清系统、不用强酸、铺防水接污水、洗完补压试漏试运行、壁挂炉燃气部分不碰（那要燃气作业资质）。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_screen_pack_measures_on_site_and_keeps_installers_indoors():
    d, problems = schema.validate(_load("window-screen"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("报的尺寸" in f for f in a.forbidden) and any("冒充金刚网" in f for f in a.forbidden)
    assert any("探身窗外" in f for f in a.forbidden) and any("防坠落" in f for f in a.forbidden)
    assert any("旧纱窗" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["纱窗更换"]
    t = d.task_templates[0]
    assert "先上门量尺寸" in t.description and "只在室内侧装" in t.description and t.visits_planned == 2


def test_heating_pack_avoids_acid_and_never_touches_gas_parts():
    d, problems = schema.validate(_load("floor-heating-cleaning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("强酸" in f for f in a.forbidden) and any("燃气" in f for f in a.forbidden)
    assert any("不补压" in f for f in a.forbidden) and any("不铺防水" in f for f in a.forbidden)
    assert any("热多少度" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["地暖清洗"]
    t = d.task_templates[0].description
    assert "不用强酸" in t and "补压" in t and "燃气部分不碰" in t


@pytest.mark.parametrize("key", ["window-screen", "floor-heating-cleaning"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600042001")
    for title, cat in (("换三扇金刚网纱窗", "纱窗更换"), ("清洗六路地暖", "地暖清洗")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("window-screen", "window-screen-helper", ("13900005701", "13900005702"), "要上门量尺寸吗", "上门量尺寸再下单，不凭客户报的数"),
    ("window-screen", "window-screen-helper", ("13900005703", "13900005704"), "材质要写清吗", "网和框的材质写清楚，到货当面验"),
    ("window-screen", "window-screen-helper", ("13900005705", "13900005706"), "能探身窗外装吗", "只在室内侧装，不探身窗外"),
    ("window-screen", "window-screen-helper", ("13900005707", "13900005708"), "纱窗能防坠落吗", "纱窗只防蚊，不承诺防坠落防盗"),
    ("window-screen", "window-screen-helper", ("13900005709", "13900005710"), "旧纱窗怎么处理", "旧纱窗拆下带走，窗槽清干净，开关给客户看"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005711", "13900005712"), "电地暖要洗吗", "先问清水地暖还是电地暖、炉子和分水器"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005713", "13900005714"), "能用强酸清洗吗", "不用强酸，用中性清洗剂或脉冲物理清洗"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005715", "13900005716"), "污水怎么排", "地面铺防水，污水接到下水道，不漏到楼下"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005717", "13900005718"), "洗完要补压吗", "洗完补压试漏，开机试运行给客户看"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005719", "13900005720"), "壁挂炉燃气阀能修吗", "壁挂炉的燃气部分不拆不修；不承诺热多少度"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("window-screen", "window-screen-helper", ("13900005721", "13900005722"), "装不上", "上门量尺寸再下单，不凭客户报的数"),
    ("window-screen", "window-screen-helper", ("13900005723", "13900005724"), "货不对板", "网和框的材质写清楚，到货当面验"),
    ("window-screen", "window-screen-helper", ("13900005725", "13900005726"), "爬窗", "纱窗只防蚊，不承诺防坠落防盗"),
    ("window-screen", "window-screen-helper", ("13900005727", "13900005728"), "推不动", "旧纱窗拆下带走，窗槽清干净，开关给客户看"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005729", "13900005730"), "第一次洗", "先问清水地暖还是电地暖、炉子和分水器"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005731", "13900005732"), "伤管子", "不用强酸，用中性清洗剂或脉冲物理清洗"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005733", "13900005734"), "满地水", "地面铺防水，污水接到下水道，不漏到楼下"),
    ("floor-heating-cleaning", "floor-heating-cleaning-helper", ("13900005735", "13900005736"), "包热", "壁挂炉的燃气部分不拆不修；不承诺热多少度"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
