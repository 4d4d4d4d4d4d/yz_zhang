"""SCN-259 / SCN-260 第四十轮场景发掘：钢琴调律、闲置代卖（367 号 spec，V393）。

两个新类目都不要资质：
- 「钢琴调律」：调前调后当面弹、换件先说清、多年没调的分两次拉、调完讲清保养；
- 「闲置代卖」：交接清点拍照、照片不露隐私、价格由主人定、货款走平台、不代卖违禁品；分享个人信息是人工关口。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_piano_pack_plays_before_and_after_and_quotes_parts_first():
    d, problems = schema.validate(_load("piano-tuning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("换件或大修" in f for f in a.forbidden) and any("推销" in f for f in a.forbidden)
    assert any("一次拉回标准音" in f for f in a.forbidden) and any("当面弹" in f for f in a.forbidden)
    assert {"money", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["钢琴调律"]
    t = d.task_templates[0].description
    assert "当面弹" in t and "我同意再动手" in t


def test_resale_pack_keeps_goods_money_and_privacy_with_the_owner():
    d, problems = schema.validate(_load("secondhand-resale"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("个人账户" in f for f in a.forbidden) and any("快递单" in f for f in a.forbidden)
    assert any("不问主人就降价" in f for f in a.forbidden) and any("管制刀具" in f for f in a.forbidden)
    assert any("不清点" in f for f in a.forbidden) and any("隐瞒瑕疵" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["闲置代卖"]
    t = d.task_templates[0].description
    assert "最低价我来定" in t and "货款走平台" in t and "原样退回" in t


@pytest.mark.parametrize("key", ["piano-tuning", "secondhand-resale"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600039301")
    for title, cat in (("立式钢琴三年没调了", "钢琴调律"), ("搬家前把闲置家电卖掉", "闲置代卖")):
        t = _post(client, requester, title=title, description="周末上门", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("piano-tuning", "piano-tuning-helper", ("13900004501", "13900004502"), "要不要问上次调律是什么时候", "上门前问清琴况与上次调律"),
    ("piano-tuning", "piano-tuning-helper", ("13900004503", "13900004504"), "调完怎么让客户验收", "调前调后各当面弹一遍"),
    ("piano-tuning", "piano-tuning-helper", ("13900004505", "13900004506"), "琴槌要不要换", "要换件、要大修的先说清楚，同意再动手"),
    ("piano-tuning", "piano-tuning-helper", ("13900004507", "13900004508"), "多年没调能一次拉到标准音吗", "多年没调的琴分两次拉回标准音"),
    ("piano-tuning", "piano-tuning-helper", ("13900004509", "13900004510"), "钢琴放哪里不容易走音", "调完讲清湿度、摆放和多久调一次"),
    ("secondhand-resale", "resale-helper", ("13900004511", "13900004512"), "接手时怎么交接", "接手时当面清点、拍照、写交接单"),
    ("secondhand-resale", "resale-helper", ("13900004513", "13900004514"), "在客户家拍照要注意什么", "上架照片不露门牌、快递单、证件和人脸"),
    ("secondhand-resale", "resale-helper", ("13900004515", "13900004516"), "买家砍价低于最低价", "标价与最低价由主人定，改价先问"),
    ("secondhand-resale", "resale-helper", ("13900004517", "13900004518"), "买家要直接转账给我", "货款走平台，按约定转给主人"),
    ("secondhand-resale", "resale-helper", ("13900004519", "13900004520"), "手机卖前要做什么", "手机电脑卖前清数据；不能卖的东西不接"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("piano-tuning", "piano-tuning-helper", ("13900004521", "13900004522"), "弦断了怎么办", "多年没调的琴分两次拉回标准音"),
    ("piano-tuning", "piano-tuning-helper", ("13900004523", "13900004524"), "我听不出好坏", "调前调后各当面弹一遍"),
    ("piano-tuning", "piano-tuning-helper", ("13900004525", "13900004526"), "是不是想让我加钱", "要换件、要大修的先说清楚，同意再动手"),
    ("secondhand-resale", "resale-helper", ("13900004527", "13900004528"), "东西说不清楚了", "接手时当面清点、拍照、写交接单"),
    ("secondhand-resale", "resale-helper", ("13900004529", "13900004530"), "能便宜卖给我朋友吗", "标价与最低价由主人定，改价先问"),
    ("secondhand-resale", "resale-helper", ("13900004531", "13900004532"), "香烟能代卖吗", "手机电脑卖前清数据；不能卖的东西不接"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
