"""SCN-269 / SCN-270 第四十五轮场景发掘：数据恢复、上门美甲（378 号 spec，V404）。

两个新类目都不要资质：
- 「数据恢复」：只给机主本人或有授权的人做、先检测后报价不打包票、只找点名的不翻看、交付后删镜像副本；
- 「上门美甲」：工具一客一消毒、有甲病红肿的不做、过敏先试一个、不磨薄真甲、卸甲泡软不硬撕。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_recovery_pack_serves_owners_only_and_keeps_no_copies():
    d, problems = schema.validate(_load("data-recovery"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("别人的设备" in f and "授权" in f for f in a.forbidden) and any("一定能恢复" in f for f in a.forbidden)
    assert any("私人照片" in f for f in a.forbidden) and any("镜像或副本" in f for f in a.forbidden)
    assert any("开盘" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["数据恢复"]
    t = d.task_templates[0].description
    assert "是我本人的" in t and "先检测再报价" in t and "删掉镜像和副本" in t


def test_manicure_pack_sanitizes_and_never_harms_the_nail():
    d, problems = schema.validate(_load("home-manicure"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("消毒" in f for f in a.forbidden) and any("灰指甲" in f for f in a.forbidden)
    assert any("磨薄" in f for f in a.forbidden) and any("硬撕" in f for f in a.forbidden)
    assert any("孕期" in f for f in a.forbidden)
    assert {"money", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["上门美甲"]
    t = d.task_templates[0].description
    assert "当面消毒" in t and "不磨薄" in t and "泡软再推" in t


@pytest.mark.parametrize("key", ["data-recovery", "home-manicure"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600040401")
    for title, cat in (("误删的照片想找回", "数据恢复"), ("上门做纯色美甲", "上门美甲")):
        t = _post(client, requester, title=title, description="本周内", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("data-recovery", "data-recovery-helper", ("13900005001", "13900005002"), "替家人恢复数据要什么手续", "只给机主本人或有授权的人恢复"),
    ("data-recovery", "data-recovery-helper", ("13900005003", "13900005004"), "误删以后要停止使用吗", "出事后先别往里写东西、别反复开机"),
    ("data-recovery", "data-recovery-helper", ("13900005005", "13900005006"), "能保证恢复成功吗", "先检测再报价，不承诺一定能恢复"),
    ("data-recovery", "data-recovery-helper", ("13900005007", "13900005008"), "会不会打开私人照片", "只找客户点名的，翻到的内容不打开看"),
    ("data-recovery", "data-recovery-helper", ("13900005009", "13900005010"), "交付后镜像要删吗", "交付后当面删掉镜像和副本"),
    ("home-manicure", "home-manicure-helper", ("13900005011", "13900005012"), "金属工具怎么消毒", "工具一客一消毒，一次性用品一客一换"),
    ("home-manicure", "home-manicure-helper", ("13900005013", "13900005014"), "指甲变色还能做吗", "先看甲面和周围皮肤，有问题的不做"),
    ("home-manicure", "home-manicure-helper", ("13900005015", "13900005016"), "以前做完手指痒", "以前做完发痒的，先在一个指甲上试"),
    ("home-manicure", "home-manicure-helper", ("13900005017", "13900005018"), "上胶前打磨到什么程度", "打磨只去表面光泽，不磨薄真甲"),
    ("home-manicure", "home-manicure-helper", ("13900005019", "13900005020"), "卸甲怎么卸", "卸甲先泡软再推，不硬撕不硬抠"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("data-recovery", "data-recovery-helper", ("13900005021", "13900005022"), "前任找上门", "只给机主本人或有授权的人恢复"),
    ("data-recovery", "data-recovery-helper", ("13900005023", "13900005024"), "还能救吗", "出事后先别往里写东西、别反复开机"),
    ("data-recovery", "data-recovery-helper", ("13900005025", "13900005026"), "私密照怎么办", "只找客户点名的，翻到的内容不打开看"),
    ("data-recovery", "data-recovery-helper", ("13900005027", "13900005028"), "删干净了没有", "交付后当面删掉镜像和副本"),
    ("home-manicure", "home-manicure-helper", ("13900005029", "13900005030"), "会不会传染", "工具一客一消毒，一次性用品一客一换"),
    ("home-manicure", "home-manicure-helper", ("13900005031", "13900005032"), "有甲沟炎", "先看甲面和周围皮肤，有问题的不做"),
    ("home-manicure", "home-manicure-helper", ("13900005033", "13900005034"), "怕伤甲", "打磨只去表面光泽，不磨薄真甲"),
    ("home-manicure", "home-manicure-helper", ("13900005035", "13900005036"), "卸不下来怎么办", "卸甲先泡软再推，不硬撕不硬抠"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
