"""SCN-261 / SCN-262 第四十一轮场景发掘：墙面刷漆翻新、宠物善终（369 号 spec，V396）。

两个新类目都不要资质：
- 「墙面刷漆」：先看墙况、漆由主人定、家具地面先保护、遍数照约定刷并拍照、通风几天再住、剩漆不倒下水道；
- 「宠物善终」：遗体送有资质的机构不随意掩埋、单独与集体火化说清楚、骨灰遗物照清单交还、不借悲伤推销、照片不做宣传。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_repaint_pack_checks_the_wall_and_paints_the_agreed_coats():
    d, problems = schema.validate(_load("wall-repaint"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("起皮发霉" in f for f in a.forbidden) and any("少刷遍数" in f for f in a.forbidden)
    assert any("下水道" in f for f in a.forbidden) and any("替主人决定" in f for f in a.forbidden)
    assert any("不盖家具地面" in f for f in a.forbidden)
    assert {"money", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["墙面刷漆"]
    t = d.task_templates[0].description
    assert "先处理再刷" in t and "每遍拍照" in t and "通风" in t


def test_aftercare_pack_uses_licensed_facilities_and_never_upsells():
    d, problems = schema.validate(_load("pet-aftercare"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("随意掩埋" in f for f in a.forbidden) and any("集体火化说成单独火化" in f for f in a.forbidden)
    assert any("推销" in f for f in a.forbidden) and any("宣传" in f for f in a.forbidden)
    assert any("传染病" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["宠物善终"]
    t = d.task_templates[0].description
    assert "有资质的机构" in t and "不拿去宣传" in t and "单独 / 集体" in t


@pytest.mark.parametrize("key", ["wall-repaint", "pet-aftercare"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600039601")
    for title, cat in (("客厅卧室墙面翻新", "墙面刷漆"), ("家里的猫走了，想单独火化", "宠物善终")):
        t = _post(client, requester, title=title, description="这周内上门", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("wall-repaint", "wall-repaint-helper", ("13900004601", "13900004602"), "旧墙起皮能直接刷吗", "先看墙况：起皮、发霉、裂缝、返潮的先处理"),
    ("wall-repaint", "wall-repaint-helper", ("13900004603", "13900004604"), "漆的品牌和色号谁来定", "漆的品牌、色号、环保等级由主人定"),
    ("wall-repaint", "wall-repaint-helper", ("13900004605", "13900004606"), "开工前家具怎么保护", "开工前把家具、地面、开关插座盖好贴好"),
    ("wall-repaint", "wall-repaint-helper", ("13900004607", "13900004608"), "一遍底漆两遍面漆够吗", "底漆面漆照约定的遍数刷，每遍拍一张"),
    ("wall-repaint", "wall-repaint-helper", ("13900004609", "13900004610"), "刷完要通风几天", "刷完开窗通风，讲清几天后再住"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004611", "13900004612"), "疑似猫瘟走的要注意什么", "接单时轻声问清宠物怎么走的"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004613", "13900004614"), "遗体能埋在小区里吗", "遗体送有资质的机构，不随意掩埋"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004615", "13900004616"), "单独火化和集体火化有什么区别", "单独火化还是集体火化，说清楚、价钱写清楚"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004617", "13900004618"), "骨灰和项圈怎么交还", "骨灰与遗物照清单交还"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004619", "13900004620"), "能推荐骨灰盒吗", "不借悲伤推销，不拿照片做宣传"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("wall-repaint", "wall-repaint-helper", ("13900004621", "13900004622"), "墙角有霉斑", "先看墙况：起皮、发霉、裂缝、返潮的先处理"),
    ("wall-repaint", "wall-repaint-helper", ("13900004623", "13900004624"), "刷完有色差", "漆的品牌、色号、环保等级由主人定"),
    ("wall-repaint", "wall-repaint-helper", ("13900004625", "13900004626"), "师傅会不会偷工", "底漆面漆照约定的遍数刷，每遍拍一张"),
    ("wall-repaint", "wall-repaint-helper", ("13900004627", "13900004628"), "屋里味道大", "刷完开窗通风，讲清几天后再住"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004629", "13900004630"), "楼下花坛行不行", "遗体送有资质的机构，不随意掩埋"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004631", "13900004632"), "会不会被掉包", "单独火化还是集体火化，说清楚、价钱写清楚"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004633", "13900004634"), "想留个纪念", "骨灰与遗物照清单交还"),
    ("pet-aftercare", "pet-aftercare-helper", ("13900004635", "13900004636"), "临时加价怎么办", "不借悲伤推销，不拿照片做宣传"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
