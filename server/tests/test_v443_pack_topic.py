"""PACK-092（416 号 spec，V443）主题打头、后面粘着情态词的问法（「楼下要拦吗」「打药要注意什么」）。

412 / 415 号试问法时撞上：知识标题里就有「楼下」「打药」，问法却答不上。
检索把「楼下要拦」当一整串，二字切片里只有打头那片命中，不到「一半且至少 2 片」就整组不算。
修法只看情态词前面那段、只看标题，免得把只靠标签的口语也接住（只靠标签的闸门用同一套打分）。
"""
from app.modules.packs import service as psvc
from tests.conftest import auth
from tests.test_pack_tag_only_questions import score_without_tags
from tests.test_v286_packs import _publish

API = "/api/v1"
CORDON = "楼下拉警戒区有人看护，六级以上大风雨雪雾停工"


def test_topics_are_the_part_before_the_modal_word():
    assert psvc.topics("楼下要拦吗") == ["楼下"]
    assert psvc.topics("修剪树枝要注意什么") == ["修剪树枝"]
    assert psvc.topics("没证可以接吗") == ["没证"]
    assert psvc.topics("客户硬说我把他车蹭了") == []          # 没有情态词：与以前一样
    assert psvc.topics("能用诱捕笼吗") == []                  # 情态词打头，前面没有主题


def test_topic_counts_only_in_the_title():
    assert psvc.topic_bonus(CORDON, "楼下要拦吗") == psvc.TOPIC_IN_TITLE
    assert psvc.topic_bonus("电锯绿篱机修剪戴护具，靠近电线的树枝不自己剪", "修剪树枝要注意什么") == psvc.TOPIC_IN_TITLE
    assert psvc.topic_bonus(CORDON, "大风天能干吗") == 0       # 三个字里只有一片在标题里：不算
    assert psvc.topic_bonus("只做约定的项目，边界清楚", "客户要特殊服务") == 0
    assert psvc.knowledge_score("只做约定的项目", "客户说什么都先问清楚", [], [], "客户要特殊服务") == 0   # 正文里有不算


def test_the_tag_only_gate_scores_the_same_way():
    """只靠标签的闸门要用和助手问答同一套打分，不然闸门比真实检索宽，钉不住标签。"""
    assert score_without_tags("high-rise-cleaning", "楼下要拦吗", CORDON) >= 3


def test_the_assistant_now_answers_these_questions(client, requester):
    for key, assistant, phones, q, title in (
        ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700443001", "13700443002"), "楼下要拦吗", CORDON),
        ("garden-care", "garden-care-helper", ("13700443003", "13700443004"), "打药要注意什么", "打药先说药名和用途，按标签用量，避开孩子宠物"),
    ):
        _publish(client, key, phones)
        r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
        assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
