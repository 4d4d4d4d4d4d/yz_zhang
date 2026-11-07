"""SCN-216 / SCN-217 / SCN-218 第二十三轮场景发掘：账号代运营、婚礼司仪，发单拦下刷粉刷量与买卖租借账号（335 号 spec，V362）。

两个数据文件、两个新类目（都不要资质），外加发单拦截一类（fake_traffic）。否定判断从「紧挨着」放宽到
「前 6 个字内、中间没有句读断开」，模板里的「不刷粉刷量、不买卖租借账号」不再被误拦，「不想自己写，代写毕业论文」照拦。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_account_ops_pack_keeps_the_account_in_the_clients_name_and_never_fakes_traffic():
    d, problems = schema.validate(_load("account-operation"))
    assert d is not None and not problems, problems
    assert d.segment == "studio"
    a = d.assistants[0]
    assert {"money", "sign"} <= set(a.human_gates)
    assert any("刷粉刷量" in f for f in a.forbidden) and any("代运营方名下" in f for f in a.forbidden)
    assert any("承诺涨多少粉" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["账号代运营"]
    assert "交还全部权限" in d.task_templates[0].description


def test_wedding_host_pack_spells_out_the_deposit_and_never_swaps_the_host():
    d, problems = schema.validate(_load("wedding-host"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("订金说成定金" in f for f in a.forbidden) and any("临时换人" in f for f in a.forbidden)
    assert any("难堪" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["婚礼司仪"]
    t = d.task_templates[0]
    assert "不超过总价二成" in t.description and "双倍返还" in t.description


@pytest.mark.parametrize("text,kind", [
    ("抖音刷粉一万", "fake_traffic"), ("买个十万粉的账号", "fake_traffic"), ("出租账号给你带货", "fake_traffic"),
    ("刷播放量", "fake_traffic"), ("收一个老帐号", "fake_traffic"), ("我不懂，帮我刷粉", "fake_traffic"),
    ("帮我卖号码", None), ("账号代运营，不刷粉不买量", None), ("帮我运营小红书，账号在我名下", None),
    ("帮我注册一个账号", None), ("不刷粉刷量、不买卖租借账号", None),
    # 否定判断放宽后，之前几轮的边界照旧
    ("不想自己写，代写毕业论文", "ghostwrite"), ("不代写学位论文、不写刷单好评", None), ("本店不刷单", None),
])
def test_what_the_traffic_guard_catches(text, kind):
    assert restricted_errand(text) == kind


def test_publishing_stops_fake_traffic_but_not_honest_account_operation(client, requester):
    r = _post(client, requester, title="涨粉", description="抖音刷粉一万，要快", category="账号代运营", is_remote=True)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "fake_traffic", r.text
    assert "账号代运营（账号在你名下）" in r.json()["detail"]["message"], "说清什么可以发"
    ok = _post(client, requester, title="小红书代运营", description="账号在我名下，每月 12 条", category="账号代运营", is_remote=True)
    assert ok.status_code in (200, 201), ok.text
    w = make_verified(client, "13600003621")
    assert client.post(f"{API}/tasks/{ok.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201
    host = _post(client, requester, title="婚礼司仪", description="十月婚礼", category="婚礼司仪")
    assert host.status_code in (200, 201), host.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("account-operation", "account-ops-helper", ("13900003621", "13900003622"), "客户要一个月涨一万粉", "不承诺涨多少粉，约定能做到的指标"),
    ("account-operation", "account-ops-helper", ("13900003623", "13900003624"), "账号注册在谁名下", "账号用客户的主体注册，停止合作时交还权限"),
    ("account-operation", "account-ops-helper", ("13900003625", "13900003626"), "能不能用群控", "不刷粉刷量、不买卖租借账号"),
    ("wedding-host", "wedding-host-helper", ("13900003627", "13900003628"), "订金和定金有什么区别", "写清「定金」还是「订金」"),
    ("wedding-host", "wedding-host-helper", ("13900003629", "13900003630"), "伴郎想搞婚闹", "不搞让人难堪的闹婚环节"),
    ("wedding-host", "wedding-host-helper", ("13900003631", "13900003632"), "那天有事能让朋友替班吗", "说好是谁就是谁上台"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
