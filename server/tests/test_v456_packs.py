"""SCN-318 / SCN-319 第六十九轮场景发掘：新生儿上门摄影、儿童居家安全防护安装（429 号 spec，V456）。

两个新类目都不要资质：
- 「新生儿上门摄影」：危险造型只用后期合成、拍摄师健康洗手消毒、按宝宝作息随时停、
  照片不经家长书面同意不公开（个保法第三十一条）、报价交付写清不强推加片（消保法第二十条）；
- 「儿童居家安全防护安装」：按年龄评估不推整套、护栏竖杆间距不大于 11 厘米且不封死逃生（GB 50352）、
  高柜固定到墙上、插座药品燃气逐项防护（未成年人保护法第十八条）、装完演示并说清不能代替看护。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091，含 PACK-093 逐个标签检查）离线试过。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_newborn_pack_keeps_babies_safe_and_photos_private():
    d, problems = schema.validate(_load("newborn-photo"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("危险造型" in f for f in a.forbidden) and any("洗手消毒" in f for f in a.forbidden)
    assert any("哭闹" in f for f in a.forbidden) and any("公开宝宝照片" in f for f in a.forbidden)
    assert any("强推加片" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["新生儿上门摄影"]
    t = d.task_templates[0].description
    assert "后期合成" in t and "书面同意" in t and "洗手消毒" in t


def test_childproofing_pack_guards_windows_without_sealing_the_exit():
    d, problems = schema.validate(_load("childproofing"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("推一整套" in f for f in a.forbidden) and any("封死" in f for f in a.forbidden)
    assert any("固定到墙上" in f for f in a.forbidden) and any("上锁" in f for f in a.forbidden)
    assert any("不用看护" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["儿童居家安全防护安装"]
    t = d.task_templates[0].description
    assert "11 厘米" in t and "不封死逃生" in t and "不能代替看护" in t


@pytest.mark.parametrize("key", ["newborn-photo", "childproofing"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600045601")
    for title, cat in (("宝宝满月上门拍照", "新生儿上门摄影"), ("孩子会爬了装防护", "儿童居家安全防护安装")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("newborn-photo", "newborn-photo-helper", ("13700456001", "13700456002"), "托腮造型安全吗", "宝宝安全第一：危险造型只用后期合成，实拍时家长手扶"),
    ("newborn-photo", "newborn-photo-helper", ("13700456003", "13700456004"), "拍摄师要消毒吗", "拍摄师身体健康，进门洗手消毒，包布道具洗干净"),
    ("newborn-photo", "newborn-photo-helper", ("13700456005", "13700456006"), "宝宝作息怎么安排", "按宝宝的作息拍，喂奶换尿布随时停，控制时长"),
    ("newborn-photo", "newborn-photo-helper", ("13700456007", "13700456008"), "照片能做样片吗", "照片不经家长书面同意，不公开、不做样片"),
    ("newborn-photo", "newborn-photo-helper", ("13700456009", "13700456010"), "加片怎么收费", "报价、精修张数、底片、加片价事先写清，不现场强推"),
    ("childproofing", "childproofing-helper", ("13700456011", "13700456012"), "上门先评估什么", "先上门按孩子的年龄评估，按需要装，不推一整套"),
    ("childproofing", "childproofing-helper", ("13700456013", "13700456014"), "窗户护栏间距多大", "窗户护栏竖杆间距不大于 11 厘米，孩子爬不上去，又不封死逃生"),
    ("childproofing", "childproofing-helper", ("13700456015", "13700456016"), "柜子要固定吗", "高柜电视柜抽屉柜用防倾倒配件固定到墙上"),
    ("childproofing", "childproofing-helper", ("13700456017", "13700456018"), "药品清洁剂怎么放", "插座保护盖、防撞角、柜门锁、燃气灶开关保护逐项装，药品清洁剂放高处上锁"),
    ("childproofing", "childproofing-helper", ("13700456019", "13700456020"), "装完要演示吗", "装完一项项演示，说清只能减少风险、不能代替看护"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("newborn-photo", "newborn-photo-helper", ("13700456021", "13700456022"), "憋着", "宝宝安全第一：危险造型只用后期合成，实拍时家长手扶"),
    ("newborn-photo", "newborn-photo-helper", ("13700456023", "13700456024"), "第二天就感冒", "拍摄师身体健康，进门洗手消毒，包布道具洗干净"),
    ("newborn-photo", "newborn-photo-helper", ("13700456025", "13700456026"), "一直哭", "按宝宝的作息拍，喂奶换尿布随时停，控制时长"),
    ("newborn-photo", "newborn-photo-helper", ("13700456027", "13700456028"), "没问我", "照片不经家长书面同意，不公开、不做样片"),
    ("childproofing", "childproofing-helper", ("13700456029", "13700456030"), "好几千", "先上门按孩子的年龄评估，按需要装，不推一整套"),
    ("childproofing", "childproofing-helper", ("13700456031", "13700456032"), "头卡进去", "窗户护栏竖杆间距不大于 11 厘米，孩子爬不上去，又不封死逃生"),
    ("childproofing", "childproofing-helper", ("13700456033", "13700456034"), "柜子倒了", "高柜电视柜抽屉柜用防倾倒配件固定到墙上"),
    ("childproofing", "childproofing-helper", ("13700456035", "13700456036"), "误吞", "插座保护盖、防撞角、柜门锁、燃气灶开关保护逐项装，药品清洁剂放高处上锁"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
