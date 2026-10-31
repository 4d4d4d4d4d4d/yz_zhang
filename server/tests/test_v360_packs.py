"""SCN-214 / SCN-215 第二十二轮场景发掘：证件照拍摄与修图、上门洗车（333 号 spec，V360）。

两个数据文件、两个新类目（都不要资质）。证件照的关口是办证与报名的照片只去瑕疵、不改五官、给原生版、不用旧照；
上门洗车的关口是先问物业、洗前拍车况、污水收走、车里的东西不动。
"""
import pytest

from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_id_photo_pack_only_removes_blemishes_for_official_use():
    d, problems = schema.validate(_load("id-photo"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("改五官" in f for f in a.forbidden) and any("旧照" in f for f in a.forbidden)
    assert any("伪造证件照" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["证件照拍摄"]
    t = d.task_templates[0]
    assert "原生版" in t.description and "不用旧照" in t.description


def test_car_wash_pack_asks_the_property_photographs_first_and_takes_the_water_away():
    d, problems = schema.validate(_load("mobile-car-wash"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不拍车况" in f for f in a.forbidden) and any("雨水口" in f for f in a.forbidden)
    assert any("消防通道" in f for f in a.forbidden) and any("车内物品" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["上门洗车"]
    assert "洗前拍车况" in d.task_templates[0].visit_checklist


def test_both_categories_take_orders(client, requester):
    w = make_verified(client, "13600003601")
    for title, cat, remote in (("拍一张护照照片", "证件照拍摄", False), ("地库洗车", "上门洗车", False)):
        t = _post(client, requester, title=title, description="x", category=cat, is_remote=remote)
        assert t.status_code in (200, 201), t.text
        assert client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("id-photo", "id-photo-helper", ("13900003601", "13900003602"), "客户要求瘦脸大眼", "办证、报名的照片：只去瑕疵，不改五官"),
    ("id-photo", "id-photo-helper", ("13900003603", "13900003604"), "考研报名照被退回了", "办证、考试报名给「原生版」"),
    ("id-photo", "id-photo-helper", ("13900003605", "13900003606"), "能用以前的照片换身份证吗", "不用旧照、不翻拍：制证要近期照片"),
    ("mobile-car-wash", "car-wash-helper", ("13900003607", "13900003608"), "车主说我刮花了车", "洗之前绕车拍一圈车况"),
    ("mobile-car-wash", "car-wash-helper", ("13900003609", "13900003610"), "保安不让在地库洗", "先问物业让不让洗"),
    # 人们真正会说的话：正文与标题里没有这些词，靠标签接住
    ("id-photo", "id-photo-helper", ("13900003611", "13900003612"), "能不能美颜一下", "办证、报名的照片：只去瑕疵，不改五官"),
    ("mobile-car-wash", "car-wash-helper", ("13900003613", "13900003614"), "邻居投诉地上全是积水", "污水收走，不往雨水口、绿地里倒"),
    ("mobile-car-wash", "car-wash-helper", ("13900003615", "13900003616"), "说我刮花了", "洗之前绕车拍一圈车况"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
