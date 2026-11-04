"""SCN-288 / SCN-289 第五十四轮场景发掘：空调加氟维修、数据分析报告（397 号 spec，V424）。

- 「空调加氟维修」要审核通过的制冷与空调作业操作证（特种作业，同高处作业、低压电工一条规则：有效期必填最长 6 年、高风险全抽）；
  先找漏点再加、不混加冷媒、计量写清、外机在高处不探身、大件先报价；
- 「数据分析报告」不要资质：先问清问题、来源授权与脱敏、不挑数据写清局限、可复现、不代做课程作业和学位论文。
问法写测试之前都先用 scripts/pack_probe.py（PACK-091）离线试过。
"""
from datetime import timedelta

import pytest

from app.modules.account import cert_spot
from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import REFRIGERATION_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_refrigerant_pack_needs_a_certified_worker_and_finds_the_leak_first():
    d, problems = schema.validate(_load("ac-refrigerant"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("没有操作证" in f for f in a.forbidden) and any("不找漏点" in f for f in a.forbidden)
    assert any("混加" in f for f in a.forbidden) and any("按瓶" in f for f in a.forbidden)
    assert any("探身窗外" in f for f in a.forbidden) and any("换整机" in f for f in a.forbidden)
    assert _categories()["空调加氟维修"]["required_cert"] == REFRIGERATION_CERT
    assert REFRIGERATION_CERT in cert_spot.high_risk_certs()
    t = d.task_templates[0].description
    assert "先测压力找漏点" in t and "不混加冷媒" in t and "拍压力表" in t


def test_analysis_pack_stays_honest_and_refuses_coursework():
    d, problems = schema.validate(_load("data-analysis-report"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("挑数据" in f for f in a.forbidden) and any("相关说成因果" in f for f in a.forbidden)
    assert any("未脱敏" in f for f in a.forbidden) and any("学位论文" in f for f in a.forbidden)
    assert any("处理步骤" in f for f in a.forbidden)
    assert {"money", "publish", "sign", "share_personal"} <= set(a.human_gates)
    assert "required_cert" not in _categories()["数据分析报告"]
    t = d.task_templates[0].description
    assert "已脱敏" in t and "相关不说成因果" in t and "可重算" in t


@pytest.mark.parametrize("key", ["ac-refrigerant", "data-analysis-report"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_refrigeration_cert_follows_the_special_operation_rule(client):
    """有效期必填、最长 6 年：与高处作业、低压电工作业操作证同一条（286 / 325 号）。"""
    w = make_verified(client, "13600042401")
    r = apply_cert(client, w, name=REFRIGERATION_CERT, expires_at=None)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_required", r.text
    r = apply_cert(client, w, name=REFRIGERATION_CERT, expires_at=(utcnow() + timedelta(days=366 * 7)).isoformat())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_too_far", r.text


def test_only_a_reviewed_refrigeration_worker_can_take_the_job(client, requester):
    ops = make_admin(client, "13600042402", "运营")
    t = _post(client, requester, title="空调不制冷要加氟", description="挂机，用了六年", category="空调加氟维修").json()
    w = make_verified(client, "13600042403")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and REFRIGERATION_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=REFRIGERATION_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件可查"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    report = _post(client, requester, title="分析上季度复购", description="三千条订单", category="数据分析报告")
    assert report.status_code in (200, 201), report.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005901", "13900005902"), "加氟要什么证", "制冷与空调作业属特种作业，持操作证上岗"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005903", "13900005904"), "加氟前要找漏点吗", "先找漏点再加氟，不是一缺就加"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005905", "13900005906"), "冷媒能混加吗", "认清铭牌上的冷媒型号，不混加；R32 不见明火"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005907", "13900005908"), "加氟怎么收费", "按压力或称重加，写清加了多少，拍压力表"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005909", "13900005910"), "压缩机坏了要换整机吗", "外机在高处的不探身；换大件先报价、客户同意再做"),
    ("data-analysis-report", "data-analysis-helper", ("13900005911", "13900005912"), "开工前先问什么", "先问清要回答什么问题，再动手"),
    ("data-analysis-report", "data-analysis-helper", ("13900005913", "13900005914"), "数据要脱敏吗", "数据来源和授权写清，含个人信息的先脱敏"),
    ("data-analysis-report", "data-analysis-helper", ("13900005915", "13900005916"), "能删数据吗", "不挑数据、不改结论，相关不说成因果，写清局限"),
    ("data-analysis-report", "data-analysis-helper", ("13900005917", "13900005918"), "要交处理步骤吗", "附上处理步骤和表格或代码，对方能重算出同样的数"),
    ("data-analysis-report", "data-analysis-helper", ("13900005919", "13900005920"), "能代做毕业论文的数据分析吗", "不代做学生的课程作业和学位论文的数据分析"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005921", "13900005922"), "没证能接吗", "制冷与空调作业属特种作业，持操作证上岗"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005923", "13900005924"), "反复加", "先找漏点再加氟，不是一缺就加"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005925", "13900005926"), "加错了", "认清铭牌上的冷媒型号，不混加；R32 不见明火"),
    ("ac-refrigerant", "ac-refrigerant-helper", ("13900005927", "13900005928"), "换新机", "外机在高处的不探身；换大件先报价、客户同意再做"),
    ("data-analysis-report", "data-analysis-helper", ("13900005929", "13900005930"), "一堆图", "先问清要回答什么问题，再动手"),
    ("data-analysis-report", "data-analysis-helper", ("13900005931", "13900005932"), "发进群", "数据来源和授权写清，含个人信息的先脱敏"),
    ("data-analysis-report", "data-analysis-helper", ("13900005933", "13900005934"), "过节", "不挑数据、不改结论，相关不说成因果，写清局限"),
    ("data-analysis-report", "data-analysis-helper", ("13900005935", "13900005936"), "换人接手", "附上处理步骤和表格或代码，对方能重算出同样的数"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
