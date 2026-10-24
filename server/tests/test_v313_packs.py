"""SCN-159 / SCN-160 第九轮场景发掘：教老人用手机、家电清洗（286 号 spec，V313）。

交付物是两个数据文件 + 「空调外机拆装（高处作业）」类目要高处作业操作证（高处作业属特种作业，持证上岗）。
"""
from datetime import timedelta

import pytest

from app.modules.account.models import utcnow
from app.modules.packs import schema
from tests.conftest import auth
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_v286_packs import _categories, _load, _publish

API = "/api/v1"


def test_elder_phone_pack_never_touches_passwords_or_money():
    d, problems = schema.validate(_load("elder-phone-teaching"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert {"money", "publish", "share_personal"} <= set(a.human_gates)
    assert any("密码" in f for f in a.forbidden) and any("转账" in f for f in a.forbidden)
    assert a.fallback_category == "助老陪伴" and "助老陪伴" in _categories()
    assert {t.category for t in d.task_templates} == {"助老陪伴"}
    assert all(t.visits_planned >= 1 and t.visit_checklist for t in d.task_templates), "按次上课、逐项回报给子女"


def test_appliance_pack_and_outdoor_category_need_a_height_work_certificate():
    d, problems = schema.validate(_load("home-appliance-cleaning"))
    assert d is not None and not problems, problems
    a = d.assistants[0]
    assert any("高处作业证" in f for f in a.forbidden) and any("带电" in f for f in a.forbidden)
    cats = _categories()
    assert "required_cert" not in cats["家电清洗"], "室内清洗不要证书"
    assert cats["空调外机拆装（高处作业）"].get("required_cert") == "高处作业操作证"
    assert {t.category for t in d.task_templates} == {"家电清洗", "空调外机拆装（高处作业）"}


def test_only_certified_workers_can_take_outdoor_units(client, requester):
    t = _post(client, requester, title="窗外空调外机清洗", description="五楼窗外", category="空调外机拆装（高处作业）").json()
    worker = make_verified(client, "13600003131")
    r = client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "高处作业操作证" in r.json()["detail"]["message"]
    indoor = _post(client, requester, title="两台挂机清洗", description="室内机", category="家电清洗").json()
    assert client.post(f"{API}/tasks/{indoor['id']}/applications", json={}, headers=auth(worker)).status_code == 201


def test_height_work_certificate_must_carry_an_expiry_within_six_years(client):
    worker = make_verified(client, "13600003132")
    r = apply_cert(client, worker, name="高处作业操作证", expires_at=None)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_required"
    assert "高处作业操作证" in r.json()["detail"]["message"]
    r = apply_cert(client, worker, name="高处作业操作证", expires_at=(utcnow() + timedelta(days=366 * 6 + 2)).isoformat())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_too_far"
    ok = apply_cert(client, worker, name="高处作业操作证", expires_at=(utcnow() + timedelta(days=365 * 5)).isoformat())
    assert ok.status_code == 201, ok.text


@pytest.mark.parametrize("key,assistant,phones,q,title", [
    ("elder-phone-teaching", "elder-phone-tutor-helper", ("13900003131", "13900003132"), "老人把支付密码告诉我怎么办", "密码、验证码、付款：只让老人自己输"),
    ("elder-phone-teaching", "elder-phone-tutor-helper", ("13900003133", "13900003134"), "怎么教老人防诈骗", "防诈骗：三句话教给老人"),
    ("home-appliance-cleaning", "appliance-cleaning-helper", ("13900003135", "13900003136"), "空调外机要高处作业证吗", "空调外机：2 米以上、出窗作业要高处作业证"),
    ("home-appliance-cleaning", "appliance-cleaning-helper", ("13900003137", "13900003138"), "客户要加氟怎么收费", "加氟、换配件：先说、走变更单"),
])
def test_the_assistants_answer_the_questions_that_matter_most(client, requester, key, assistant, phones, q, title):
    _publish(client, key, phones)
    r = client.post(f"{API}/packs/{key}/assistants/{assistant}/ask", json={"q": q}, headers=auth(requester)).json()
    assert any(c["title"] == title for c in r["citations"]), (q, [c["title"] for c in r["citations"]])
