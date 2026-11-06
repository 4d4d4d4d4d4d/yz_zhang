"""SCN-302 / SCN-303 第六十一轮场景发掘：庭院绿化养护、高空外窗外墙清洗（415 号 spec，V442）。

- 「庭院绿化养护」不要资质：报价按面积次数写清、打药按标签说清药名并避开孩子宠物（农药管理条例）、
  电锯修剪戴护具不碰电线、枝叶清走不焚烧（大气污染防治法）、公共绿地和别人的树不擅自砍（城市绿化条例）；
- 「高空外窗外墙清洗」要审核通过的高处作业操作证（安全生产法第三十条，特种作业持证上岗）：
  工作绳安全绳分开挂并检查、楼下警戒、六级以上大风停工（JGJ 80）、清洁剂不腐蚀控制滴水、买意外险。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091）离线试过。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import HEIGHT_WORK_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_garden_pack_sprays_by_label_and_keeps_to_its_own_yard():
    d, problems = schema.validate(_load("garden-care"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("超量打药" in f for f in a.forbidden) and any("靠近电线" in f for f in a.forbidden)
    assert any("焚烧" in f for f in a.forbidden) and any("公共绿地" in f for f in a.forbidden)
    assert any("写清次数" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["庭院绿化养护"]
    t = d.task_templates[0].description
    assert "按标签用量" in t and "不焚烧" in t and "公共绿地不动" in t


def test_high_rise_pack_needs_a_certified_worker_on_two_ropes():
    d, problems = schema.validate(_load("high-rise-cleaning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("没有高处作业证" in f for f in a.forbidden) and any("一根绳" in f for f in a.forbidden)
    assert any("警戒区" in f for f in a.forbidden) and any("大风雨天" in f for f in a.forbidden)
    assert any("腐蚀性" in f for f in a.forbidden)
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert _categories()["高空外窗外墙清洗"]["required_cert"] == HEIGHT_WORK_CERT
    t = d.task_templates[0].description
    assert "高处作业操作证" in t and "安全绳分开挂" in t and "大风" in t


@pytest.mark.parametrize("key", ["garden-care", "high-rise-cleaning"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_height_worker_can_take_the_high_rise_job(client, requester):
    ops = make_admin(client, "13600044201", "运营")
    t = _post(client, requester, title="18 楼外窗清洗", description="三室两厅外窗", category="高空外窗外墙清洗").json()
    w = make_verified(client, "13600044202")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and HEIGHT_WORK_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=HEIGHT_WORK_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    garden = _post(client, requester, title="院子每月修剪四次", description="五十平米草坪", category="庭院绿化养护").json()
    other = make_verified(client, "13600044203")
    assert client.post(f"{API}/tasks/{garden['id']}/applications", json={}, headers=auth(other)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("garden-care", "garden-care-helper", ("13700442001", "13700442002"), "报价怎么写", "报价按面积和次数写清，换季加活先报价"),
    ("garden-care", "garden-care-helper", ("13700442003", "13700442004"), "打药前要告诉谁", "打药先说药名和用途，按标签用量，避开孩子宠物"),
    ("garden-care", "garden-care-helper", ("13700442005", "13700442006"), "用电锯要戴什么", "电锯绿篱机修剪戴护具，靠近电线的树枝不自己剪"),
    ("garden-care", "garden-care-helper", ("13700442007", "13700442008"), "剪下来的枝叶怎么处理", "修剪下来的枝叶清走，按当地规定处理，不焚烧"),
    ("garden-care", "garden-care-helper", ("13700442009", "13700442010"), "小区绿地的树能剪吗", "只打理委托人自己的院子，公共绿地和别人的树不动"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442011", "13700442012"), "要什么证", "持审核通过的高处作业操作证上岗"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442013", "13700442014"), "绳子怎么挂", "工作绳安全绳分开挂在牢靠挂点，开工前检查"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442015", "13700442016"), "要拉警戒线吗", "楼下拉警戒区有人看护，六级以上大风雨雪雾停工"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442017", "13700442018"), "清洁剂怎么选", "清洁剂选不腐蚀的，控制滴水不伤行人和车"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442019", "13700442020"), "要买保险吗", "按面积楼层报价，给作业的人买意外险，不赶工"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("garden-care", "garden-care-helper", ("13700442021", "13700442022"), "下雨不来", "报价按面积和次数写清，换季加活先报价"),
    ("garden-care", "garden-care-helper", ("13700442023", "13700442024"), "起了一身疹子", "打药先说药名和用途，按标签用量，避开孩子宠物"),
    ("garden-care", "garden-care-helper", ("13700442025", "13700442026"), "跳闸", "电锯绿篱机修剪戴护具，靠近电线的树枝不自己剪"),
    ("garden-care", "garden-care-helper", ("13700442027", "13700442028"), "被邻居投诉", "修剪下来的枝叶清走，按当地规定处理，不焚烧"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442029", "13700442030"), "临时工", "持审核通过的高处作业操作证上岗"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442031", "13700442032"), "快磨断", "工作绳安全绳分开挂在牢靠挂点，开工前检查"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442033", "13700442034"), "被吹得撞墙", "楼下拉警戒区有人看护，六级以上大风雨雪雾停工"),
    ("high-rise-cleaning", "high-rise-cleaning-helper", ("13700442035", "13700442036"), "工伤", "按面积楼层报价，给作业的人买意外险，不赶工"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
