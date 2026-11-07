"""SCN-227 / SCN-228 第二十六轮场景发掘：住院护工、家电上门维修（341 号 spec，V368）。

两个数据文件、两个新类目：「住院护工」要审核通过的医疗护理员培训合格证明；「家电维修」不要资质。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from app.modules.task.errand import restricted_errand
from app.modules.task.service import CAREGIVER_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_caregiver_pack_keeps_to_daily_care_and_never_handles_money():
    d, problems = schema.validate(_load("inpatient-caregiver"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("调输液" in f for f in a.forbidden) and any("私下加价" in f for f in a.forbidden)
    assert any("银行卡" in f for f in a.forbidden) and any("医疗建议" in f for f in a.forbidden)
    assert _categories()["住院护工"]["required_cert"] == CAREGIVER_CERT
    t = d.task_templates[0]
    assert "只做生活照护" in t.description and "床栏拉好" in t.visit_checklist


def test_appliance_repair_pack_quotes_first_and_hands_back_old_parts():
    d, problems = schema.validate(_load("appliance-repair"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("小毛病说成大毛病" in f for f in a.forbidden) and any("旧件冒充新件" in f for f in a.forbidden)
    assert "required_cert" not in _categories()["家电维修"]
    t = d.task_templates[0]
    assert "旧件交给我" in t.description and "上门费" in t.description
    assert "旧件交给客户并拍照" in t.visit_checklist


@pytest.mark.parametrize("key", ["inpatient-caregiver", "appliance-repair"])
def test_templates_do_not_trip_the_errand_guard(key):
    t = _load(key)["task_templates"][0]
    assert restricted_errand(f"{t['title']} {t['description']}") is None


def test_only_a_reviewed_caregiver_certificate_can_take_an_inpatient_job(client, requester):
    ops = make_admin(client, "13600003681", "运营")
    t = _post(client, requester, title="骨科术后陪护", description="24 小时，一对一，七天", category="住院护工").json()
    w = make_verified(client, "13600003682")
    no = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w))
    assert no.status_code == 400 and CAREGIVER_CERT in no.json()["detail"]["message"], no.text
    app_id = apply_cert(client, w, name=CAREGIVER_CERT, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "培训证明清晰，姓名一致"},
                       headers=auth(ops)).status_code == 200
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201
    fix = _post(client, requester, title="洗衣机不脱水", description="滚筒，用了五年", category="家电维修")
    assert fix.status_code in (200, 201), fix.text
    assert client.post(f"{API}/tasks/{fix.json()['id']}/applications", json={}, headers=auth(w)).status_code == 201


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("inpatient-caregiver", "caregiver-helper", ("13900003701", "13900003702"), "家属让我把输液调快点", "只做生活照护，医疗护理交给护士"),
    ("inpatient-caregiver", "caregiver-helper", ("13900003703", "13900003704"), "老人夜里自己下床怎么办", "防跌倒、防压疮"),
    ("inpatient-caregiver", "caregiver-helper", ("13900003705", "13900003706"), "家属给红包收不收", "价钱写进单子，不私下加价"),
    ("inpatient-caregiver", "caregiver-helper", ("13900003707", "13900003708"), "病人发烧了怎么办", "每一班记清楚，有异常马上叫护士"),
    ("appliance-repair", "appliance-repair-helper", ("13900003709", "13900003710"), "客户问换下来的零件呢", "换下的旧件当面给客户看、交给客户"),
    ("appliance-repair", "appliance-repair-helper", ("13900003711", "13900003712"), "能不能用拆机件", "配件写清原厂、通用还是拆机件"),
    ("appliance-repair", "appliance-repair-helper", ("13900003713", "13900003714"), "修完三天又坏了", "修理部位保修多久写清，开收据"),
    ("appliance-repair", "appliance-repair-helper", ("13900003715", "13900003716"), "上门费要提前说吗", "上门费、检测费事先说清"),
    # 只有标签里的口语才接得住（标题与正文里没有这些词）
    ("inpatient-caregiver", "caregiver-helper", ("13900003717", "13900003718"), "能不能帮他滴快点", "只做生活照护，医疗护理交给护士"),
    ("appliance-repair", "appliance-repair-helper", ("13900003719", "13900003720"), "客户说被掉包了", "换下的旧件当面给客户看、交给客户"),
    ("appliance-repair", "appliance-repair-helper", ("13900003721", "13900003722"), "给我换的是副厂的吧", "配件写清原厂、通用还是拆机件"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]], r.get("answer"))
