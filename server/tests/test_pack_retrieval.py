"""SCN-105 场景包知识检索（138 号 spec）：标签整词、连接词、技能概念展开。

137 号的「没做的」：「雇人还是发临时单」命中不到「临时单不能替代用工合同」——二字切片覆盖不到一半。
检索仍是摘录式、可解释的字面匹配，只是**多认出**三种情形；原来命中的照样命中。
"""
import json

from app.modules.notebook.service import terms
from app.modules.packs import schema
from app.modules.packs import service as psvc

SHOP = schema.validate(json.loads((psvc.SEEDS / "shop-temp-help.json").read_text(encoding="utf-8")))[0]
CREATOR = schema.validate(json.loads((psvc.SEEDS / "creator-freelance.json").read_text(encoding="utf-8")))[0]


def _keys(d, q):
    return [k.key for k, _ in psvc._knowledge_hits(d, [], q)]


def test_connector_words_are_not_topics():
    assert not any(t in ("还是", "或者") for t, _, _ in terms("雇人还是发临时单"))
    assert [t for t, w, _ in terms("雇人还是发临时单") if w == 3] == ["雇人", "发临时单"]


def test_questions_with_connectors_find_the_employment_rule():
    for q in ("雇人还是发临时单", "长期要人或者发临时单", "雇人以及买保险"):
        assert "temp-not-employment" in _keys(SHOP, q), q


def test_a_tag_named_in_the_question_is_a_strong_hit():
    assert psvc.tag_bonus(["雇人", "临时单", "x"], "我想雇人") == psvc.TAG_IN_QUESTION
    assert psvc.tag_bonus(["雇人", "雇人"], "雇人") == psvc.TAG_IN_QUESTION, "重复标签不重复计分"
    assert psvc.tag_bonus(["人"], "雇人") == 0, "一个字的标签不算"
    assert psvc.tag_bonus(["PSD"], "要 psd 源文件") == psvc.TAG_IN_QUESTION
    # 一整句没有标点、二字片覆盖不到一半时，只靠标签整词命中
    assert "temp-not-employment" in _keys(SHOP, "老板说雇人要签")


def test_skill_concepts_expand_pack_questions():
    """问「VI设计的版权」：概念表把 VI 设计展开成品牌设计及其别名，带「品牌设计」的条目也能找到。"""
    d = CREATOR.model_copy(deep=True)
    d.knowledge.append(schema.KnowledgeDef(key="brand-scope", title="品牌设计通常包含哪些交付物",
                                           body="品牌设计一般包括标志、标准色、标准字与基础应用。", source="平台经验"))
    assert "brand-scope" in _keys(d, "VI设计交什么")


def test_old_hits_still_hit_and_unrelated_still_miss():
    assert _keys(SHOP, "工伤保险")[0] == "injury-insurance"
    assert _keys(SHOP, "小时工工资多少")[0] == "part-time-pay"
    assert _keys(SHOP, "今天天气怎么样") == []


def test_admin_added_concepts_reach_pack_answers(client, requester):
    """运营在后台加的概念（不只是种子）也用于场景包问答：问的是「零工单」，找得到写着「临时单」的条目。"""
    from tests.conftest import auth, make_admin
    from tests.test_scenario_packs import SHOP as SHOP_SEED, _publish

    _publish(client, SHOP_SEED, phones=("13900000601", "13900000602"))
    ask = "/api/v1/packs/shop-temp-help/assistants/shop-helper/ask"
    before = client.post(ask, json={"q": "零工单"}, headers=auth(requester)).json()
    assert not any(c["kind"] == "pack" for c in before["citations"])
    admin = make_admin(client, "13900000603", "运营")
    r = client.post("/api/v1/admin/skill-concepts", json={"name": "临时单", "aliases": ["零工单"]}, headers=auth(admin))
    assert r.status_code in (200, 201), r.text
    after = client.post(ask, json={"q": "零工单"}, headers=auth(requester)).json()
    assert any(c["title"] == "平台上的临时单不能替代用工合同" for c in after["citations"]), after
