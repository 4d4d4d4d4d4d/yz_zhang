from app.core.db import SessionLocal
from app.modules.contract.models import Contract, ContractSignature, Milestone
from app.modules.contract.service import verify_signatures
from app.vendors.signature import PlatformWitnessSignature, document_hash
from tests.conftest import auth, topup
from tests.test_task_flow import publish_task, match_and_fund


def test_first_signature_locks_milestones(client, requester, worker):
    task = publish_task(client, requester)
    aid = client.post(f"/api/v1/tasks/{task['id']}/applications", json={"message": "我来"}, headers=auth(worker)).json()["id"]
    cid = client.post(f"/api/v1/applications/{aid}/accept", headers=auth(requester)).json()["contract_id"]
    assert client.post(f"/api/v1/contracts/{cid}/sign", headers=auth(worker)).status_code == 200
    result = client.post(f"/api/v1/contracts/{cid}/milestones", json={"items": [{"title": "changed", "amount_cents": 20000}]}, headers=auth(requester))
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "milestones_locked"


def test_signature_binds_milestones_and_amount(client, requester, worker):
    topup(client, requester, 100000)
    cid = match_and_fund(client, requester, worker, publish_task(client, requester))
    with SessionLocal() as db:
        c = db.get(Contract, cid)
        assert verify_signatures(db, c)["valid"]
        m = db.query(Milestone).filter_by(contract_id=cid).first()
        m.title += "altered"
        db.flush()
        assert not verify_signatures(db, c)["valid"]
        db.rollback()
    with SessionLocal() as db:
        c = db.get(Contract, cid)
        c.amount_cents += 1
        assert not verify_signatures(db, c)["valid"]


def test_legacy_signature_uses_original_provider(client, requester, worker, monkeypatch):
    from app.vendors.signature import settings
    topup(client, requester, 100000)
    cid = match_and_fund(client, requester, worker, publish_task(client, requester))
    with SessionLocal() as db:
        c = db.get(Contract, cid)
        row = db.query(ContractSignature).filter_by(contract_id=cid).first()
        result = PlatformWitnessSignature().sign(row.signer_id, document_hash(c.terms), {})
        row.document_hash, row.signature, row.extra = document_hash(c.terms), result.signature, result.extra
        monkeypatch.setattr(settings, "SIGNATURE_PROVIDER", "future-provider")
        assert verify_signatures(db, c)["valid"]
        row.provider = "unknown-provider"
        assert not verify_signatures(db, c)["valid"]


def test_nonce_cannot_be_overridden_by_metadata():
    provider = PlatformWitnessSignature()
    result = provider.sign(1, 'a' * 64, {"nonce": "attacker", "ip": "private"})
    assert result.extra["nonce"] != "attacker"
    assert "ip" not in result.extra
    assert provider.verify(1, 'a' * 64, result)
