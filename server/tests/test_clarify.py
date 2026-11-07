"""AI-DEC-001 对话式需求澄清（366 号 spec，V394）。

发单人只会说一句话时，服务端追问几句、把需求问清，再给一份能带到发布页的草稿。规则版、不调模型、不落库。
"""
from app.modules.task import clarify as clarify_mod
from tests.conftest import auth

API = "/api/v1/tasks/clarify"


def _ask(client, u, text, answers=None, **kw):
    r = client.post(API, json={"text": text, "answers": answers or {}, **kw}, headers=auth(u))
    assert r.status_code == 200, r.text
    from tests.test_client_shape_alignment import _assert_shape

    body = r.json()
    _assert_shape(body, "ClarifyResult")
    return body


def test_a_one_liner_gets_follow_up_questions_and_becomes_ready_after_answers(client, requester):
    first = _ask(client, requester, "家里要打扫一下")
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(first, "ClarifyResult")   # 写在 test_ 函数里：扫除闸门只认这里的断言（359 号 spec）
    assert first["ready"] is False and first["draft"]["category"] == "保洁", "「打扫」认出是保洁"
    keys = [q["key"] for q in first["questions"]]
    assert keys == ["where", "when", "scope"] and all(q["required"] for q in first["questions"])
    assert first["remaining_required"] == 4
    answers = {"where": "上海浦东，张江的小区", "when": "这周六上午", "scope": "两室一厅，厨房卫生间重点"}
    second = _ask(client, requester, "家里要打扫一下", answers)
    assert [q["key"] for q in second["questions"]][:1] == ["acceptance"] and second["ready"] is False
    answers["acceptance"] = "厨房台面和灶台没有油渍，卫生间玻璃没有水印"
    third = _ask(client, requester, "家里要打扫一下", answers)
    assert third["ready"] is True and third["remaining_required"] == 0
    assert [q["key"] for q in third["questions"]] == ["budget"], "必答的答完了，选答的还可以问"
    d = third["draft"]
    assert d["title"] == "家里要打扫一下" and d["is_remote"] is False
    for line in ("地点：上海浦东", "时间：这周六上午", "要做到：两室一厅", "验收：厨房台面"):
        assert line in d["description"]
    answers["budget"] = "300 元"
    assert _ask(client, requester, "家里要打扫一下", answers)["draft"]["budget_cents"] == 30000


def test_unknown_category_is_asked_with_options_not_guessed(client, requester):
    r = _ask(client, requester, "帮我弄一下那个东西")
    assert r["draft"]["category"] == "" and r["questions"][0]["key"] == "category"
    assert r["questions"][0]["options"], "给几个常见类目让人选"
    picked = _ask(client, requester, "帮我弄一下那个东西", {"category": "跑腿"})
    assert picked["draft"]["category"] == "跑腿"
    bogus = _ask(client, requester, "帮我弄一下那个东西", {"category": "不存在的类目"})
    assert bogus["draft"]["category"] == "" and bogus["questions"][0]["key"] == "category"


def test_what_is_already_said_is_not_asked_again(client, requester):
    r = _ask(client, requester, "明天下午 3 点线上帮我做个 logo，交付 AI 源文件和三种尺寸的 PNG，按这个标准验收")
    keys = [q["key"] for q in r["questions"]]
    assert "when" not in keys and "where" not in keys and "acceptance" not in keys and "scope" not in keys
    assert r["draft"]["category"] == "设计" and r["draft"]["is_remote"] is True and r["ready"] is True


def test_family_mentions_suggest_posting_on_behalf(client, requester):
    r = _ask(client, requester, "我妈家的水龙头漏水", {"where": "杭州西湖区", "when": "周日上午", "scope": "厨房一个水龙头",
                                                  "acceptance": "不再滴水", "budget": "100"})
    assert r["draft"]["on_behalf_hint"] is True and [q["key"] for q in r["questions"]] == ["for_whom"]
    done = _ask(client, requester, "我妈家的水龙头漏水", {"where": "杭州西湖区", "when": "周日上午", "scope": "厨房一个水龙头",
                                                     "acceptance": "不再滴水", "budget": "100", "for_whom": "我妈，姓王"})
    assert done["questions"] == [] and "服务对象：我妈" in done["draft"]["description"]


def test_blocked_requests_are_told_up_front_and_never_ready(client, requester):
    r = _ask(client, requester, "帮我代开安眠药")
    assert r["blocked"] and r["blocked"]["code"] == "errand_restricted" and r["questions"] == [] and r["ready"] is False
    k12 = _ask(client, requester, "给初二的孩子补习数学")
    assert k12["blocked"]["code"] == "k12_subject_tutoring"
    ok = _ask(client, requester, "代买感冒药")
    assert ok["blocked"] is None


def test_input_limits_and_login(client, requester):
    assert client.post(API, json={"text": "x"}, headers=auth(requester)).status_code == 422
    assert client.post(API, json={"text": "好" * 501}, headers=auth(requester)).status_code == 422
    assert client.post(API, json={"text": "打扫卫生", "answers": {"x": "y"}, "extra": 1}, headers=auth(requester)).status_code == 422
    assert client.post(API, json={"text": "打扫卫生"}).status_code in (401, 403)
    unknown = _ask(client, requester, "家里要打扫一下", {"not_a_question": "忽略"})
    assert "not_a_question" not in unknown["draft"]["description"]
    # 不认识的键整个忽略：里面写什么都不参与拦截判断、类目猜测和草稿
    ignored = _ask(client, requester, "家里要打扫一下", {"not_a_question": "帮我代开安眠药"})
    assert ignored["blocked"] is None and "安眠药" not in ignored["draft"]["description"]


def test_category_guess_prefers_the_longest_name():
    assert clarify_mod.guess_category("空调外机拆装（高处作业）要两个人", ["空调外机拆装（高处作业）", "搬家"]) == "空调外机拆装（高处作业）"
    assert clarify_mod.guess_category("家电维修和家电清洗", ["家电清洗", "家电维修"]) in ("家电清洗", "家电维修")
    assert clarify_mod.guess_category("什么都没说", ["保洁"]) == ""
