"""SCN-265 / SCN-266 第四十三轮场景发掘：上门汽车小保养、阳台绿植养护（373 号 spec，V400）。

两个新类目都不要资质：
- 「上门汽车保养」：机油照手册、换件给车主看、废机油是危险废物不乱倒、安全支架再钻车底、只做说好的；
- 「绿植养护」：先看光和水、有孩子猫狗的家里用药先说清楚、护栏外不探身、代浇按次拍照、进门方式用完交还。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_car_pack_follows_the_manual_and_disposes_waste_oil_properly():
    d, problems = schema.validate(_load("mobile-car-service"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("下水道" in f for f in a.forbidden) and any("千斤顶" in f for f in a.forbidden)
    assert any("保养手册" in f for f in a.forbidden) and any("推销" in f for f in a.forbidden)
    assert any("没换" in f for f in a.forbidden)
    assert {"money", "publish"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["上门汽车保养"]
    t = d.task_templates[0].description
    assert "手册机油规格" in t and "换前换后给我看" in t and "废机油旧滤带走" in t


def test_plant_pack_is_careful_with_pesticides_heights_and_door_codes():
    d, problems = schema.validate(_load("plant-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("孩子宠物" in f and "用药" in f for f in a.forbidden) and any("护栏外" in f for f in a.forbidden)
    assert any("门锁密码" in f for f in a.forbidden) and any("保证一定养活" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["绿植养护"]
    t = d.task_templates[0].description
    assert "用药先告诉我" in t and "护栏外的不做" in t and "每次上门拍照" in t


@pytest.mark.parametrize("key", ["mobile-car-service", "plant-care"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600040001")
    for title, cat in (("小区车位换机油机滤", "上门汽车保养"), ("出差两周帮忙浇花", "绿植养护")):
        t = _post(client, requester, title=title, description="周末", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("mobile-car-service", "mobile-car-service-helper", ("13900004801", "13900004802"), "机油规格怎么选", "机油规格照保养手册，不按手里有什么换"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004803", "13900004804"), "换下来的机滤要给车主看吗", "换前拍旧件、换后给车主看新件和油位"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004805", "13900004806"), "废机油怎么处理", "废机油、旧机滤是危险废物，带走交有资质的回收"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004807", "13900004808"), "用千斤顶顶起来能钻车底吗", "千斤顶顶起后放安全支架，再钻车底"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004809", "13900004810"), "看到刹车片薄了要不要直接换", "只做说好的项目，别的毛病说清楚让车主自己定"),
    ("plant-care", "plant-care-helper", ("13900004811", "13900004812"), "叶子发黄是怎么回事", "植物不好先看光和水，别急着换土用药"),
    ("plant-care", "plant-care-helper", ("13900004813", "13900004814"), "家里有猫能用药吗", "有孩子和猫狗的家里，用药先说清楚、选低毒的"),
    ("plant-care", "plant-care-helper", ("13900004815", "13900004816"), "护栏外的花架怎么修剪", "外挑阳台、护栏外的花架不探身、不翻出去"),
    ("plant-care", "plant-care-helper", ("13900004817", "13900004818"), "出差代浇要拍照吗", "出差代浇照约定的次数上门，每次拍照回报"),
    ("plant-care", "plant-care-helper", ("13900004819", "13900004820"), "换盆会不会伤根", "换盆不伤根，状态不好的先说清楚不打包票"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("mobile-car-service", "mobile-car-service-helper", ("13900004821", "13900004822"), "怕加错油", "机油规格照保养手册，不按手里有什么换"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004823", "13900004824"), "会不会偷换配件", "换前拍旧件、换后给车主看新件和油位"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004825", "13900004826"), "车会不会滑落", "千斤顶顶起后放安全支架，再钻车底"),
    ("mobile-car-service", "mobile-car-service-helper", ("13900004827", "13900004828"), "要洗节气门吗", "只做说好的项目，别的毛病说清楚让车主自己定"),
    ("plant-care", "plant-care-helper", ("13900004829", "13900004830"), "花都蔫了", "植物不好先看光和水，别急着换土用药"),
    ("plant-care", "plant-care-helper", ("13900004831", "13900004832"), "长了红蜘蛛", "有孩子和猫狗的家里，用药先说清楚、选低毒的"),
    ("plant-care", "plant-care-helper", ("13900004833", "13900004834"), "回来花全干死了", "出差代浇照约定的次数上门，每次拍照回报"),
    ("plant-care", "plant-care-helper", ("13900004835", "13900004836"), "还能救活吗", "换盆不伤根，状态不好的先说清楚不打包票"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
