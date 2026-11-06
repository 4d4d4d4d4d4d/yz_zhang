"""SCN-306 / SCN-307 第六十三轮场景发掘：志愿填报咨询、户外徒步领队（419 号 spec，V446）。

两个新类目都不要资质：
- 「志愿填报咨询」：不承诺录取（广告法第二十四条）、只用公开的招生计划和往年分数不卖内部数据、
  考生本人登录填报不要账号密码、冲稳保拉开梯度讲清风险、分数身份信息只用于这一单（个保法第六条）；
- 「户外徒步领队」：难度如实写并劝退体力不够的、查天气定折返时间、买户外意外险
  （民法典第一千一百九十八条、第一千一百七十六条）、前有领队后有收队并点人数、只走开放线路。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091）离线试过。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_gaokao_pack_promises_nothing_and_never_takes_the_password():
    d, problems = schema.validate(_load("gaokao-advisor"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("承诺录取" in f for f in a.forbidden) and any("内部数据" in f for f in a.forbidden)
    assert any("账号密码" in f for f in a.forbidden) and any("不拉梯度" in f for f in a.forbidden)
    assert any("留存或外传" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["志愿填报咨询"]
    t = d.task_templates[0].description
    assert "不承诺录取" in t and "考生本人登录填报" in t and "冲稳保" in t


def test_hiking_pack_turns_back_on_time_and_counts_heads():
    d, problems = schema.validate(_load("hiking-leader"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("难度写轻" in f for f in a.forbidden) and any("折返时间" in f for f in a.forbidden)
    assert any("不买保险" in f for f in a.forbidden) and any("收队" in f for f in a.forbidden)
    assert any("未开放区域" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["户外徒步领队"]
    t = d.task_templates[0].description
    assert "折返时间" in t and "户外意外险" in t and "收队" in t


@pytest.mark.parametrize("key", ["gaokao-advisor", "hiking-leader"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600044601")
    for title, cat in (("孩子 580 分想看看志愿", "志愿填报咨询"), ("周末十人徒步带队", "户外徒步领队")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446001", "13700446002"), "能保证录取吗", "不承诺录取，不说「保过」"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446003", "13700446004"), "用哪些数据", "只用公开的招生计划和往年分数，不卖内部数据"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446005", "13700446006"), "要给你账号密码吗", "考生本人登录填报，不要账号密码、不代填"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446007", "13700446008"), "冲稳保怎么分", "冲稳保拉开梯度，讲清滑档和调剂的风险"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446009", "13700446010"), "分数信息会外传吗", "分数和身份信息只用于这一单，不留存不外传"),
    ("hiking-leader", "hiking-leader-helper", ("13700446011", "13700446012"), "路线难度怎么写", "路线距离、爬升、难度如实写，体力不够的提前劝退"),
    ("hiking-leader", "hiking-leader-helper", ("13700446013", "13700446014"), "折返时间怎么定", "出发前查天气，定好折返时间，到点就回"),
    ("hiking-leader", "hiking-leader-helper", ("13700446015", "13700446016"), "要买什么保险", "给每个队员买户外意外险，名单和保险对上"),
    ("hiking-leader", "hiking-leader-helper", ("13700446017", "13700446018"), "收队要做什么", "检查装备，前有领队后有收队，每到一个点数人数"),
    ("hiking-leader", "hiking-leader-helper", ("13700446019", "13700446020"), "能走野线吗", "只走开放的线路，不进未开放区域，不在禁火区用火"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446021", "13700446022"), "滑档", "不承诺录取，不说「保过」"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446023", "13700446024"), "特殊渠道", "只用公开的招生计划和往年分数，不卖内部数据"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446025", "13700446026"), "验证码", "考生本人登录填报，不要账号密码、不代填"),
    ("gaokao-advisor", "gaokao-advisor-helper", ("13700446027", "13700446028"), "骚扰电话", "分数和身份信息只用于这一单，不留存不外传"),
    ("hiking-leader", "hiking-leader-helper", ("13700446029", "13700446030"), "走不动", "路线距离、爬升、难度如实写，体力不够的提前劝退"),
    ("hiking-leader", "hiking-leader-helper", ("13700446031", "13700446032"), "天黑了", "出发前查天气，定好折返时间，到点就回"),
    ("hiking-leader", "hiking-leader-helper", ("13700446033", "13700446034"), "扭伤", "给每个队员买户外意外险，名单和保险对上"),
    ("hiking-leader", "hiking-leader-helper", ("13700446035", "13700446036"), "少了一个人", "检查装备，前有领队后有收队，每到一个点数人数"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
