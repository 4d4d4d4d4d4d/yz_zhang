"""SCN-235 / SCN-236 第二十九轮场景发掘：地推与发传单、汽车贴膜（345 号 spec，V372）。

两个数据文件、两个新类目（都不要资质）。地推：不乱贴、扫码注册让对方自己操作、不刷单凑数、结算口径写清；
贴膜：前挡透光率不低于 70%、品牌型号如实写、施工前后拍车况。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_street_promotion_pack_never_posts_illegally_or_fills_in_strangers_info():
    d, problems = schema.validate(_load("street-promotion"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("乱贴" in f for f in a.forbidden) and any("代填" in f for f in a.forbidden)
    assert any("刷单凑数" in f for f in a.forbidden) and any("老人或小孩" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["地推传单"]
    t = d.task_templates[0].description
    assert "不乱贴" in t and "不代填信息" in t and "「无效」的判法" in t


def test_car_film_pack_keeps_the_windshield_legal_and_the_brand_honest():
    d, problems = schema.validate(_load("car-window-film"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("透光率不达标" in f for f in a.forbidden) and any("冒充大牌" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["汽车贴膜"]
    t = d.task_templates[0]
    assert "不低于 70%" in t.description and "给车主看膜卷标识" in t.visit_checklist


@pytest.mark.parametrize("key", ["street-promotion", "car-window-film"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_orders_without_certificates(client, requester):
    w = make_verified(client, "13600003711")
    for cat, title in (("地推传单", "商场门口发传单"), ("汽车贴膜", "全车隔热膜")):
        t = _post(client, requester, title=title, description="周六全天", category=cat)
        assert t.status_code in (200, 201), t.text
        assert client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201
    fake = _post(client, requester, title="拉新", description="找亲戚朋友刷单凑注册数", category="地推传单")
    assert fake.status_code == 400 and fake.json()["detail"]["code"] == "fake_review", "刷单凑数照拦"


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("street-promotion", "street-promotion-helper", ("13900003791", "13900003792"), "商家让我往电线杆上贴", "不往墙上、电线杆、车窗上乱贴"),
    ("street-promotion", "street-promotion-helper", ("13900003793", "13900003794"), "能不能帮路人填身份证", "扫码注册让对方自己操作，不替人填信息"),
    ("street-promotion", "street-promotion-helper", ("13900003795", "13900003796"), "结账说注册无效不给钱", "什么算有效、怎么结算，写进单子；不刷单凑数"),
    ("street-promotion", "street-promotion-helper", ("13900003797", "13900003798"), "被保安赶走了", "商场门店门口发，先经场地方同意"),
    ("car-window-film", "car-film-helper", ("13900003799", "13900003800"), "客户要前挡贴最黑的", "前挡和驾驶员视区的膜，透光率不低于 70%"),
    ("car-window-film", "car-film-helper", ("13900003801", "13900003802"), "国产膜能说成大牌吗", "膜的品牌型号如实写，现场亮膜卷"),
    ("car-window-film", "car-film-helper", ("13900003803", "13900003804"), "贴完一周起泡了", "气泡、翘边怎么返工写清"),
    ("car-window-film", "car-film-helper", ("13900003805", "13900003806"), "施工把仪表台刮花了", "施工前拍车况，贴完拍效果"),
    # 只有标签里的口语才接得住（标题与正文里没有这个词）
    ("street-promotion", "street-promotion-helper", ("13900003807", "13900003808"), "大爷让我替他刷脸", "扫码注册让对方自己操作，不替人填信息"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
