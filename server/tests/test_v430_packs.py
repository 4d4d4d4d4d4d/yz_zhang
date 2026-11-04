"""SCN-294 / SCN-295 第五十七轮场景发掘：无人机航拍、电脑组装与重装（403 号 spec，V430）。

两个新类目都不要资质（无人机按机型需要操控员执照的，知识里提醒持证再飞）：
- 「无人机航拍」：先实名登记并买第三者责任险、起飞前查空域该申请的先申请（无人驾驶航空器飞行管理暂行条例）、
  人群上方不飞不拍私密空间（民法典第一千零三十三条）、看风力电量留足返航、成片规格与素材用途写清；
- 「电脑组装与重装」：配置单写清型号装前核对（消保法第二十条）、二手翻新件说明白（第五十五条）、
  正版系统不捆绑、重装前先备份、压力测试后交付。
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


def test_drone_pack_registers_checks_airspace_and_avoids_crowds():
    d, problems = schema.validate(_load("drone-aerial"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("黑飞" in f for f in a.forbidden) and any("管制空域" in f for f in a.forbidden)
    assert any("人群上方" in f for f in a.forbidden) and any("私密空间" in f for f in a.forbidden)
    assert any("大风低电量" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["无人机航拍"]
    t = d.task_templates[0].description
    assert "实名登记" in t and "查空域" in t and "不在人群上方飞" in t


def test_pc_build_pack_is_honest_about_parts_and_backs_up_first():
    d, problems = schema.validate(_load("pc-build"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("配置单" in f for f in a.forbidden) and any("二手翻新件当新件" in f for f in a.forbidden)
    assert any("盗版系统" in f for f in a.forbidden) and any("不备份就格式化" in f for f in a.forbidden)
    assert any("不测试就交付" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["电脑组装与重装"]
    t = d.task_templates[0].description
    assert "核对" in t and "正版系统" in t and "先备份" in t


@pytest.mark.parametrize("key", ["drone-aerial", "pc-build"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600043001")
    for title, cat in (("小区全景航拍", "无人机航拍"), ("装一台剪辑用的电脑", "电脑组装与重装")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("drone-aerial", "drone-aerial-helper", ("13900008001", "13900008002"), "无人机要实名登记吗", "无人机先实名登记，商用拍摄买好第三者责任险"),
    ("drone-aerial", "drone-aerial-helper", ("13900008003", "13900008004"), "起飞前要查什么空域", "起飞前查空域，机场附近和管制空域不飞，该申请的先申请"),
    ("drone-aerial", "drone-aerial-helper", ("13900008005", "13900008006"), "能在人群上方飞吗", "人群上方不飞，不拍军事设施和别人家的私密空间"),
    ("drone-aerial", "drone-aerial-helper", ("13900008007", "13900008008"), "起飞前要看风力和电量吗", "看风力、电量和信号，留足返航余量，现场先试飞"),
    ("drone-aerial", "drone-aerial-helper", ("13900008009", "13900008010"), "成片要写清什么", "成片规格、交付时间、改几次和素材用途写清"),
    ("pc-build", "pc-build-helper", ("13900008011", "13900008012"), "配置单要给客户核对吗", "配置单写清每个配件的型号，装之前给客户核对"),
    ("pc-build", "pc-build-helper", ("13900008013", "13900008014"), "二手配件能当新的卖吗", "二手、翻新、拆机件说明白，不当新件卖"),
    ("pc-build", "pc-build-helper", ("13900008015", "13900008016"), "能装破解版系统吗", "装正版系统，不装破解版，不捆绑客户没要的软件"),
    ("pc-build", "pc-build-helper", ("13900008017", "13900008018"), "重装系统前要备份吗", "重装或换硬盘前先备份，客户确认后再格式化"),
    ("pc-build", "pc-build-helper", ("13900008019", "13900008020"), "装好要测试吗", "装好压力测试，温度跑分正常再交付"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("drone-aerial", "drone-aerial-helper", ("13900008021", "13900008022"), "黑飞", "无人机先实名登记，商用拍摄买好第三者责任险"),
    ("drone-aerial", "drone-aerial-helper", ("13900008023", "13900008024"), "禁飞区", "起飞前查空域，机场附近和管制空域不飞，该申请的先申请"),
    ("drone-aerial", "drone-aerial-helper", ("13900008025", "13900008026"), "偷拍", "人群上方不飞，不拍军事设施和别人家的私密空间"),
    ("drone-aerial", "drone-aerial-helper", ("13900008027", "13900008028"), "炸机", "看风力、电量和信号，留足返航余量，现场先试飞"),
    ("pc-build", "pc-build-helper", ("13900008029", "13900008030"), "杂牌", "配置单写清每个配件的型号，装之前给客户核对"),
    ("pc-build", "pc-build-helper", ("13900008031", "13900008032"), "矿卡", "二手、翻新、拆机件说明白，不当新件卖"),
    ("pc-build", "pc-build-helper", ("13900008033", "13900008034"), "全家桶", "装正版系统，不装破解版，不捆绑客户没要的软件"),
    ("pc-build", "pc-build-helper", ("13900008035", "13900008036"), "照片全没了", "重装或换硬盘前先备份，客户确认后再格式化"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
