"""LAW-062 法律条目的复核日期与到期复核（169 号 spec，V196）。

法规会改：去年写的「抚养费按收入 20%~30%」今年可能已经不对。条目没有有效期，就会一直原样回答下去。
现在每条都有复核日期（不写就上线后一年），过了这天问答就停用它（问题回到「找律师」、重新进雷达），
到期前 30 天与到期当天各提醒合规一次；复核过、内容仍然对就续期（最长 2 年，写审计）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.admin.models import AdminAudit
from app.modules.legal.faq import DEFAULT_VALID_DAYS, LegalFaq, beijing_today
from tests.conftest import JOB_HEADERS, auth, register
from tests.test_legal_faq import URL, _ask, _role
from tests.test_ticket_assign_reply import _titles

API = "/api/v1"
JOB = f"{API}/admin/jobs/remind-legal-reviews"
BODY = {"topic": "租房买房", "keywords": ["押金", "房东"], "answer": "押金一般在退租验房后返还，扣除要有约定和依据。拿不准建议找律师。",
        "source": "《民法典》第七百二十二条"}


def _published(client, a, b, **extra):
    f = client.post(URL, json={**BODY, **extra}, headers=auth(a)).json()
    client.post(f"{URL}/{f['id']}/submit", headers=auth(a))
    r = client.post(f"{URL}/{f['id']}/approve", headers=auth(b))
    assert r.status_code == 200, r.text
    return r.json()


def _set_valid(fid, days_from_today, stage=None):
    with SessionLocal() as db:
        f = db.get(LegalFaq, fid)
        f.valid_until = beijing_today() + timedelta(days=days_from_today)
        if stage is not None:
            f.review_stage = stage
        db.commit()


def test_default_review_date_and_expired_entries_stop_answering(client):
    a = _role(client, "13800330001", "合规甲", "compliance")
    b = _role(client, "13800330002", "合规乙", "compliance")
    u = register(client, "13800330003", "问的人")
    f = _published(client, a, b)
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(f, "LegalFaqRow")
    assert f["valid_until"] == (beijing_today() + timedelta(days=DEFAULT_VALID_DAYS)).isoformat() and f["expired"] is False
    assert _ask(client, u, "房东不退押金怎么办")["refused"] is False
    _set_valid(f["id"], -1)
    r = _ask(client, u, "房东不退押金怎么办")
    assert r["refused_reason"] == "out_of_scope", "过了复核日期就不能再拿它回答"
    row = next(x for x in client.get(URL, headers=auth(a)).json() if x["id"] == f["id"])
    assert row["expired"] is True and row["status"] == "published"


def test_reminders_30_days_before_and_on_expiry_once_each_to_compliance(client):
    a = _role(client, "13800330011", "合规甲", "compliance")
    b = _role(client, "13800330012", "合规乙", "compliance")
    ops = _role(client, "13800330013", "运营", "ops")
    f = _published(client, a, b)
    assert client.post(JOB, headers=JOB_HEADERS).json()["reminded_soon"] == [], "一年后到期：现在不提醒"
    _set_valid(f["id"], 20)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["reminded_soon"] == [f["id"]] and r["reminded_due"] == []
    assert client.post(JOB, headers=JOB_HEADERS).json()["reminded_soon"] == [], "每步只提醒一次"
    assert any("30 天内到复核日期" in t for t in _titles(client, a))
    assert not any("复核日期" in t for t in _titles(client, ops)), "只叫合规"
    _set_valid(f["id"], -1)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["reminded_due"] == [f["id"]]
    assert client.post(JOB, headers=JOB_HEADERS).json()["reminded_due"] == []
    assert any("已过复核日期，问答已停用" in t for t in _titles(client, b))


def test_renew_brings_it_back_resets_reminders_and_is_audited(client):
    a = _role(client, "13800330021", "合规甲", "compliance")
    b = _role(client, "13800330022", "合规乙", "compliance")
    u = register(client, "13800330023", "问的人")
    f = _published(client, a, b)
    _set_valid(f["id"], -1, stage=2)
    bad = client.post(f"{URL}/{f['id']}/renew", json={"valid_until": (beijing_today() + timedelta(days=800)).isoformat()}, headers=auth(a))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "legal_faq_bad_valid_until"
    past = client.post(f"{URL}/{f['id']}/renew", json={"valid_until": beijing_today().isoformat()}, headers=auth(a))
    assert past.status_code == 400
    new = (beijing_today() + timedelta(days=200)).isoformat()
    ok = client.post(f"{URL}/{f['id']}/renew", json={"valid_until": new}, headers=auth(a)).json()
    assert ok["valid_until"] == new and ok["expired"] is False
    assert _ask(client, u, "房东不退押金怎么办")["refused"] is False, "续期后又能回答"
    with SessionLocal() as db:
        assert db.get(LegalFaq, f["id"]).review_stage == 0, "续期后提醒重新计"
        assert db.query(AdminAudit).filter(AdminAudit.action == "legal_faq_renew").count() == 1
    draft = client.post(URL, json=BODY, headers=auth(a)).json()
    nd = client.post(f"{URL}/{draft['id']}/renew", json={"valid_until": new}, headers=auth(a))
    assert nd.status_code == 409 and nd.json()["detail"]["code"] == "legal_faq_not_published"


def test_draft_can_carry_its_own_review_date_within_two_years(client):
    a = _role(client, "13800330031", "合规甲", "compliance")
    b = _role(client, "13800330032", "合规乙", "compliance")
    d = (beijing_today() + timedelta(days=90)).isoformat()
    f = _published(client, a, b, valid_until=d)
    assert f["valid_until"] == d
    far = client.post(URL, json={**BODY, "valid_until": (beijing_today() + timedelta(days=731)).isoformat()}, headers=auth(a))
    assert far.status_code == 400 and far.json()["detail"]["code"] == "legal_faq_bad_valid_until"
