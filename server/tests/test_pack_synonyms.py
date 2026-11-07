"""PACK-092b（435 号 spec，V462）场景包检索认近义说法。

「天气不好还走吗」整串不命中，二字切片只有「天气」一片，写着「下雨」「打雷」的那条知识接不住。
近义表（packs/synonyms.json）只给场景包用：同组互为近义，includes 是单向的上位词（问「天气不好」也找「下雨」「大风」，
问「下雨」不去找「大风」）。助手问答、离线试问法（pack_probe）与只靠标签的闸门用同一个 pack_terms。
"""
import json

import pytest

from app.modules.notebook.service import MAX_TERMS, terms
from app.modules.packs import service as psvc
from app.modules.skills.service import concepts, norm
from scripts import pack_probe
from tests.conftest import auth
from tests.test_v286_packs import _publish

API = "/api/v1"


@pytest.mark.parametrize("key,q,title", [
    ("hiking-leader", "天气不好还走吗", "出发前查天气，定好折返时间，到点就回"),
    ("hiking-leader", "变天了怎么办", "出发前查天气，定好折返时间，到点就回"),
    ("wedding-planning", "暴雨怎么办", "流程单精确到分钟，下雨迟到设备坏都有备案"),
    ("high-rise-cleaning", "下大雨还干吗", "楼下拉警戒区有人看护，六级以上大风雨雪雾停工"),
    ("solar-heater-service", "下雪能上屋顶吗", "上屋顶前看天气，防滑系安全带，2 米以上持高处作业证"),
    ("team-building", "恶劣天气退钱吗", "提前看天气，备室内方案，改期和取消怎么算写清"),
])
def test_near_synonyms_reach_the_knowledge_that_uses_another_word(key, q, title):
    d = pack_probe.load(key)
    a = next(x for x in d.assistants if not x.knowledge or any(k.title == title and k.key in x.knowledge
                                                                for k in d.knowledge))
    assert title in [k.title for k, _ in psvc._knowledge_hits(d, a.knowledge, q)], q
    # 没有近义表就答不上——这几句正是因为它才接得住
    no_syn = [k.title for k in d.knowledge
              if psvc.knowledge_score(k.title, k.body, k.tags, terms(q), q) + psvc.tag_bonus(k.tags, q) >= 3]
    assert title not in no_syn, q


def test_the_assistant_endpoint_uses_the_synonyms(client, requester):
    _publish(client, "hiking-leader", ("13700462001", "13700462002"))
    r = client.post(f"{API}/packs/hiking-leader/assistants/hiking-leader-helper/ask",
                    json={"q": "天气不好还走吗"}, headers=auth(requester))
    assert r.status_code == 200, r.text
    assert any(c["title"] == "出发前查天气，定好折返时间，到点就回" for c in r.json()["citations"]), r.json()


def test_upper_words_expand_one_way_only():
    bad = psvc.synonyms_in("天气不好还走吗")
    assert "下雨" in bad and "大风" in bad and "结冰" in bad
    rain = psvc.synonyms_in("下雨了怎么办")
    assert "暴雨" in rain and "雨天" in rain
    assert not {"大风", "天气不好", "结冰"} & set(rain)          # 问下雨不去找大风、不反推上位词
    assert psvc.synonyms_in("报价怎么算") == []


def test_synonym_table_stays_clean():
    groups = psvc.synonym_groups()
    seen: dict[str, str] = {}
    skill_words = {norm(w) for c in concepts(None) for w in [c["name"], *c["aliases"]]}
    for name, g in groups.items():
        assert name in g["words"], f"组名「{name}」要是组里的一个写法"
        for w in g["words"]:
            assert len(w) >= 2, f"「{w}」太短：单字几乎哪条知识里都有"
            assert w not in seen, f"「{w}」同时在「{seen.get(w)}」和「{name}」两组里"
            assert norm(w) not in skill_words, f"「{w}」也是技能概念表里的词，两边会重复展开"
            seen[w] = name
        for inc in g["includes"]:
            assert inc in groups and inc != name, f"「{name}」包含的「{inc}」不是别的组"
        size = len(g["words"]) + sum(len(groups[i]["words"]) for i in g["includes"])
        assert size <= 24, f"「{name}」一展开就 {size} 个词，太宽"
    raw = json.loads(psvc.SYNONYMS.read_text(encoding="utf-8"))
    assert len(raw["groups"]) == len(groups), "组名重复了"


def test_synonyms_are_not_cut_off_by_the_term_limit():
    q = "我们周末徒步爬山露营团队活动安排路线行程天气不好还走吗"
    assert len(terms(q)) == MAX_TERMS                          # 问题本身就占满了
    ts = psvc.pack_terms(q)
    words = {t for t, _, _ in ts}
    assert {"下雨", "大风"} <= words
    syn = [x for x in ts if x[0] == "下雨"][0]
    assert syn[1] == psvc.SYNONYM_WEIGHT and all(g != syn[2] for t, _, g in ts if t != "下雨")   # 自成一组、只算整词


def test_probe_scores_with_the_same_terms_as_the_assistant():
    ok, why = pack_probe.probe(pack_probe.load("hiking-leader"), "天气不好还走吗", "出发前查天气", False)
    assert ok, why


def test_tag_only_checks_count_synonyms_too():
    """标题里写着「大风」，问「风很大」靠近义就接住了，不算「只靠标签」：试问法与闸门都要看得出来。"""
    from tests.test_pack_tag_only_questions import score_without_tags

    title = "楼下拉警戒区有人看护，六级以上大风雨雪雾停工"
    assert score_without_tags("high-rise-cleaning", "风很大", title) >= 3
    ok, why = pack_probe.probe(pack_probe.load("high-rise-cleaning"), "风很大", title[:8], True)
    assert not ok and "去掉标签也得" in why, why
