"""SCN-276 / SCN-277 第四十八轮场景发掘：瓷砖美缝、网店商品拍摄（385 号 spec，V412）。

两个新类目都不要资质：
- 「瓷砖美缝」：先清缝再打胶、材料当面开封、颜色先打小样、不碰的地方先贴保护、固化前不踩不沾水、美缝不是防水；
- 「商品拍摄」：先要规格清单、颜色按实物放色卡校色、修图只修瑕疵不改商品、模特签肖像授权、样品收发留底。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_grout_pack_cleans_first_and_never_swaps_materials():
    d, problems = schema.validate(_load("tile-grout"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不清缝" in f for f in a.forbidden) and any("偷换" in f for f in a.forbidden)
    assert any("小样" in f for f in a.forbidden) and any("防水" in f for f in a.forbidden)
    assert any("保护" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["瓷砖美缝"]
    t = d.task_templates[0]
    assert "先清缝再施工" in t.description and "当面开封" in t.description and "打小样" in t.description


def test_photo_pack_keeps_colors_true_and_retouching_honest():
    d, problems = schema.validate(_load("product-photography"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("颜色调得跟实物不符" in f for f in a.forbidden) and any("改变商品本身" in f for f in a.forbidden)
    assert any("肖像" in f for f in a.forbidden) and any("不留底" in f for f in a.forbidden)
    assert any("使用范围" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["商品拍摄"]
    t = d.task_templates[0].description
    assert "放色卡校色" in t and "修图只修瑕疵" in t and "签肖像授权" in t


@pytest.mark.parametrize("key", ["tile-grout", "product-photography"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600041201")
    for title, cat in (("卫生间地面美缝", "瓷砖美缝"), ("拍二十款新品主图", "商品拍摄")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("tile-grout", "tile-grout-helper", ("13900005301", "13900005302"), "旧缝要擦干净吗", "先把旧缝清到够深、擦干净，再打胶"),
    ("tile-grout", "tile-grout-helper", ("13900005303", "13900005304"), "材料要当面开封吗", "材料当面开封，品牌支数写进约定"),
    ("tile-grout", "tile-grout-helper", ("13900005305", "13900005306"), "颜色怎么定", "颜色先在不显眼处打一小段小样"),
    ("tile-grout", "tile-grout-helper", ("13900005307", "13900005308"), "要贴美纹纸保护吗", "不碰的地方先贴美纹纸，溢胶趁没干刮掉"),
    ("tile-grout", "tile-grout-helper", ("13900005309", "13900005310"), "美缝能当防水吗", "固化前不踩不沾水；美缝不是防水"),
    ("product-photography", "product-photography-helper", ("13900005311", "13900005312"), "开拍前要哪些规格", "开拍前要到平台规格和拍摄清单"),
    ("product-photography", "product-photography-helper", ("13900005313", "13900005314"), "颜色怎么校", "颜色按实物拍，放色卡校色，不调得跟实物差很多"),
    ("product-photography", "product-photography-helper", ("13900005315", "13900005316"), "修图只修瑕疵吗", "修图只修瑕疵，不改商品本身"),
    ("product-photography", "product-photography-helper", ("13900005317", "13900005318"), "模特要签肖像授权吗", "模特签肖像授权，字体音乐道具的授权写清"),
    ("product-photography", "product-photography-helper", ("13900005319", "13900005320"), "样品收到要怎么签收", "样品收发拍开箱视频、对清单签收"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("tile-grout", "tile-grout-helper", ("13900005321", "13900005322"), "胶掉了", "先把旧缝清到够深、擦干净，再打胶"),
    ("tile-grout", "tile-grout-helper", ("13900005323", "13900005324"), "怕以次充好", "材料当面开封，品牌支数写进约定"),
    ("tile-grout", "tile-grout-helper", ("13900005325", "13900005326"), "有色差", "颜色先在不显眼处打一小段小样"),
    ("tile-grout", "tile-grout-helper", ("13900005327", "13900005328"), "能拖地吗", "固化前不踩不沾水；美缝不是防水"),
    ("product-photography", "product-photography-helper", ("13900005329", "13900005330"), "要重裁", "开拍前要到平台规格和拍摄清单"),
    ("product-photography", "product-photography-helper", ("13900005331", "13900005332"), "偏色了", "颜色按实物拍，放色卡校色，不调得跟实物差很多"),
    ("product-photography", "product-photography-helper", ("13900005333", "13900005334"), "被说图文不符", "修图只修瑕疵，不改商品本身"),
    ("product-photography", "product-photography-helper", ("13900005335", "13900005336"), "被找上门了", "模特签肖像授权，字体音乐道具的授权写清"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
