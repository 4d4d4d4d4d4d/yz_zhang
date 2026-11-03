"""SCN-263 / SCN-264 第四十二轮场景发掘：老照片扫描修复、净水器安装与换滤芯（371 号 spec，V398）。

两个新类目都不要资质：
- 「老照片修复」（创作者）：原件当面清点、不拆不裁、修复不编造（上色补全先说是猜的）、文件只交主人、交完删副本；
- 「净水器安装」：先看现场、不用电解 / TDS 演示吓唬人、到期哪级换哪级、查漏两遍、原装与否说清楚。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_photo_pack_restores_without_inventing_and_keeps_faces_private():
    d, problems = schema.validate(_load("photo-restoration"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("换脸" in f for f in a.forbidden) and any("上色和补全说成原样" in f for f in a.forbidden)
    assert any("作品集" in f for f in a.forbidden) and any("副本" in f for f in a.forbidden)
    assert any("不清点" in f for f in a.forbidden) and any("裁照片" in f for f in a.forbidden)
    assert {"money", "sign", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["老照片修复"]
    t = d.task_templates[0].description
    assert "当面清点" in t and "先修一张给我看" in t and "删除副本" in t


def test_purifier_pack_never_scares_and_replaces_only_what_is_due():
    d, problems = schema.validate(_load("water-purifier"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("电解" in f and "TDS" in f for f in a.forbidden) and any("没到期" in f for f in a.forbidden)
    assert any("非原装" in f for f in a.forbidden) and any("不查漏" in f for f in a.forbidden)
    assert {"money", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["净水器安装"]
    t = d.task_templates[0].description
    assert "哪一级到期换哪一级" in t and "查漏两遍" in t and "不做电解" in t


@pytest.mark.parametrize("key", ["photo-restoration", "water-purifier"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600039801")
    for title, cat in (("三十张老照片扫描修复", "老照片修复"), ("厨下净水器换滤芯", "净水器安装")):
        t = _post(client, requester, title=title, description="这周内", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("photo-restoration", "photo-restoration-helper", ("13900004701", "13900004702"), "原件怎么交接清点", "接原件时当面清点，拍照留底"),
    ("photo-restoration", "photo-restoration-helper", ("13900004703", "13900004704"), "粘在相册里的照片怎么扫描", "扫描不拆相册、不裁照片、不用胶水胶带"),
    ("photo-restoration", "photo-restoration-helper", ("13900004705", "13900004706"), "要不要给老照片上色", "修复只去损伤，不编造；上色补全先说是猜的"),
    ("photo-restoration", "photo-restoration-helper", ("13900004707", "13900004708"), "修好的能放进作品集吗", "文件只交主人本人，不做作品集、不发网上"),
    ("photo-restoration", "photo-restoration-helper", ("13900004709", "13900004710"), "交付后副本要删除吗", "原件照清单当面还，交完删掉自己的副本"),
    ("water-purifier", "water-purifier-helper", ("13900004711", "13900004712"), "装之前要看水压吗", "装之前看水压、进水角阀、插座和下水口"),
    ("water-purifier", "water-purifier-helper", ("13900004713", "13900004714"), "能用电解演示水质吗", "不用电解、TDS 笔演示吓唬人"),
    ("water-purifier", "water-purifier-helper", ("13900004715", "13900004716"), "反渗透膜要不要换", "哪一级到期就换哪一级"),
    ("water-purifier", "water-purifier-helper", ("13900004717", "13900004718"), "装完怎么查漏", "装完查漏两遍，十分钟后再看"),
    ("water-purifier", "water-purifier-helper", ("13900004719", "13900004720"), "兼容滤芯能用吗", "滤芯型号、价钱、是不是原装说清楚"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("photo-restoration", "photo-restoration-helper", ("13900004721", "13900004722"), "照片寄丢了怎么办", "接原件时当面清点，拍照留底"),
    ("photo-restoration", "photo-restoration-helper", ("13900004723", "13900004724"), "修完人变样了", "修复只去损伤，不编造；上色补全先说是猜的"),
    ("photo-restoration", "photo-restoration-helper", ("13900004725", "13900004726"), "会不会发到网上", "文件只交主人本人，不做作品集、不发网上"),
    ("photo-restoration", "photo-restoration-helper", ("13900004727", "13900004728"), "我电脑里还留着", "原件照清单当面还，交完删掉自己的副本"),
    ("water-purifier", "water-purifier-helper", ("13900004729", "13900004730"), "水变黄了是有毒吗", "不用电解、TDS 笔演示吓唬人"),
    ("water-purifier", "water-purifier-helper", ("13900004731", "13900004732"), "师傅说要全换", "哪一级到期就换哪一级"),
    ("water-purifier", "water-purifier-helper", ("13900004733", "13900004734"), "底下一直冒水", "装完查漏两遍，十分钟后再看"),
    ("water-purifier", "water-purifier-helper", ("13900004735", "13900004736"), "怕买到假滤芯", "滤芯型号、价钱、是不是原装说清楚"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
