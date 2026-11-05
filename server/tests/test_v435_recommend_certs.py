"""SCN-294d（408 号 spec，V435）要资质的单只推荐张张都有的人；理由里写明持什么证。

改造前推荐不看资质：发单人照着推荐去邀请，对方去报名才被「该类目需……」挡下，两头白跑。
"""
from datetime import timedelta

from app.modules.account.models import utcnow
from app.modules.task.service import HEIGHT_WORK_CERT, REFRIGERATION_CERT
from tests.conftest import auth, make_admin
from tests.test_certification import apply_cert, make_verified
from tests.test_multiday_slots import _post

API = "/api/v1"


def _approve(client, ops, w, name):
    app_id = apply_cert(client, w, name=name, expires_at=(utcnow() + timedelta(days=365)).isoformat()).json()["id"]
    assert client.post(f"{API}/admin/certifications/{app_id}/decide", json={"approve": True, "reason": "证件可查"},
                       headers=auth(ops)).status_code == 200


def _recs(client, requester, tid):
    return {r["user_id"]: r for r in client.get(f"{API}/tasks/{tid}/recommendations", headers=auth(requester)).json()}


def test_task_added_cert_filters_recommendations(client, requester):
    ops = make_admin(client, "13600043501", "审核")
    holder = make_verified(client, "13600043502")
    other = make_verified(client, "13600043503")
    _approve(client, ops, holder, HEIGHT_WORK_CERT)
    t = _post(client, requester, title="展台背板 3 米高", description="要上梯子", category="展台搭建",
              task_certs=[HEIGHT_WORK_CERT]).json()
    recs = _recs(client, requester, t["id"])
    assert holder["id"] in recs and other["id"] not in recs
    assert f"持「{HEIGHT_WORK_CERT}」" in recs[holder["id"]]["reasons"]


def test_category_required_cert_filters_recommendations_too(client, requester):
    ops = make_admin(client, "13600043504", "审核")
    holder = make_verified(client, "13600043505")
    other = make_verified(client, "13600043506")
    _approve(client, ops, holder, REFRIGERATION_CERT)
    t = _post(client, requester, title="空调不制冷", description="挂机", category="空调加氟维修").json()
    recs = _recs(client, requester, t["id"])
    assert holder["id"] in recs and other["id"] not in recs


def test_no_cert_needed_nothing_filtered(client, requester):
    a = make_verified(client, "13600043507")
    b = make_verified(client, "13600043508")
    t = _post(client, requester, title="展位布置", description="只摆展品", category="展台搭建").json()
    recs = _recs(client, requester, t["id"])
    assert {a["id"], b["id"]} <= set(recs)
    assert not any(x.startswith("持「") for r in recs.values() for x in r["reasons"])


def test_expired_cert_does_not_count(client, requester):
    from app.core.db import SessionLocal
    from app.modules.account.models_cert import CertificationApplication

    ops = make_admin(client, "13600043509", "审核")
    w = make_verified(client, "13600043510")
    _approve(client, ops, w, HEIGHT_WORK_CERT)
    with SessionLocal() as db:
        for r in db.query(CertificationApplication).filter(CertificationApplication.user_id == w["id"]).all():
            r.expires_at = utcnow() - timedelta(days=1)
        db.commit()
    t = _post(client, requester, title="展台背板", description="3 米", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    assert w["id"] not in _recs(client, requester, t["id"])


def test_profile_risk_mentions_added_certs(client, requester):
    r = client.post(f"{API}/profiles/task-draft", json={"title": "展台背板", "category": "展台搭建", "task_certs": [HEIGHT_WORK_CERT]},
                    headers=auth(requester)).json()
    assert any(x["kind"] == "cert" and f"这一单另外要「{HEIGHT_WORK_CERT}」" in x["text"] for x in r["risks"]), r["risks"]
    plain = client.post(f"{API}/profiles/task-draft", json={"title": "展台背板", "category": "展台搭建"}, headers=auth(requester)).json()
    assert not any(x["kind"] == "cert" for x in plain["risks"])
    t = _post(client, requester, title="展台背板 3 米高", description="要上梯子", category="展台搭建", task_certs=[HEIGHT_WORK_CERT]).json()
    prof = client.get(f"{API}/tasks/{t['id']}/profile", headers=auth(requester)).json()
    assert any(f"「{HEIGHT_WORK_CERT}」" in x["text"] for x in prof["risks"])
