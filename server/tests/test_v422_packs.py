"""SCN-286 / SCN-287 第五十三轮场景发掘：宠物家庭寄养、汽车搭电换胎（395 号 spec，V422）。

两个新类目都不要资质：
- 「宠物寄养」：接收前看疫苗本、和自家宠物分开防走失、每天拍照回报、急病先送医不自己用药、按主人的喂法不换粮；
- 「搭电换胎」：先停到安全处打双闪放三角牌、高速快速路上的不接请车主报警、搭电按顺序接线、备胎限速说清、费用事先写清。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_boarding_pack_checks_vaccines_and_keeps_pets_apart():
    d, problems = schema.validate(_load("pet-boarding"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("疫苗本" in f for f in a.forbidden) and any("关在一起" in f for f in a.forbidden)
    assert any("自己给宠物用药" in f for f in a.forbidden) and any("换粮" in f for f in a.forbidden)
    assert any("不回报" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["宠物寄养"]
    t = d.task_templates[0].description
    assert "疫苗本" in t and "每天拍照或视频回报" in t and "不自己用药" in t


def test_roadside_pack_puts_safety_first_and_stays_off_highways():
    d, problems = schema.validate(_load("roadside-jumpstart"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("高速" in f for f in a.forbidden) and any("警告牌" in f for f in a.forbidden)
    assert any("接线" in f for f in a.forbidden) and any("限速" in f for f in a.forbidden)
    assert any("临时加价" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["搭电换胎"]
    t = d.task_templates[0].description
    assert "不在高速快速路上" in t and "放三角牌" in t and "到场不另加价" in t


@pytest.mark.parametrize("key", ["pet-boarding", "roadside-jumpstart"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600042201")
    for title, cat in (("国庆寄养一只柯基", "宠物寄养"), ("小区里车打不着火", "搭电换胎")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("pet-boarding", "pet-boarding-helper", ("13900005801", "13900005802"), "要看疫苗本吗", "接收前看疫苗本和驱虫记录，正在生病的不收"),
    ("pet-boarding", "pet-boarding-helper", ("13900005803", "13900005804"), "能和自家的狗关一起吗", "和自家宠物分开，门窗纱窗关好，出门系绳"),
    ("pet-boarding", "pet-boarding-helper", ("13900005805", "13900005806"), "每天要拍照回报吗", "每天拍照或视频回报吃喝拉撒"),
    ("pet-boarding", "pet-boarding-helper", ("13900005807", "13900005808"), "生病能自己喂药吗", "急病先送最近的宠物医院，马上告诉主人，不自己用药"),
    ("pet-boarding", "pet-boarding-helper", ("13900005809", "13900005810"), "主人的粮吃完了怎么办", "交接当面清点，按主人的喂法喂，不乱换粮"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005811", "13900005812"), "到场先放三角牌吗", "先停到安全的地方，开双闪放三角牌，人站到安全区域"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005813", "13900005814"), "高速公路趴窝能接吗", "高速和快速路上的不接，请车主报警等专业救援"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005815", "13900005816"), "搭电怎么接线", "搭电按顺序接线，不接反；混动纯电不搭"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005817", "13900005818"), "备胎要限速吗", "换完备胎告诉车主限速，螺丝按对角拧紧"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005819", "13900005820"), "夜间加价要写清吗", "上门费、夜间加价事先写清；不到场加价、不推销来路不明的配件"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("pet-boarding", "pet-boarding-helper", ("13900005821", "13900005822"), "猫瘟", "接收前看疫苗本和驱虫记录，正在生病的不收"),
    ("pet-boarding", "pet-boarding-helper", ("13900005823", "13900005824"), "跑丢了", "和自家宠物分开，门窗纱窗关好，出门系绳"),
    ("pet-boarding", "pet-boarding-helper", ("13900005825", "13900005826"), "报平安", "每天拍照或视频回报吃喝拉撒"),
    ("pet-boarding", "pet-boarding-helper", ("13900005827", "13900005828"), "医药费", "急病先送最近的宠物医院，马上告诉主人，不自己用药"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005829", "13900005830"), "差点被撞", "先停到安全的地方，开双闪放三角牌，人站到安全区域"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005831", "13900005832"), "高速上能接吗", "高速和快速路上的不接，请车主报警等专业救援"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005833", "13900005834"), "冒烟", "搭电按顺序接线，不接反；混动纯电不搭"),
    ("roadside-jumpstart", "roadside-jumpstart-helper", ("13900005835", "13900005836"), "小备胎", "换完备胎告诉车主限速，螺丝按对角拧紧"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
