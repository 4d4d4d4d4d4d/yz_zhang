"""SCN-142 直播话术自查工具（210 号 spec，V238）。

小店直播顾问能读用户贴进来的话术，按词表标出绝对化用语、功效承诺、价格与限时的词和出处；
只标出来，不断定违规，改不改由用户定。
"""
from app.modules.packs.live import script_check
from tests.conftest import auth
from tests.test_v237_packs import KEY, _publish

API = "/api/v1"


def test_words_are_flagged_by_kind_with_their_source():
    r = script_check("家人们，这款面霜全网最低，第一品牌，用了根治痘痘，原价 199 今天 99，最后一天！最便宜就在这里，全网最低")
    got = [(h["word"], h["kind"]) for h in r["hits"]]
    assert ("全网最低", "绝对化用语") in got and ("第一", "绝对化用语") in got and ("最便宜", "绝对化用语") in got
    assert ("根治", "功效承诺") in got and ("原价", "价格与限时") in got and ("最后一天", "价格与限时") in got
    assert [w for w, _ in got].count("全网最低") == 1, "同一个词只报一次"
    assert next(h for h in r["hits"] if h["word"] == "根治")["source"] == "《广告法》第十七条"
    assert next(h for h in r["hits"] if h["word"] == "第一")["source"] == "《广告法》第九条第（三）项"
    assert script_check("这款面霜质地清爽，我自己用了一个月")["hits"] == []
    assert script_check("")["hits"] == [] and script_check(None)["hits"] == []


def test_the_live_advisor_runs_the_check_on_a_pasted_script(client, requester):
    _publish(client)
    q = "帮我看看这段话术：这款锅全网最低价，顶级不粘，原价 299 今天只要 99"
    r = client.post(f"{API}/packs/{KEY}/assistants/live-shop-advisor/ask", json={"q": q}, headers=auth(requester)).json()
    tool = next(c for c in r["citations"] if c["title"].startswith("话术自查"))
    assert "「全网最低」" in tool["snippet"] and "「顶级」" in tool["snippet"] and "「原价」" in tool["snippet"]
    clean = client.post(f"{API}/packs/{KEY}/assistants/live-shop-advisor/ask",
                        json={"q": "帮我看看这段话术：这款锅不粘、好清洗，我家用了半年"}, headers=auth(requester)).json()
    tool = next(c for c in clean["citations"] if c["title"].startswith("话术自查"))
    assert tool["title"] == "话术自查（标出 0 处）" and "以市场监管部门认定为准" in tool["snippet"]
    short = client.post(f"{API}/packs/{KEY}/assistants/live-shop-advisor/ask", json={"q": "这样说第一行吗"}, headers=auth(requester)).json()
    assert not any(c["title"].startswith("话术自查") for c in short["citations"]), "太短的问题不是贴话术，不跑自查"
