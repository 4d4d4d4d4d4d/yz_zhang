"""SCN-331 / SCN-332 第七十五轮场景发掘：健身器材安装维修、木地板维修（442 号 spec，V469）。

- 「健身器材安装维修」不要资质：动手前拔电源取安全钥匙、两人搬运放平留空地、跑带按说明调整只用专用硅油、
  装好低速试跑试急停、交代孩子宠物远离（消保法第十八条）；
- 「木地板维修」不要资质：先找水从哪来（消保法第二十条）、四周留伸缩缝、换板用余料或同款同色、
  异响分清龙骨与锁扣地暖地板不打钉、交代防潮（第五十二条）。
问法写测试之前都先用 scripts/pack_probe.py 离线试过；写完用 scripts/pack_mutate.py（PACK-094）做变异红验。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_fitness_pack_unplugs_first_and_tests_the_emergency_stop():
    d, problems = schema.validate(_load("fitness-equipment-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不拔电源" in f for f in a.forbidden) and any("一个人搬" in f for f in a.forbidden)
    assert any("机油" in f for f in a.forbidden) and any("不试急停" in f for f in a.forbidden)
    assert any("孩子远离" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["健身器材安装维修"]
    t = d.task_templates[0].description
    assert "拔电源、取安全钥匙" in t and "两人搬运" in t and "专用硅油" in t


def test_floor_pack_finds_the_water_first_and_never_nails_into_floor_heating():
    d, problems = schema.validate(_load("wood-floor-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("不找水源" in f for f in a.forbidden) and any("伸缩缝" in f for f in a.forbidden)
    assert any("别的颜色" in f for f in a.forbidden) and any("乱打钉" in f for f in a.forbidden)
    assert any("防潮" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["木地板维修"]
    t = d.task_templates[0].description
    assert "先找水" in t and "伸缩缝" in t and "不打钉" in t


@pytest.mark.parametrize("key", ["fitness-equipment-repair", "wood-floor-repair"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications(client, requester):
    w = make_verified(client, "13600046901")
    for title, cat in (("跑步机跑带跑偏", "健身器材安装维修"), ("客厅地板起拱", "木地板维修")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469001", "13700469002"), "要拔电源吗", "动手前先拔电源、取下安全钥匙"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469003", "13700469004"), "后面要留多少空地", "两个人抬，放在平整结实的地面上，后面留出两米左右空地"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469005", "13700469006"), "跑带跑偏怎么调", "跑带跑偏、打滑按说明书调松紧和左右，加专用硅油"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469007", "13700469008"), "急停要试吗", "装好先低速试跑，再试一次急停和拔安全钥匙能不能停"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469009", "13700469010"), "孩子要注意什么", "交代用完拔钥匙断电，孩子和宠物远离运转的跑带"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469011", "13700469012"), "地板起拱怎么办", "起拱、发黑先找水从哪来，不解决水源修了还会坏"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469013", "13700469014"), "伸缩缝要留吗", "起拱多半是四周没留伸缩缝，踢脚线下面切出缝来"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469015", "13700469016"), "换板颜色怎么配", "局部换板用客户留的余料或同款同色，先放几天适应湿度"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469017", "13700469018"), "踩着响怎么修", "踩着响先分清是龙骨松了还是锁扣坏了，地暖地板不乱打钉"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469019", "13700469020"), "怎么防潮", "修完交代拖地拧干、别泡水，开窗和空调怎么防潮"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469021", "13700469022"), "突然转", "动手前先拔电源、取下安全钥匙"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469023", "13700469024"), "砸到脚", "两个人抬，放在平整结实的地面上，后面留出两米左右空地"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469025", "13700469026"), "一股味", "跑带跑偏、打滑按说明书调松紧和左右，加专用硅油"),
    ("fitness-equipment-repair", "fitness-equipment-helper", ("13700469027", "13700469028"), "刹不住", "装好先低速试跑，再试一次急停和拔安全钥匙能不能停"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469029", "13700469030"), "又鼓起来", "起拱、发黑先找水从哪来，不解决水源修了还会坏"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469031", "13700469032"), "门关不上", "起拱多半是四周没留伸缩缝，踢脚线下面切出缝来"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469033", "13700469034"), "补丁", "局部换板用客户留的余料或同款同色，先放几天适应湿度"),
    ("wood-floor-repair", "wood-floor-helper", ("13700469035", "13700469036"), "地暖管", "踩着响先分清是龙骨松了还是锁扣坏了，地暖地板不乱打钉"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
