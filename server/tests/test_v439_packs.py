"""SCN-300 / SCN-301 第六十轮场景发掘：团建活动执行、寻宠服务（412 号 spec，V439）。

两个新类目都不要资质：
- 「团建活动执行」：人均预算逐项列不加隐形消费（消保法第二十条）、户外看场地安全买团体意外险
  （民法典第一千一百九十八条，群众性活动组织者的安全保障义务）、备雨天方案写清改期规则、
  人数名单车辆逐一核对、活动自愿不劝酒；
- 「寻宠服务」：分阶段收费写清找不到怎么算（消保法第五十二条）、按范围搜索每天回报、
  启事贴在允许的地方用虚拟号、不藏宠索钱不诱捕别人的宠物（民法典第三百一十四条）、交接先核对。
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


def test_team_building_pack_is_transparent_and_insured():
    d, problems = schema.validate(_load("team-building"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("隐形消费" in f for f in a.forbidden) and any("不买保险" in f for f in a.forbidden)
    assert any("雨天备案" in f for f in a.forbidden) and any("不核对人数" in f for f in a.forbidden)
    assert any("劝酒" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["团建活动执行"]
    t = d.task_templates[0].description
    assert "逐项列" in t and "团体意外险" in t and "不劝酒" in t


def test_pet_finder_pack_charges_in_stages_and_never_holds_pets_hostage():
    d, problems = schema.validate(_load("pet-finder"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("先收全款" in f for f in a.forbidden) and any("不回报" in f for f in a.forbidden)
    assert any("乱贴小广告" in f for f in a.forbidden) and any("藏起宠物" in f for f in a.forbidden)
    assert any("不核对就交接" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["寻宠服务"]
    t = d.task_templates[0].description
    assert "分阶段收费" in t and "虚拟号" in t and "核对特征" in t


@pytest.mark.parametrize("key", ["team-building", "pet-finder"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_both_categories_take_applications_without_a_certificate(client, requester):
    w = make_verified(client, "13600043901")
    for title, cat in (("部门五十人周六郊外团建", "团建活动执行"), ("家里的橘猫昨晚跑丢了", "寻宠服务")):
        t = _post(client, requester, title=title, description="本周", category=cat)
        assert t.status_code in (200, 201), t.text
        r = client.post(f"{API}/tasks/{t.json()['id']}/applications", json={}, headers=auth(w))
        assert r.status_code == 201, r.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("team-building", "team-building-helper", ("13700439001", "13700439002"), "报价要逐项列吗", "人均预算逐项列，场地餐饮交通保险分开写，不加隐形消费"),
    ("team-building", "team-building-helper", ("13700439003", "13700439004"), "要买保险吗", "户外项目先看场地安全，买团体意外险，高风险项目不安排"),
    ("team-building", "team-building-helper", ("13700439005", "13700439006"), "天气不好要改期吗", "提前看天气，备室内方案，改期和取消怎么算写清"),
    ("team-building", "team-building-helper", ("13700439007", "13700439008"), "返程前要点名吗", "人数名单车辆逐一核对，集合点和返程时间写明"),
    ("team-building", "team-building-helper", ("13700439009", "13700439010"), "晚宴能劝酒吗", "活动自愿、不劝酒，不安排让人难堪的环节"),
    ("pet-finder", "pet-finder-helper", ("13700439011", "13700439012"), "定金怎么收", "不先收全款，按阶段收，找不到怎么算事先写清"),
    ("pet-finder", "pet-finder-helper", ("13700439013", "13700439014"), "每天要回报吗", "先问清走失的时间地点特征，按范围搜索，每天回报进展"),
    ("pet-finder", "pet-finder-helper", ("13700439015", "13700439016"), "寻宠启事贴在哪", "启事贴在允许的地方，主人号码尽量用虚拟号"),
    ("pet-finder", "pet-finder-helper", ("13700439017", "13700439018"), "能用诱捕笼吗", "不藏起宠物向主人要钱，不诱捕别人家的宠物"),
    ("pet-finder", "pet-finder-helper", ("13700439019", "13700439020"), "找到后怎么交接", "找到后核对特征和主人身份再交接，受伤的先看"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("team-building", "team-building-helper", ("13700439021", "13700439022"), "又加了", "人均预算逐项列，场地餐饮交通保险分开写，不加隐形消费"),
    ("team-building", "team-building-helper", ("13700439023", "13700439024"), "崴了脚", "户外项目先看场地安全，买团体意外险，高风险项目不安排"),
    ("team-building", "team-building-helper", ("13700439025", "13700439026"), "泡汤", "提前看天气，备室内方案，改期和取消怎么算写清"),
    ("team-building", "team-building-helper", ("13700439027", "13700439028"), "开出去", "人数名单车辆逐一核对，集合点和返程时间写明"),
    ("pet-finder", "pet-finder-helper", ("13700439029", "13700439030"), "一千块", "不先收全款，按阶段收，找不到怎么算事先写清"),
    ("pet-finder", "pet-finder-helper", ("13700439031", "13700439032"), "被罚款", "启事贴在允许的地方，主人号码尽量用虚拟号"),
    ("pet-finder", "pet-finder-helper", ("13700439033", "13700439034"), "抓错", "不藏起宠物向主人要钱，不诱捕别人家的宠物"),
    ("pet-finder", "pet-finder-helper", ("13700439035", "13700439036"), "冒领", "找到后核对特征和主人身份再交接，受伤的先看"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
