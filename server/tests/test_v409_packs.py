"""SCN-274 / SCN-275 第四十七轮场景发掘：鞋包清洗护理、表格整理（383 号 spec，V409）。

两个新类目都不要资质：
- 「鞋包清洗」：收件当面查验拍照、先认材质再定洗法、阴干不暴晒、名贵的不承诺洗得跟新的一样、洗出问题不掩盖；
- 「表格整理」：先备份原表、去重规则先确认、公式抽样核对、个人信息只按约定用、不编数据不改数字。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_shoe_pack_inspects_at_pickup_and_never_covers_up_damage():
    d, problems = schema.validate(_load("shoe-bag-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不检查拍照就收件" in f for f in a.forbidden) and any("漂白水" in f for f in a.forbidden)
    assert any("跟新的一样" in f for f in a.forbidden) and any("掩盖" in f for f in a.forbidden)
    assert any("暴晒" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["鞋包清洗"]
    t = d.task_templates[0]
    assert "当面检查并拍照" in t.description and "阴干不暴晒" in t.description and t.visits_planned == 2


def test_spreadsheet_pack_keeps_the_original_and_never_fakes_numbers():
    d, problems = schema.validate(_load("spreadsheet-cleanup"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("原表上改" in f for f in a.forbidden) and any("不经确认就删除" in f for f in a.forbidden)
    assert any("个人信息" in f for f in a.forbidden) and any("编造或篡改" in f for f in a.forbidden)
    assert any("不核对" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["表格整理"]
    t = d.task_templates[0].description
    assert "规则先写给我确认" in t and "合计和原表对得上" in t and "交付后删除" in t


@pytest.mark.parametrize("key", ["shoe-bag-care", "spreadsheet-cleanup"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600040901")
    for title, cat in (("洗三双球鞋", "鞋包清洗"), ("整理客户名单去重", "表格整理")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005201", "13900005202"), "收件时要拍照吗", "收件时当面查验拍照，写进收件单"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005203", "13900005204"), "麂皮能泡水吗", "先认材质再定洗法，真皮麂皮不泡水"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005205", "13900005206"), "洗完怎么晾干", "洗完阴干定型，不暴晒、不高温烘"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005207", "13900005208"), "限量鞋要讲风险吗", "名贵包和限量鞋先讲清风险，不承诺洗得跟新的一样"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005209", "13900005210"), "洗出问题怎么协商", "洗出问题先停手告诉客户，按约定或实际损失协商"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005211", "13900005212"), "要先备份原表吗", "先备份原表，只在副本上改"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005213", "13900005214"), "去重的规则要先确认吗", "去重、补空、统一格式的规则先请对方确认"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005215", "13900005216"), "公式怎么核对", "公式写完抽样手算，合计和原表对一遍"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005217", "13900005218"), "表里有个人信息怎么办", "表里的个人信息只按约定用，交付后删除"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005219", "13900005220"), "缺的数据能自己编吗", "缺的数据标出来请对方补，不编、不改数字凑结果"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005221", "13900005222"), "客户赖我", "收件时当面查验拍照，写进收件单"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005223", "13900005224"), "会褪色吗", "先认材质再定洗法，真皮麂皮不泡水"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005225", "13900005226"), "多久能干", "洗完阴干定型，不暴晒、不高温烘"),
    ("shoe-bag-care", "shoe-bag-care-helper", ("13900005227", "13900005228"), "被投诉了", "洗出问题先停手告诉客户，按约定或实际损失协商"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005229", "13900005230"), "找不回了", "先备份原表，只在副本上改"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005231", "13900005232"), "有重名的", "去重、补空、统一格式的规则先请对方确认"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005233", "13900005234"), "差了一截", "公式写完抽样手算，合计和原表对一遍"),
    ("spreadsheet-cleanup", "spreadsheet-cleanup-helper", ("13900005235", "13900005236"), "怕泄露", "表里的个人信息只按约定用，交付后删除"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
