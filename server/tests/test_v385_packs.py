"""SCN-251 / SCN-252 第三十六轮场景发掘：改衣裁缝、身后事办理协助（358 号 spec，V385）。

两个数据文件、两个新类目，都不要资质。
改衣：当面量尺寸、改前拍照、贵重面料先说风险、工期写清、改坏按说好的赔；
身后事：先开死亡证明、遗体只交殡仪馆运送、价格看公示不推销、待遇与销户清单、不经手钱不代签。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_tailor_pack_measures_photographs_and_never_promises_like_new():
    d, problems = schema.validate(_load("tailor-alterations"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("跟新的一样" in f for f in a.forbidden) and any("拍照" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["改衣裁缝"]
    t = d.task_templates[0].description
    assert "改前拍照" in t and "改坏了" in t


def test_bereavement_pack_keeps_money_and_signatures_with_the_family():
    d, problems = schema.validate(_load("bereavement-affairs"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("私人车辆" in f for f in a.forbidden) and any("推销" in f for f in a.forbidden)
    assert any("代家属收付" in f for f in a.forbidden) and any("代家属签字" in f for f in a.forbidden)
    assert any("法律意见" in f for f in a.forbidden)
    assert {"money", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["身后事协助"]
    t = d.task_templates[0].description
    assert "家属自己付" in t and "本人签" in t and "殡仪馆" in t


@pytest.mark.parametrize("key", ["tailor-alterations", "bereavement-affairs"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_orders_without_a_certificate(client, requester):
    for title, cat in (("改两条裤长", "改衣裁缝"), ("帮忙跑销户流程", "身后事协助")):
        r = _post(client, requester, title=title, description="周末", category=cat)
        assert r.status_code in (200, 201), r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("tailor-alterations", "tailor-helper", ("13900004101", "13900004102"), "客户说我把裤子改短了", "当面量尺寸，改多少写在单子上"),
    ("tailor-alterations", "tailor-helper", ("13900004103", "13900004104"), "真丝裙子能不能收腰", "贵重面料先说风险，不承诺改得跟新的一样"),
    ("tailor-alterations", "tailor-helper", ("13900004105", "13900004106"), "客户婚礼前要改好", "工期写清，赶日子的先问"),
    ("tailor-alterations", "tailor-helper", ("13900004107", "13900004108"), "改坏了怎么赔", "改坏了按说好的办法赔"),
    ("tailor-alterations", "tailor-helper", ("13900004109", "13900004110"), "改之前要不要拍照", "改前拍照留底"),
    ("bereavement-affairs", "bereavement-helper", ("13900004111", "13900004112"), "老人在家走了先办什么", "第一件事是开死亡证明"),
    ("bereavement-affairs", "bereavement-helper", ("13900004113", "13900004114"), "医院门口有人要拉遗体", "遗体只交殡仪馆运送，不找私人车辆"),
    ("bereavement-affairs", "bereavement-helper", ("13900004115", "13900004116"), "骨灰盒要买多贵的", "价格看公示，按需选择不攀比"),
    ("bereavement-affairs", "bereavement-helper", ("13900004117", "13900004118"), "丧葬费去哪里领", "待遇与销户：一张清单一件件办"),
    ("bereavement-affairs", "bereavement-helper", ("13900004119", "13900004120"), "家属让我先垫钱", "协助人不经手钱，不替家属签字"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("tailor-alterations", "tailor-helper", ("13900004121", "13900004122"), "客户嫌长了", "当面量尺寸，改多少写在单子上"),
    ("tailor-alterations", "tailor-helper", ("13900004123", "13900004124"), "原来有污渍", "改前拍照留底"),
    ("tailor-alterations", "tailor-helper", ("13900004125", "13900004126"), "客户问能不能退钱", "改坏了按说好的办法赔"),
    ("bereavement-affairs", "bereavement-helper", ("13900004127", "13900004128"), "该先打给谁", "第一件事是开死亡证明"),
    ("bereavement-affairs", "bereavement-helper", ("13900004129", "13900004130"), "碰到黑车", "遗体只交殡仪馆运送，不找私人车辆"),
    ("bereavement-affairs", "bereavement-helper", ("13900004131", "13900004132"), "套餐太贵", "价格看公示，按需选择不攀比"),
    ("bereavement-affairs", "bereavement-helper", ("13900004133", "13900004134"), "丧葬费", "待遇与销户：一张清单一件件办"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
