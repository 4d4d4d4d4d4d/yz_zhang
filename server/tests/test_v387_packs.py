"""SCN-253 / SCN-254 第三十七轮场景发掘：新房验房、窗帘安装（360 号 spec，V387）。

两个数据文件、两个新类目，都不要资质。
验房：先看交付文件、问题拍照量数据、保修期限、只出清单不替业主签收、不收开发商好处；
窗帘：先量尺寸、打孔前探管线、登高有人扶不站窗台、石膏板吊顶找龙骨、拉绳收好防孩子缠绕。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_inspection_pack_lists_problems_and_never_signs_for_the_owner():
    d, problems = schema.validate(_load("home-inspection"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("签收" in f for f in a.forbidden) and any("没有问题" in f for f in a.forbidden)
    assert any("开发商" in f for f in a.forbidden) and any("破坏性" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["验房"]
    t = d.task_templates[0].description
    assert "不替我签收" in t or "我自己定" in t


def test_curtain_pack_detects_before_drilling_and_keeps_cords_away_from_children():
    d, problems = schema.validate(_load("curtain-installation"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("探测" in f for f in a.forbidden) and any("窗台" in f for f in a.forbidden)
    assert any("拉绳" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["窗帘安装"]
    t = d.task_templates[0].description
    assert "探测" in t and "拉绳" in t


@pytest.mark.parametrize("key", ["home-inspection", "curtain-installation"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_orders_without_a_certificate(client, requester):
    for title, cat in (("精装房收房验房", "验房"), ("客厅装窗帘轨道", "窗帘安装")):
        r = _post(client, requester, title=title, description="周末白天", category=cat)
        assert r.status_code in (200, 201), r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("home-inspection", "home-inspection-helper", ("13900004201", "13900004202"), "验房要带什么文件", "先看交付文件，对照着验"),
    ("home-inspection", "home-inspection-helper", ("13900004203", "13900004204"), "墙面空鼓怎么查", "问题拍照、量数据、标位置"),
    ("home-inspection", "home-inspection-helper", ("13900004205", "13900004206"), "卫生间防水保修几年", "保修期限：防水 5 年，水电管线和装修 2 年"),
    ("home-inspection", "home-inspection-helper", ("13900004207", "13900004208"), "业主问要不要先签字收房", "只出问题清单，不替业主签收"),
    ("home-inspection", "home-inspection-helper", ("13900004209", "13900004210"), "物业私下给介绍费", "只替业主看，不收开发商和物业的好处"),
    ("curtain-installation", "curtain-helper", ("13900004211", "13900004212"), "窗帘量多宽合适", "先量尺寸，写清装在哪"),
    ("curtain-installation", "curtain-helper", ("13900004213", "13900004214"), "打孔会不会打到电线", "打孔前探测墙里的电线水管"),
    ("curtain-installation", "curtain-helper", ("13900004215", "13900004216"), "能站窗台上装吗", "登高用稳梯、有人扶，不站窗台"),
    ("curtain-installation", "curtain-helper", ("13900004217", "13900004218"), "石膏板吊顶能装吗", "石膏板吊顶要找龙骨或加固"),
    ("curtain-installation", "curtain-helper", ("13900004219", "13900004220"), "家里有小孩百叶帘拉绳怎么办", "拉绳珠链收短固定，防孩子缠绕"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("home-inspection", "home-inspection-helper", ("13900004221", "13900004222"), "两书在哪", "先看交付文件，对照着验"),
    ("home-inspection", "home-inspection-helper", ("13900004223", "13900004224"), "开发商说过保了", "保修期限：防水 5 年，水电管线和装修 2 年"),
    ("home-inspection", "home-inspection-helper", ("13900004225", "13900004226"), "验收单", "只出问题清单，不替业主签收"),
    ("home-inspection", "home-inspection-helper", ("13900004227", "13900004228"), "业主让我打包票", "只替业主看，不收开发商和物业的好处"),
    ("curtain-installation", "curtain-helper", ("13900004229", "13900004230"), "客户说短了", "先量尺寸，写清装在哪"),
    ("curtain-installation", "curtain-helper", ("13900004231", "13900004232"), "要搬梯子吗", "登高用稳梯、有人扶，不站窗台"),
    ("curtain-installation", "curtain-helper", ("13900004233", "13900004234"), "遮光帘太重了", "石膏板吊顶要找龙骨或加固"),
    ("home-inspection", "home-inspection-helper", ("13900004235", "13900004236"), "两书在哪看", "先看交付文件，对照着验"),
    ("home-inspection", "home-inspection-helper", ("13900004237", "13900004238"), "开发商拿来验收单", "只出问题清单，不替业主签收"),
    ("curtain-installation", "curtain-helper", ("13900004239", "13900004240"), "绳子垂得太长", "拉绳珠链收短固定，防孩子缠绕"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
