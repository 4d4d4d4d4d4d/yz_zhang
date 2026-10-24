"""ADMIN-063 审计链头外部锚定（156 号 spec）。

149 号的哈希链能发现「改了一条没重算」，发现不了「有库权限的人把整条链重算」。
锚点写在存证链上（存证链再交第三方背书）：重算过的链，锚定那一刻的那一条哈希对不上。
"""
import pytest
from sqlalchemy import text

from app.core.db import SessionLocal
from app.modules.admin.audit_chain import anchor_head, digest, verify
from app.modules.admin.models import AdminAudit, AuditChainHead
from app.modules.admin.router import record_audit
from app.modules.anchor.models import AnchorEntry
from app.modules.anchor.service import verify_chain
from tests.conftest import JOB_HEADERS

API = "/api/v1"


@pytest.fixture(autouse=True)
def _fresh_db(client):
    yield


def _chain(n):
    with SessionLocal() as db:
        for i in range(n):
            record_audit(db, 1, f"act_{i}", "user", i, f"第 {i} 条")
        db.commit()


def _anchor():
    with SessionLocal() as db:
        out = anchor_head(db)
        db.commit()
        return out


def _verify():
    with SessionLocal() as db:
        return verify(db)


def test_anchor_writes_the_head_into_the_evidence_chain_once_per_change(client):
    assert _anchor()["anchored"] is False      # 还没有审计
    _chain(3)
    a = _anchor()
    assert a["anchored"] is True
    with SessionLocal() as db:
        head = db.get(AuditChainHead, 1)
        assert (a["head_audit_id"], a["head_hash"]) == (head.last_audit_id, head.last_hash)
        assert db.query(AnchorEntry).filter(AnchorEntry.event_type == "admin_audit.head").count() == 1
        assert verify_chain(db)["valid"] is True, "锚点进的是同一条存证哈希链"
    assert _anchor()["anchored"] is False, "链头没变就不重复写"
    _chain(1)
    assert _anchor()["anchored"] is True
    v = _verify()
    assert v["ok"] is True and v["anchors_checked"] == 2 and v["last_anchor_audit_id"] == v["head_audit_id"]
    assert v["last_anchored_at"]


def test_recomputing_the_whole_chain_is_caught_by_the_anchor(client):
    """有库权限的人改了一条，再把整条链和链头都重算——链本身是自洽的，只有锚点对不上。"""
    _chain(4)
    _anchor()
    with SessionLocal() as db:
        rows = db.query(AdminAudit).order_by(AdminAudit.id).all()
        rows[1].detail = "改过的说明"
        prev = ""
        for r in rows:
            r.prev_hash = prev
            r.hash = digest(prev, r)
            prev = r.hash
        head = db.get(AuditChainHead, 1)
        head.last_hash = prev
        db.commit()
        anchored_id = rows[-1].id
    v = _verify()
    assert v["ok"] is False
    assert any(p["audit_id"] == anchored_id and "整体重算" in p["reason"] for p in v["problems"])


def test_deleting_the_anchored_row_is_caught(client):
    _chain(3)
    _anchor()
    with SessionLocal() as db:
        last = db.query(AdminAudit).order_by(AdminAudit.id.desc()).first().id
        db.execute(text("DELETE FROM admin_audits WHERE id = :i"), {"i": last})
        db.commit()
    assert any("已经不在了" in p["reason"] for p in _verify()["problems"])


def test_job_endpoint_is_scheduled_and_runs(client):
    from app.core.jobs import JOBS

    assert any(j.path == "/admin/jobs/anchor-audit-head" for j in JOBS)
    _chain(2)
    r = client.post(f"{API}/admin/jobs/anchor-audit-head", headers=JOB_HEADERS)
    assert r.status_code == 200 and r.json()["anchored"] is True
