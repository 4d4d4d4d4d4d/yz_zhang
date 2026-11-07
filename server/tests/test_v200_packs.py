"""SCN-115 第四轮场景发掘的两个场景包（173 号 spec）：宠物上门照看、给爸妈办事。

交付物是两个数据文件 + 两个类目 + 一个技能概念 + 一个雷达主题；这里核对它们真的能上线、能答出最要紧的那几句话。
"""
import json

import pytest

from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.packs.topics import LEGAL_TOPICS, topic_of
from tests.conftest import auth, make_admin

API = "/api/v1"
NEW = ("pet-home-care", "elder-family-help")


def _load(key):
    return json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8"))


def _publish(client, definition, phones):
    a, b = make_admin(client, phones[0], "运营甲"), make_admin(client, phones[1], "运营乙")
    pid = client.post(f"{API}/admin/packs", json={"definition": definition}, headers=auth(a)).json()["id"]
    client.post(f"{API}/admin/packs/{pid}/submit", headers=auth(a))
    assert client.post(f"{API}/admin/packs/{pid}/approve", headers=auth(b)).status_code == 200


@pytest.mark.parametrize("key", NEW)
def test_new_packs_pass_the_platform_red_lines(key):
    d, problems = schema.validate(_load(key))
    assert d is not None and not problems, problems
    for a in d.assistants:
        # 发单方的助手：钱、发布之外，还碰别人的门锁密码与老人的个人信息
        assert {"money", "publish", "share_personal"} <= set(a.human_gates), a.key
        assert a.forbidden and a.fallback_category
        assert any("诊疗" in f or "医疗" in f for f in a.forbidden), "不给诊疗、用药建议要写进禁止动作"
    assert all(k.source for k in d.knowledge) and all(t.acceptance for t in d.task_templates)
    from app.modules.task.service import ADDED_CATEGORIES, SEED_CATEGORIES

    names = {c["name"] for c in SEED_CATEGORIES + ADDED_CATEGORIES}
    assert {t.category for t in d.task_templates} <= names, "模板用了不存在的类目"
    assert {a.fallback_category for a in d.assistants} <= names, "答不了时的去处类目不存在"


def test_subsidy_policy_carries_an_expiry_so_it_gets_reviewed():
    """补贴各地每年重发：政策条目必须带有效期，过期就在雷达上被看见。"""
    d, _ = schema.validate(_load("elder-family-help"))
    policy = [k for k in d.knowledge if k.kind == "policy"]
    assert policy and all(k.valid_until for k in policy)


@pytest.mark.parametrize("key,assistant,questions,title", [
    ("pet-home-care", "pet-care-advisor", ("我家狗咬了人谁负责", "宠物伤人怎么办"), "宠物咬了人、抓伤了人谁负责"),
    ("pet-home-care", "pet-care-advisor", ("猫生病了能让上门的人喂药吗",), "给宠物看病、用药找执业兽医"),
    ("pet-home-care", "pet-sitter-coach", ("遛狗要系绳吗",), "遛狗要系犬绳、戴犬牌"),
    ("pet-home-care", "pet-care-advisor", ("春节要提前多久约",), "节假日要提前约"),
    ("elder-family-help", "elder-help-advisor", ("我妈接到电话让转账到安全账户", "要验证码的电话"),
     "防电信诈骗：不轻信、不透露、不转账、及时报案"),
    ("elder-family-help", "elder-help-advisor", ("装扶手有补贴吗",), "居家适老化改造补贴怎么查"),
    ("elder-family-help", "elder-help-advisor", ("陪伴的人能帮我爸喂药吗",), "上门陪伴不是医疗护理"),
])
def test_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, questions, title):
    phones = {"pet-home-care": ("13900000801", "13900000802"), "elder-family-help": ("13900000803", "13900000804")}[key]
    _publish(client, _load(key), phones)
    for q in questions:
        r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
        assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])


def test_import_seeds_picks_up_the_two_new_packs(client):
    a = make_admin(client, "13900000805", "运营甲")
    out = client.post(f"{API}/admin/packs/import-seeds", headers=auth(a)).json()
    assert set(NEW) <= set(out["created"]) and out["invalid"] == []


def test_new_categories_exist_so_templates_can_be_posted(client, requester):
    cats = {c["name"] for c in client.get(f"{API}/categories").json()}
    assert {"宠物照护", "助老陪伴"} <= cats


def test_pet_questions_land_in_their_own_radar_topic():
    """宠物伤人、照看纠纷原先落到「其他」，雷达看不出来该补哪类知识。"""
    assert topic_of("邻居家的狗咬伤了我孩子", LEGAL_TOPICS) == "宠物饲养"
    assert topic_of("上门喂猫的人把猫弄丢了", LEGAL_TOPICS) == "宠物饲养"
    assert topic_of("房东不退押金怎么办", LEGAL_TOPICS) == "租房买房"
