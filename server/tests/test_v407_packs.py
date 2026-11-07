"""SCN-272 / SCN-273 第四十六轮场景发掘：装修过程监理、宠物接送（380 号 spec，V407）。

两个新类目都不要资质：
- 「装修监理」：按节点巡检、隐蔽工程封板前验、闭水泡满、问题拍照写依据、只对业主负责不收施工方的钱不代签；
- 「宠物接送」：装箱系绳、不单独留车里、问清脾气身体带疫苗本、两头当面交接拍照、急病先送医不自己喂药。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_supervision_pack_inspects_before_concealing_and_stays_on_the_owners_side():
    d, problems = schema.validate(_load("renovation-supervision"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("封板后再补验" in f for f in a.forbidden) and any("回扣" in f for f in a.forbidden)
    assert any("替业主在验收单上签字" in f for f in a.forbidden) and any("闭水" in f for f in a.forbidden)
    assert {"money", "publish", "sign"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["装修监理"]
    t = d.task_templates[0]
    assert "封板前" in t.description and "不收施工方的钱" in t.description and t.visits_planned == 5


def test_transport_pack_crates_pets_and_never_doctors_them():
    d, problems = schema.validate(_load("pet-transport"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("航空箱" in f for f in a.forbidden) and any("单独留在车里" in f for f in a.forbidden)
    assert any("喂药" in f for f in a.forbidden) and any("当面清点" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["宠物接送"]
    t = d.task_templates[0].description
    assert "装箱或系绳" in t and "不单独留在车里" in t and "先送最近的宠物医院" in t


@pytest.mark.parametrize("key", ["renovation-supervision", "pet-transport"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600040701")
    for title, cat in (("新房装修全程监理", "装修监理"), ("送猫去宠物医院", "宠物接送")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("renovation-supervision", "renovation-supervision-helper", ("13900005101", "13900005102"), "开工前要看哪些合同图纸", "开工前拿到施工合同、图纸和报价单"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005103", "13900005104"), "水电管路什么时候验", "水电管路封板、贴砖之前一定要验"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005105", "13900005106"), "闭水试验做多久", "防水做完闭水试验，泡满 48 小时"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005107", "13900005108"), "问题怎么拍照记下来", "问题拍照、写清依据和建议"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005109", "13900005110"), "监理能收施工方的钱吗", "只对业主负责：不收施工方的钱，不替业主签字"),
    ("pet-transport", "pet-transport-helper", ("13900005111", "13900005112"), "猫要装航空箱吗", "猫和小狗进航空箱，大狗系牵引绳"),
    ("pet-transport", "pet-transport-helper", ("13900005113", "13900005114"), "能把宠物留在车里吗", "不把宠物单独留在车里，开空调带水"),
    ("pet-transport", "pet-transport-helper", ("13900005115", "13900005116"), "要带疫苗本吗", "接之前问清宠物的脾气和身体，带上疫苗本"),
    ("pet-transport", "pet-transport-helper", ("13900005117", "13900005118"), "交接要拍照吗", "交接两头当面清点，拍照回报"),
    ("pet-transport", "pet-transport-helper", ("13900005119", "13900005120"), "路上抽搐怎么办", "路上急病先送最近的宠物医院，马上告诉主人"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("renovation-supervision", "renovation-supervision-helper", ("13900005121", "13900005122"), "怕被增项", "开工前拿到施工合同、图纸和报价单"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005123", "13900005124"), "已经封墙了", "水电管路封板、贴砖之前一定要验"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005125", "13900005126"), "漏到楼下了", "防水做完闭水试验，泡满 48 小时"),
    ("renovation-supervision", "renovation-supervision-helper", ("13900005127", "13900005128"), "怕他们串通", "只对业主负责：不收施工方的钱，不替业主签字"),
    ("pet-transport", "pet-transport-helper", ("13900005129", "13900005130"), "跳车怎么办", "猫和小狗进航空箱，大狗系牵引绳"),
    ("pet-transport", "pet-transport-helper", ("13900005131", "13900005132"), "天太热", "不把宠物单独留在车里，开空调带水"),
    ("pet-transport", "pet-transport-helper", ("13900005133", "13900005134"), "怕接错", "交接两头当面清点，拍照回报"),
    ("pet-transport", "pet-transport-helper", ("13900005135", "13900005136"), "看着不对劲", "路上急病先送最近的宠物医院，马上告诉主人"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
