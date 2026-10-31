"""CERT-053 资质审核抽检（348 号 spec，V375）。

资质一核准就生效，准入只看一个审核员的判断。核准后抽检：和人身安全、未成年人有关的资质全部抽，其他按比例抽，
交另一位合规审核员复看：维持就结束，推翻就撤销资质、通知持证人。原审核员不能复看自己的；每位审核员被抽多少、
被推翻多少一起给出。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account import cert_spot
from app.modules.account.models import utcnow
from app.modules.admin.models import AdminAudit
from app.modules.notification.models import Notification
from app.modules.task.service import DRIVER_CERT
from tests.conftest import auth
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"
S = f"{API}/admin/cert-spot-checks"


def _approve(client, reviewer, w, name):
    app_id = apply_cert(client, w, name=name, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    r = client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件清晰"},
                    headers=auth(reviewer))
    assert r.status_code == 200, r.text
    return app_id


def test_high_risk_certs_are_always_sampled_and_a_second_reviewer_confirms(client, monkeypatch):
    from tests.test_client_shape_alignment import _assert_shape

    monkeypatch.setattr(cert_spot, "SPOT_CHECK_RATE", 0.0)
    a, b = _admin(client, "13600003751", ["compliance"]), _admin(client, "13600003752", ["compliance"])
    w = make_verified(client, "13600003753")
    app_id = _approve(client, a, w, DRIVER_CERT)
    _approve(client, a, make_verified(client, "13600003754"), "健身教练证")      # 不是高风险、比例为 0：不抽
    listed = client.get(S, headers=auth(b))
    assert listed.status_code == 200, listed.text
    _assert_shape(listed.json(), "CertSpotCheckList")
    items = listed.json()["items"]
    assert [(x["application_id"], x["reason"]) for x in items] == [(app_id, "high_risk")]
    _assert_shape(items[0], "CertSpotCheckItem")
    sid = items[0]["id"]
    me = client.post(f"{S}/{sid}/confirm", json={}, headers=auth(a))
    assert me.status_code == 403 and me.json()["detail"]["code"] == "cert_spot_self", "不能复看自己审的"
    ok = client.post(f"{S}/{sid}/confirm", json={"note": "证号可查"}, headers=auth(b))
    assert ok.status_code == 200 and ok.json()["status"] == "confirmed" and ok.json()["checked_by"] == b["id"]
    _assert_shape(ok.json(), "CertSpotCheckItem")
    again = client.post(f"{S}/{sid}/overturn", json={"note": "改主意了的理由"}, headers=auth(b))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "cert_spot_decided"
    with SessionLocal() as db:
        assert db.query(AdminAudit).filter(AdminAudit.action == "cert_spot_confirm").count() == 1


def test_overturn_revokes_the_certificate_and_tells_the_holder(client, requester, monkeypatch):
    monkeypatch.setattr(cert_spot, "SPOT_CHECK_RATE", 0.0)
    a, b = _admin(client, "13600003755", ["compliance"]), _admin(client, "13600003756", ["compliance"])
    w = make_verified(client, "13600003757")
    _approve(client, a, w, DRIVER_CERT)
    t = _post(client, requester, title="代驾", description="饭店到小区", category="代驾").json()
    assert client.post(f"{API}/tasks/{t['id']}/applications", json={}, headers=auth(w)).status_code == 201, "核准即生效"
    sid = client.get(S, headers=auth(b)).json()["items"][0]["id"]
    short = client.post(f"{S}/{sid}/overturn", json={"note": "假"}, headers=auth(b))
    assert short.status_code == 400 and short.json()["detail"]["code"] == "cert_spot_reason_required"
    r = client.post(f"{S}/{sid}/overturn", json={"note": "证号在交管系统查不到"}, headers=auth(b))
    assert r.status_code == 200 and r.json()["status"] == "overturned"
    t2 = _post(client, requester, title="代驾二", description="机场到家", category="代驾").json()
    assert client.post(f"{API}/tasks/{t2['id']}/applications", json={}, headers=auth(w)).status_code == 400, "推翻后资质立刻撤销"
    with SessionLocal() as db:
        titles = [n.title for n in db.query(Notification).filter(Notification.user_id == w["id"])]
        assert f"你的「{DRIVER_CERT}」资质复核没有通过" in titles
        assert db.query(AdminAudit).filter(AdminAudit.action == "cert_spot_overturn").count() == 1
    stats = {x["reviewer_id"]: x for x in client.get(f"{S}?status=all", headers=auth(b)).json()["reviewers"]}
    assert stats[a["id"]]["sampled"] == 1 and stats[a["id"]]["overturned"] == 1, "原审核员被推翻的记一笔"


def test_random_sampling_rate_and_who_can_see_it(client, monkeypatch):
    a = _admin(client, "13600003758", ["compliance"])
    ops = _admin(client, "13600003759", ["ops"])
    monkeypatch.setattr(cert_spot, "SPOT_CHECK_RATE", 1.0)
    app_id = _approve(client, a, make_verified(client, "13600003760"), "健身教练证")
    items = client.get(S, headers=auth(a)).json()["items"]
    assert [(x["application_id"], x["reason"]) for x in items] == [(app_id, "random")], "按比例抽到的标 random"
    rejected_id = apply_cert(client, make_verified(client, "13600003761"), name="健身教练证").json()["id"]
    client.post(f"{API}/admin/certifications/{rejected_id}/decide", json={"approve": False, "reason": "照片看不清"}, headers=auth(a))
    assert len(client.get(S, headers=auth(a)).json()["items"]) == 1, "驳回的不抽"
    with SessionLocal() as db:   # 函数自己也守住：不是已核准的一律不抽（别处调用时不靠调用方）
        from app.modules.account.models_cert import CertificationApplication

        assert cert_spot.maybe_sample(db, db.get(CertificationApplication, rejected_id)) is None
    assert client.get(S, headers=auth(ops)).status_code == 403, "只给合规审核员"
    monkeypatch.setattr(cert_spot, "SPOT_CHECK_RATE", 0.1)
    picks = [cert_spot._sampled(i) for i in range(1, 2001)]
    assert 100 < sum(picks) < 300, "约一成"
    assert picks == [cert_spot._sampled(i) for i in range(1, 2001)], "同一份申请结果固定"
