"""SCN-282 / SCN-283 第五十一轮场景发掘：老人回忆录整理、陪同口译（391 号 spec，V418）。

两个新类目都不要资质：
- 「回忆录整理」：用老人自己的话不编情节、录音先得本人同意、写到别人的私事要谨慎、老照片原件当面交接归还、著作权和印制写清；
- 「陪同口译」：提前要资料和术语、忠实传达不替一方说话、内容保密、法庭公证医疗诊断找有资质的不替人签字、时长加班写清。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_memoir_pack_keeps_the_elders_own_words_and_others_privacy():
    d, problems = schema.validate(_load("memoir-writing"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("编造" in f for f in a.forbidden) and any("不告诉老人就录音" in f for f in a.forbidden)
    assert any("别人的私事" in f for f in a.forbidden) and any("原件" in f for f in a.forbidden)
    assert any("著作权" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["回忆录整理"]
    t = d.task_templates[0]
    assert "本人已同意" in t.description and "不编情节" in t.description and "扫描后归还" in t.description
    assert t.visits_planned == 3


def test_interpreting_pack_stays_neutral_and_never_signs_for_anyone():
    d, problems = schema.validate(_load("escort-interpreting"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("替一方说话" in f for f in a.forbidden) and any("外传" in f for f in a.forbidden)
    assert any("替当事人签字" in f for f in a.forbidden) and any("加班费" in f for f in a.forbidden)
    assert any("不做准备" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["陪同口译"]
    t = d.task_templates[0].description
    assert "忠实传达" in t and "不替我签字" in t and "内容保密" in t


@pytest.mark.parametrize("key", ["memoir-writing", "escort-interpreting"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600041801")
    for title, cat in (("给爷爷整理回忆录", "回忆录整理"), ("广交会英语陪同", "陪同口译")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("memoir-writing", "memoir-writing-helper", ("13900005601", "13900005602"), "能编情节吗", "用老人自己的话，不编情节，记不清的标出来"),
    ("memoir-writing", "memoir-writing-helper", ("13900005603", "13900005604"), "录音要老人同意吗", "访谈录音先得老人本人同意"),
    ("memoir-writing", "memoir-writing-helper", ("13900005605", "13900005606"), "写到别人的私事怎么办", "写到别人的私事要谨慎，公开前请家人看"),
    ("memoir-writing", "memoir-writing-helper", ("13900005607", "13900005608"), "老照片原件怎么办", "老照片老信件原件当面交接，扫描后归还"),
    ("memoir-writing", "memoir-writing-helper", ("13900005609", "13900005610"), "著作权归谁", "著作权归谁、怎么印，写进约定"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005611", "13900005612"), "要提前准备术语吗", "提前要资料和术语表，行业词先问清"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005613", "13900005614"), "能替一方说话吗", "忠实传达，不替一方说话，不加自己的意见"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005615", "13900005616"), "参观内容要保密吗", "谈判和参观看到的内容保密，不拍照外传"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005617", "13900005618"), "法庭公证要找有资质的吗", "法庭、公证、医疗诊断找有资质的口译；不替人签字"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005619", "13900005620"), "加班费怎么算", "时长、超时加班、交通餐费和取消写清"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("memoir-writing", "memoir-writing-helper", ("13900005621", "13900005622"), "添油加醋", "用老人自己的话，不编情节，记不清的标出来"),
    ("memoir-writing", "memoir-writing-helper", ("13900005623", "13900005624"), "伤心事", "访谈录音先得老人本人同意"),
    ("memoir-writing", "memoir-writing-helper", ("13900005625", "13900005626"), "得罪人", "写到别人的私事要谨慎，公开前请家人看"),
    ("memoir-writing", "memoir-writing-helper", ("13900005627", "13900005628"), "丢了怎么办", "老照片老信件原件当面交接，扫描后归还"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005629", "13900005630"), "卡壳", "提前要资料和术语表，行业词先问清"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005631", "13900005632"), "自作主张", "忠实传达，不替一方说话，不加自己的意见"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005633", "13900005634"), "说漏嘴了", "谈判和参观看到的内容保密，不拍照外传"),
    ("escort-interpreting", "escort-interpreting-helper", ("13900005635", "13900005636"), "拖到晚上", "时长、超时加班、交通餐费和取消写清"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
