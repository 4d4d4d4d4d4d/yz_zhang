"""SCN-241 / SCN-242 第三十二轮场景发掘：开荒保洁、二手车陪验（349 号 spec，V376）。

两个数据文件、两个新类目（都不要资质）。开荒：高层外窗不探身（外侧另发高处作业单）、清洁剂先试、开工前拍照、
装修垃圾另算；陪验：只替买家看不收回扣、查记录核车架号、看泡水火烧事故与调表、报告只写看到的。
"""
import pytest

from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from tests.conftest import auth
from tests.test_certification import make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_reno_cleaning_pack_never_leans_out_and_tests_cleaners_first():
    d, problems = schema.validate(_load("post-renovation-cleaning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("探身出窗" in f for f in a.forbidden) and any("强酸强碱" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["开荒保洁"]
    t = d.task_templates[0]
    assert "外窗只擦室内够得到的" in t.description and "开工前每个房间拍一圈" in t.visit_checklist


def test_used_car_pack_works_for_the_buyer_only():
    d, problems = schema.validate(_load("used-car-inspection"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("回扣" in f for f in a.forbidden) and any("打包票" in f for f in a.forbidden)
    assert any("里程表" in f for f in a.forbidden) and any("定金" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["二手车陪验"]
    assert "看不到的写「未检查」" in d.task_templates[0].description


@pytest.mark.parametrize("key", ["post-renovation-cleaning", "used-car-inspection"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_orders_without_certificates(client, requester):
    w = make_verified(client, "13600003771")
    for cat, title in (("开荒保洁", "新房开荒九十平"), ("二手车陪验", "陪看一台五年的轿车")):
        t = _post(client, requester, title=title, description="周六上午", category=cat)
        assert t.status_code in (200, 201), t.text
        assert client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("post-renovation-cleaning", "reno-cleaning-helper", ("13900003871", "13900003872"), "十八楼的外窗外面要擦吗", "高层外窗不探身，外侧另发高处作业单"),
    ("post-renovation-cleaning", "reno-cleaning-helper", ("13900003873", "13900003874"), "大理石台面上的水泥渍用什么洗", "清洁剂先在不起眼处试，石材木材不用强酸强碱"),
    ("post-renovation-cleaning", "reno-cleaning-helper", ("13900003875", "13900003876"), "客户说地板是我们划的", "开工前每个房间拍一圈"),
    ("post-renovation-cleaning", "reno-cleaning-helper", ("13900003877", "13900003878"), "一屋子砖头要帮着扔吗", "装修垃圾清运不在开荒范围，要的话另算"),
    ("used-car-inspection", "used-car-helper", ("13900003879", "13900003880"), "车商说给我介绍费", "只替买家看，不收卖家或车商的回扣"),
    ("used-car-inspection", "used-car-helper", ("13900003881", "13900003882"), "怎么看是不是泡水车", "看泡水、火烧、重大事故的痕迹"),
    ("used-car-inspection", "used-car-helper", ("13900003883", "13900003884"), "怀疑公里数不对", "核对里程，警惕调表"),
    ("used-car-inspection", "used-car-helper", ("13900003885", "13900003886"), "报告能写车况良好吗", "报告只写看到的，看不到的写「未检查」"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("post-renovation-cleaning", "reno-cleaning-helper", ("13900003887", "13900003888"), "能用洁厕灵刷台面吗", "清洁剂先在不起眼处试，石材木材不用强酸强碱"),
    ("post-renovation-cleaning", "reno-cleaning-helper", ("13900003889", "13900003890"), "业主硬说是你弄的", "开工前每个房间拍一圈"),
    ("used-car-inspection", "used-car-helper", ("13900003891", "13900003892"), "卖家让我帮着说好话", "只替买家看，不收卖家或车商的回扣"),
    ("used-car-inspection", "used-car-helper", ("13900003893", "13900003894"), "买家让我保证没问题", "报告只写看到的，看不到的写「未检查」"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
