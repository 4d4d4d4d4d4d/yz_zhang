"""SCN-144 服务对象是未成年人的单：监护人关口与无犯罪记录证明（214 号 spec，V242）。

依据与关口见 212 号 spec（G2、G3）：发单人确认是监护人或经监护人同意，选「监护人在场」或「公开场所」，
不允许单独相处的安排；接这类单（以及「陪练看护」类目）要持有平台审核通过、在有效期内的无犯罪记录证明。
"""
from datetime import timedelta

from app.modules.account.models import utcnow
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post

API = "/api/v1/tasks"
MINOR = {"minor_involved": True, "guardian_mode": "guardian_present", "guardian_consented": True}


def _approved(client, worker, admin_phone):
    app_id = apply_cert(client, worker, name="无犯罪记录证明", issuer="上海市公安局某派出所").json()["id"]
    admin = make_admin(client, admin_phone)
    r = client.post(f"/api/v1/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证明清晰，姓名一致"},
                    headers=auth(admin))
    assert r.status_code == 200, r.text


def test_publishing_a_minor_task_needs_guardian_consent_and_a_safe_setting(client, requester):
    base = {"title": "孩子钢琴陪练", "description": "每周六下午一小时"}
    for extra, code in [({"minor_involved": True, "guardian_consented": True}, "minor_needs_guardian_mode"),
                        ({"minor_involved": True, "guardian_mode": "alone", "guardian_consented": True}, "minor_needs_guardian_mode"),
                        ({"minor_involved": True, "guardian_mode": "public_place"}, "guardian_required"),
                        ({"guardian_mode": "public_place"}, "guardian_without_minor")]:
        r = _post(client, requester, **base, **extra)
        assert r.status_code == 400 and r.json()["detail"]["code"] == code, extra
    r = _post(client, requester, **base, **MINOR)
    assert r.status_code in (200, 201), r.text
    t = r.json()
    assert (t["minor_involved"], t["guardian_mode"]) == (True, "guardian_present")
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(t, "Task")
    from app.core.db import SessionLocal
    from app.modules.task.models import Task

    with SessionLocal() as db:
        assert db.get(Task, t["id"]).guardian_consent_at is not None, "记下监护人确认的时间"


def test_only_people_with_an_approved_record_check_can_apply(client, requester):
    t = _post(client, requester, title="孩子钢琴陪练", description="每周六下午", **MINOR).json()
    worker = make_verified(client, "13600002421")
    r = client.post(f"{API}/{t['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required"
    assert "无犯罪记录证明" in r.json()["detail"]["message"]
    _approved(client, worker, "13600002422")
    assert client.post(f"{API}/{t['id']}/applications", json={}, headers=auth(worker)).status_code == 201
    plain = _post(client, requester, title="周末帮忙搬家", description="两个小时").json()
    other = make_verified(client, "13600002423")
    assert client.post(f"{API}/{plain['id']}/applications", json={}, headers=auth(other)).status_code == 201, "别的单不受影响"


def test_care_category_requires_the_record_check_and_slots_inherit_the_flag(client, requester):
    t = _post(client, requester, title="周末看护", description="公园里陪孩子玩", category="陪练看护", people_needed=2,
              **{**MINOR, "guardian_mode": "public_place"}).json()
    slot = t["slots"][0]
    assert slot["minor_involved"] is True and slot["guardian_mode"] == "public_place", "名额继承"
    worker = make_verified(client, "13600002424")
    r = client.post(f"{API}/{slot['id']}/applications", json={}, headers=auth(worker))
    assert r.json()["detail"]["code"] == "certification_required"


def test_record_check_certificate_must_carry_an_expiry_within_a_year(client):
    worker = make_verified(client, "13600002425")
    r = apply_cert(client, worker, name="无犯罪记录证明", expires_at=None)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_required"
    r = apply_cert(client, worker, name="无犯罪记录证明", expires_at=(utcnow() + timedelta(days=400)).isoformat())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certificate_expiry_too_far"
    assert apply_cert(client, worker, name="无犯罪记录证明").status_code == 201


def test_the_care_category_needs_the_record_check_even_without_the_flag(client, requester):
    t = _post(client, requester, title="成人羽毛球陪练", description="周末两小时", category="陪练看护").json()
    worker = make_verified(client, "13600002426")
    r = client.post(f"{API}/{t['id']}/applications", json={}, headers=auth(worker))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "certification_required", "类目本身就要这份证明"
