"""SCN-239 / SCN-240 第三十一轮场景发掘：上门保健按摩、家庭网络与智能家居调试（347 号 spec，V374）。

两个数据文件、两个新类目（都不要资质）。按摩：只做保健、不正骨不针灸、这几种情况不按、不说能治病；
网络：账号在客户名下、默认密码全改、不装破解直播源、不碰客户的数据。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_massage_pack_stays_wellness_only():
    d, problems = schema.validate(_load("home-massage"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("正骨" in f for f in a.forbidden) and any("能治病" in f for f in a.forbidden)
    assert any("孕妇腰腹" in f for f in a.forbidden) and any("约定以外" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["上门按摩"]
    t = d.task_templates[0]
    assert "不做正骨、针灸、放血" in t.description and "当面再确认身体情况" in t.visit_checklist


def test_network_pack_keeps_accounts_with_the_client_and_no_cracked_sources():
    d, problems = schema.validate(_load("home-network-setup"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("自己的手机号" in f for f in a.forbidden) and any("默认密码" in f for f in a.forbidden)
    assert any("破解直播源" in f for f in a.forbidden) and any("手机电脑" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["网络与智能家居"]
    t = d.task_templates[0]
    assert "账号用我的手机号注册" in t.description and "默认密码全改" in t.visit_checklist


@pytest.mark.parametrize("key", ["home-massage", "home-network-setup"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_orders_without_certificates(client, requester):
    w = make_verified(client, "13600003731")
    for cat, title in (("上门按摩", "肩颈放松一小时"), ("网络与智能家居", "全屋 Mesh 组网")):
        t = _post(client, requester, title=title, description="周六下午", category=cat)
        assert t.status_code in (200, 201), t.text
        assert client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("home-massage", "home-massage-helper", ("13900003841", "13900003842"), "客户让我帮他正一下骨", "只做保健按摩，不正骨不针灸"),
    ("home-massage", "home-massage-helper", ("13900003843", "13900003844"), "孕妇能按吗", "这几种情况不按"),
    ("home-massage", "home-massage-helper", ("13900003845", "13900003846"), "能不能说按摩治失眠", "不说按摩能治什么病"),
    ("home-massage", "home-massage-helper", ("13900003847", "13900003848"), "客户提出不舒服的要求怎么办", "只做约定的项目，边界清楚"),
    ("home-network-setup", "home-network-helper", ("13900003849", "13900003850"), "用我的手机号绑客户的门锁行吗", "所有账号用客户的手机号注册"),
    ("home-network-setup", "home-network-helper", ("13900003851", "13900003852"), "路由器还是admin要改吗", "默认密码一律改掉，当面交给客户"),
    ("home-network-setup", "home-network-helper", ("13900003853", "13900003854"), "客户想在电视盒子上免费看直播", "不装破解直播源、盗版软件"),
    ("home-network-setup", "home-network-helper", ("13900003855", "13900003856"), "租的房子能打孔走线吗", "打孔走线先问物业和房东"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("home-massage", "home-massage-helper", ("13900003857", "13900003858"), "腰椎间盘突出能按好吗", "只做保健按摩，不正骨不针灸"),
    ("home-massage", "home-massage-helper", ("13900003859", "13900003860"), "跟客户讲疗效行吗", "不说按摩能治什么病"),
    ("home-massage", "home-massage-helper", ("13900003861", "13900003862"), "客户要特殊服务", "只做约定的项目，边界清楚"),
    ("home-network-setup", "home-network-helper", ("13900003863", "13900003864"), "能挂我的号上吗", "所有账号用客户的手机号注册"),
    ("home-network-setup", "home-network-helper", ("13900003865", "13900003866"), "admin行不行", "默认密码一律改掉，当面交给客户"),
    ("home-network-setup", "home-network-helper", ("13900003867", "13900003868"), "客户想看球", "不装破解直播源、盗版软件"),
    ("home-network-setup", "home-network-helper", ("13900003869", "13900003870"), "怕被扣押金", "打孔走线先问物业和房东"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
