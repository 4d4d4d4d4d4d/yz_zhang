"""SCN-244 / SCN-245 第三十三轮场景发掘：宠物训犬、地陪导游（352 号 spec，V379）。

两个数据文件、两个新类目：「宠物训犬」不要资质；「地陪导游」要审核通过的导游证。
训犬：正向训练不打不电、目标写清不包会、寄训每天回报、咬人史说清；导游：持证、不带购物不收回扣、
不开私家车载客收费、费用透明、户外先讲安全。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import GUIDE_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_dog_training_pack_is_positive_and_never_guarantees():
    d, problems = schema.validate(_load("dog-training"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("电击" in f for f in a.forbidden) and any("包会" in f for f in a.forbidden)
    assert any("咬人史" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["宠物训犬"]
    t = d.task_templates[0].description
    assert "不打不电" in t and "不承诺包会" in t


def test_tour_guide_pack_needs_a_licence_and_never_does_shopping_or_private_car_fares():
    d, problems = schema.validate(_load("local-tour-guide"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("回扣" in f for f in a.forbidden) and any("私家车" in f for f in a.forbidden)
    assert any("没有导游证" in f for f in a.forbidden)
    assert _categories()["地陪导游"]["required_cert"] == GUIDE_CERT
    assert "不安排购物" in d.task_templates[0].description


@pytest.mark.parametrize("key", ["dog-training", "local-tour-guide"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_guide_licence_can_take_a_tour(client, requester):
    ops = make_admin(client, "13600003791", "运营")
    t = _post(client, requester, title="城墙一日讲解", description="一家四口，有老人", category="地陪导游").json()
    w = make_verified(client, "13600003792")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and GUIDE_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=GUIDE_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "导游证可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    dog = _post(client, requester, title="柯基随行训练", description="一岁，爱拉扯", category="宠物训犬")
    assert dog.status_code in (200, 201), dog.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("dog-training", "dog-training-helper", ("13900003901", "13900003902"), "能不能用电击项圈", "用正向奖励，不打不电不勒"),
    ("dog-training", "dog-training-helper", ("13900003903", "13900003904"), "主人要我保证十天包会", "目标写清到动作，不承诺包会"),
    ("dog-training", "dog-training-helper", ("13900003905", "13900003906"), "寄训的狗今天不吃东西", "寄训每天发视频和喂食记录"),
    ("dog-training", "dog-training-helper", ("13900003907", "13900003908"), "这只狗咬过人", "有咬人史的狗先说清风险"),
    ("local-tour-guide", "tour-guide-helper", ("13900003909", "13900003910"), "购物店给人头费能拿吗", "不安排购物，不收商店和景区的回扣"),
    ("local-tour-guide", "tour-guide-helper", ("13900003911", "13900003912"), "能开我自己的车接送收钱吗", "不用私家车载客收费"),
    ("local-tour-guide", "tour-guide-helper", ("13900003913", "13900003914"), "门票我先垫上再加点钱行吗", "门票餐费游客自己付，导游费写清"),
    ("local-tour-guide", "tour-guide-helper", ("13900003915", "13900003916"), "带老人爬山要注意什么", "户外线路先讲安全，老人小孩多照看"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("dog-training", "dog-training-helper", ("13900003917", "13900003918"), "狗回来变得怕人了", "用正向奖励，不打不电不勒"),
    ("dog-training", "dog-training-helper", ("13900003919", "13900003920"), "主人说回家就不听", "目标写清到动作，不承诺包会"),
    ("dog-training", "dog-training-helper", ("13900003921", "13900003922"), "狗生病了", "寄训每天发视频和喂食记录"),
    ("local-tour-guide", "tour-guide-helper", ("13900003923", "13900003924"), "游客怕被带进店", "不安排购物，不收商店和景区的回扣"),
    ("local-tour-guide", "tour-guide-helper", ("13900003925", "13900003926"), "游客想包车", "不用私家车载客收费"),
    ("local-tour-guide", "tour-guide-helper", ("13900003927", "13900003928"), "能先帮游客垫付吗", "门票餐费游客自己付，导游费写清"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
